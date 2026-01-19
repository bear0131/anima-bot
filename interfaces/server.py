from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from interfaces.protocol import IncomingEvent
from agent.schema import Event
import asyncio
import json

app = FastAPI()

# 全局变量存队列和连接（MVP 简化写法）
# 在 core 启动时会把它的 queue 传进来，或者我们直接引用
global_event_queue: asyncio.Queue = None
active_socket: WebSocket = None

def set_queue(queue: asyncio.Queue):
    global global_event_queue
    global_event_queue = queue

async def send_packet(data: dict):
    """供 Core 调用的发送函数"""
    if active_socket:
        await active_socket.send_json(data)
    else:
        print("[Warn] No active Node.js connection!")

@app.websocket("/ws/minecraft")
async def websocket_endpoint(websocket: WebSocket):
    global active_socket
    await websocket.accept()
    active_socket = websocket
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
