from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from interfaces.protocol import IncomingEvent, OutgoingCommand
from agent.schema import Event
from agent.logger import get_ws_handler
import asyncio
import json
from datetime import datetime
import os
import logging

# 配置 FastAPI/uvicorn 日志级别，减少 INFO 输出
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("fastapi").setLevel(logging.WARNING)

app = FastAPI()

# 添加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件服务
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
async def frontend():
    """前端首页"""
    frontend_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return JSONResponse({"error": "Frontend not found"}, status_code=404)

# 全局变量存队列和连接（MVP 简化写法）
# 在 core 启动时会把它的 queue 传进来，或者我们直接引用
global_event_queue: asyncio.Queue = None
active_socket: WebSocket = None

# JS 连接状态
js_connection_status = {"connected": False, "last_connected": None}

# Observer Vision 连接状态
vision_connection_status = {
    "connected": False,
    "last_connected": None,
    "last_frame": None,
    "state": None,
    "camera_bound": None,
}

# Agent 状态引用（由 core.py 设置）
_global_agent_state = None

def set_agent_state(state):
    """设置全局 agent state，供 core.py 调用"""
    global _global_agent_state
    _global_agent_state = state

def get_agent_state():
    """获取全局 agent state"""
    global _global_agent_state
    return _global_agent_state

def set_queue(queue: asyncio.Queue):
    global global_event_queue
    global_event_queue = queue


def is_observer_front_active(max_stale_seconds: float = 3.0) -> bool:
    """判断 observer 主视角是否活跃（用于 front 截图优先级）"""
    if not vision_connection_status["connected"]:
        return False

    last_frame_iso = vision_connection_status.get("last_frame")
    if not last_frame_iso:
        return False

    try:
        delta = datetime.now() - datetime.fromisoformat(last_frame_iso)
        return delta.total_seconds() <= max_stale_seconds
    except Exception:
        return False

async def send_packet(data: dict):
    """供 Core 调用的发送函数"""
    if active_socket:
        await active_socket.send_json(data)
    else:
        print("[Warn] No active Node.js connection!")

@app.get("/ws/status")
async def connection_status():
    """供 JSProcessManager 或其他模块查询 WebSocket 连接状态"""
    return js_connection_status

@app.websocket("/ws/minecraft")
async def websocket_endpoint(websocket: WebSocket):
    global active_socket
    await websocket.accept()
    active_socket = websocket
    js_connection_status["connected"] = True
    js_connection_status["last_connected"] = datetime.now().isoformat()
    print("[Server] Node.js connected.")

    try:
        while True:
            # 1. 接收原始 JSON
            data = await websocket.receive_json()
            # 2. 校验并放入队列
            incoming_event = IncomingEvent(**data)
            if global_event_queue:
                await global_event_queue.put(incoming_event)
    except WebSocketDisconnect:
        print("[Server] Node.js disconnected.")
        active_socket = None
        js_connection_status["connected"] = False


@app.get("/ws/vision/status")
async def vision_status():
    """Observer vision 连接状态"""
    return vision_connection_status


@app.websocket("/ws/vision")
async def vision_websocket_endpoint(websocket: WebSocket):
    """接收 observer-client 的主视角流并写入 agent_state.last_screenshot_front"""
    await websocket.accept()
    vision_connection_status["connected"] = True
    vision_connection_status["last_connected"] = datetime.now().isoformat()
    print("[Server] Observer vision connected.")

    try:
        while True:
            data = await websocket.receive_json()
            packet_type = data.get("type")
            content = data.get("content") or {}

            if packet_type == "vision_status":
                vision_connection_status["state"] = content.get("state")
                vision_connection_status["camera_bound"] = content.get("camera_bound")

            elif packet_type == "vision_frame":
                jpeg_base64 = content.get("jpeg_base64")
                if jpeg_base64:
                    state = get_agent_state()
                    if state is not None:
                        state.last_screenshot_front = jpeg_base64
                        state.timestamp_screenshot = datetime.now()

                vision_connection_status["last_frame"] = datetime.now().isoformat()

    except WebSocketDisconnect:
        print("[Server] Observer vision disconnected.")
        vision_connection_status["connected"] = False
        vision_connection_status["state"] = None
        vision_connection_status["camera_bound"] = None


@app.websocket("/ws/logs")
async def logs_websocket(websocket: WebSocket):
    """前端日志流 WebSocket"""
    await websocket.accept()

    # 获取 handler
    ws_handler = get_ws_handler()
    print(f"[Server] Frontend logs client connected. Active clients: {len(ws_handler.clients) + 1}")

    # 创建一个队列用于接收日志
    log_queue = asyncio.Queue()
    ws_handler.add_client(log_queue)

    try:
        while True:
            # 等待日志或心跳（设置超时）
            try:
                log_entry = await asyncio.wait_for(log_queue.get(), timeout=30.0)
                await websocket.send_json(log_entry)
            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except:
                    break
    except WebSocketDisconnect:
        print(f"[Server] Frontend logs client disconnected. Active clients: {len(ws_handler.clients)}")
    except Exception as e:
        print(f"[Server] Error in logs websocket: {e}")
    finally:
        ws_handler.remove_client(log_queue)
        print(f"[Server] Cleaned up log client. Active clients: {len(ws_handler.clients)}")


# ==================== 前端 API 端点 ====================

from pydantic import BaseModel


class CommandRequest(BaseModel):
    type: str  # "chat" | "code_run_request"
    content: str


@app.get("/api/status")
async def get_agent_status():
    """获取 agent 当前状态"""
    state = get_agent_state()

    # 返回状态，即使 agent 未初始化也返回 200
    return {
        "initialized": state is not None,
        "connected": js_connection_status["connected"],
        "vision_connected": vision_connection_status["connected"],
        "status": state.status if state else "IDLE",
        "mc_state": state.mc_state if state else None,
        "last_screenshot_front": state.last_screenshot_front if state else None
    }


@app.get("/api/screenshot")
async def get_screenshot():
    """获取最新截图"""
    state = get_agent_state()
    if state is None:
        return JSONResponse({"error": "Agent not initialized"}, status_code=503)
    return {
        "screenshot_front": state.last_screenshot_front
    }


@app.post("/api/command")
async def send_command(command: CommandRequest):
    """
    发送命令给 agent
    type: "chat" | "code_run_request"
    """
    # 检查连接状态
    if not js_connection_status["connected"] or not active_socket:
        return JSONResponse(
            {"error": "Not connected to Minecraft", "connected": False},
            status_code=503
        )

    if command.type not in ["chat", "code_run_request"]:
        return JSONResponse({"error": "Invalid command type"}, status_code=400)

    cmd = OutgoingCommand(
        type=command.type,
        target="minecraft",
        payload=command.content,
    )
    await send_packet(cmd.model_dump())
    return {"status": "command_sent", "type": command.type}


@app.get("/api/inventory")
async def get_inventory():
    """获取背包信息"""
    state = get_agent_state()
    if state is None or state.mc_state is None:
        return JSONResponse({"error": "Agent state not available"}, status_code=503)
    return state.mc_state.inventory or {}


@app.get("/api/llm-requests")
async def get_llm_requests():
    """获取 LLM 请求历史"""
    from agent.main_agent import get_llm_requests as get_llm_reqs
    requests = get_llm_reqs()
    return requests
