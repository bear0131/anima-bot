import asyncio
import os
import signal
import sys
import logging
import uvicorn
from fastapi import FastAPI, WebSocket
from interfaces.js_process_manager import JSProcessManager

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TestRunner")

# ==========================================
# 1. 定义 Mock Server (模拟 Agent 大脑)
# ==========================================
app = FastAPI()

@app.websocket("/ws/minecraft")
async def mock_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("[MockServer] Node.js JS 进程已连接！")
    try:
        while True:
            # 保持连接，接收消息但不处理，只是为了让 JS 不报错
            await websocket.receive_text()
    except Exception:
        logger.info("[MockServer] Node.js 连接断开")

async def run_mock_server():
    """在后台运行一个轻量级的 Uvicorn 服务器"""
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    logger.info("[MockServer] 正在启动端口 8000...")
    await server.serve()

# ==========================================
# 2. 测试逻辑
# ==========================================
async def test_crash_recovery():
    print(f"\n{'='*50}")
    print("🚀 开始测试：JS 进程生命周期与崩溃自动重启")
    print(f"{'='*50}\n")

    # --- A. 启动 Mock Server ---
    # 将 server 作为一个后台任务启动
    server_task = asyncio.create_task(run_mock_server())
    # 给它一点时间启动端口
    await asyncio.sleep(2) 

    # --- B. 初始化 JS Manager ---
    # 假设你本机开了 MC，或者 JS 代码能处理 MC 连接超时而不立刻崩溃
    manager = JSProcessManager(
        node_path="node", 
        js_entry="mineflayer/index.js",
        # restart_delay=3.0,  # 设置重启延迟为 3 秒
        extra_args=["--headless=true"] # 测试模式不弹窗
    )

    try:
        # --- C. 启动 JS 进程 ---
        print("[Test] 1. 启动 JS 进程...")
        await manager.start()
        
        # 等待 JS 启动并连接 WebSocket
        print("[Test] 等待 5 秒让 JS 完成初始化...")
        await asyncio.sleep(5)
        
        if not await manager.is_alive():
            print("[Test] ❌ 启动失败：进程在测试开始前就退出了。")
            # 可能是 MC 没开导致 JS 报错退出，或者依赖没装好
            return

        pid_1 = manager.process.pid
        print(f"[Test] ✅ 进程运行正常 (PID: {pid_1})")

        # --- D. 制造崩溃 ---
        print(f"\n[Test] 2. 🔪 模拟意外崩溃 (Kill PID {pid_1})...")
        
        if sys.platform == "win32":
            # Windows 下 terminate 比较强硬
            manager.process.terminate()
        else:
            os.kill(pid_1, signal.SIGKILL)
            
        # --- E. 验证自动重启 ---
        print("[Test] 等待 6 秒观察重启逻辑 (Delay 3s + Buffer)...")
        await asyncio.sleep(6)

        if not await manager.is_alive():
            print("[Test] ❌ 重启失败：进程未恢复")
        else:
            pid_2 = manager.process.pid
            if pid_2 != pid_1:
                print(f"[Test] ✅ 检测到新进程 (PID: {pid_2})")
                print(f"[Test] 🎉 测试通过：崩溃检测与自动重启功能正常！")
            else:
                print("[Test] ❓ 异常：PID 未变化，可能是杀进程失败")

    except Exception as e:
        print(f"[Test] ❌ 测试过程发生错误: {e}")
    
    finally:
        # --- F. 清理 ---
        print("\n[Test] 3. 清理资源...")
        await manager.cleanup()
        
        # 停止 Mock Server (强行取消任务)
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            print("[MockServer] 服务器已停止")

if __name__ == "__main__":
    # Windows 必须使用 ProactorEventLoop 才能支持子进程
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(test_crash_recovery())
    except KeyboardInterrupt:
        pass