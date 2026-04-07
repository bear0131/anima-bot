import os
import asyncio
from dotenv import load_dotenv
import uvicorn
from interfaces import server
from interfaces.protocol import IncomingEvent, OutgoingCommand
from interfaces.js_process_manager import JSProcessManager
from agent.main_agent import MainAgent
from agent.schema import Event, AgentState
from agent.logger import get_logger
from openai import AsyncOpenAI
from agent.tools.coding_tool import CodingTool

load_dotenv()

logger = get_logger("core")

class Agent:
    def __init__(self):
        # 1. 初始化队列
        self.event_queue = asyncio.Queue()
        # 把队列挂载到 Server 模块上
        server.set_queue(self.event_queue)

        self.agent_state = AgentState()
        
        self.main_agent = MainAgent(self.agent_state, self.event_queue)
        self.coding_tool = CodingTool(self.agent_state, self.event_queue)

        # 初始化 JS 进程管理器
        # 从环境变量读取命令行参数
        js_extra_args = []
        if os.getenv("HEADLESS") == "false":
            js_extra_args.append("--headless=false")
        if os.getenv("PRISMARINE_VIEWER") == "false":
            js_extra_args.append("--prismarine_viewer=false")

        self.js_manager = JSProcessManager(extra_args=js_extra_args)
        self._think_lock = asyncio.Lock() 

        # 注册全局状态供 API 访问
        server.set_agent_state(self.agent_state)
        logger.info("Global agent_state registered")
        
    async def start(self):
        # 启动 Server (作为一个后台 Task)
        # 注意：这里使用 uvicorn 的配置来在 asyncio 循环里跑
        config = uvicorn.Config(server.app, host="0.0.0.0", port=8000, log_level="warning")
        server_instance = uvicorn.Server(config)
        asyncio.create_task(server_instance.serve())

        logger.info("Agent Core Started. Starting JS process...")

        # 启动 JS 进程
        await self.js_manager.start()

        # 等待 JS 端就绪
        ready = await self.js_manager.wait_until_ready(timeout=60)
        if not ready:
            logger.error("JS process failed to become ready, shutting down")
            await self.js_manager.stop()
            return

        logger.info("JS process ready. Starting main loop...")

        # 启动主循环
        try:
            asyncio.create_task(self.main_agent.main_loop())
            await self.main_loop()
        finally:
            # 清理 JS 进程
            await self.js_manager.cleanup()

    async def main_loop(self):
        while True:
            try:
                incoming_event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if not await self.js_manager.is_alive():
                    pass 
                continue

            event = Event(
                type=incoming_event.type,
                content=incoming_event.content,
                source=incoming_event.source,
                metadata=incoming_event.metadata
            )
            
            if event.type == 'user_chat':
                logger.info(f"📥 收到聊天事件: {event.content}")
                asyncio.create_task(self.main_agent.event_queue.put(event))

            elif event.type == 'bot_chat':
                asyncio.create_task(self.execute_decision(event))
            
            elif event.type == 'tool_call':
                asyncio.create_task(self.coding_tool.tool_call(event))
            
            elif event.type == 'observation':
                self.agent_state.timestamp_state = event.timestamp
                self.agent_state.update_mc_state(event.content)

            elif event.type == 'task_done':
                logger.info(f"任务结束：{event.content}")
                asyncio.create_task(self.main_agent.event_queue.put(event))

            elif event.type == 'code_run_request':
                asyncio.create_task(self.execute_decision(event))
            
            elif event.type == 'code_run_result':
                if incoming_event.error:
                    result_desc = f"代码执行失败: {incoming_event.error}"
                    if incoming_event.content:
                        result_desc += f"\n错误详情:\n{incoming_event.content}"
                    logger.error(f"❌ 代码执行失败: {incoming_event.error}")
                else:
                    result_desc = f"代码执行成功!"
                    if incoming_event.content:
                        result_desc += f"\n返回结果:\n{incoming_event.content}"
                    logger.info("✅ 代码执行成功")
                
                event.content = result_desc

                asyncio.create_task(self.coding_tool.receive_result(event))

            self.event_queue.task_done()

    async def execute_decision(self, decision: Event):
        logger.debug(f"Executing: {decision.type}")

        cmd = OutgoingCommand(
            type=decision.type,
            target='minecraft',
            payload=decision.content,
            metadata=decision.metadata
        )

        await server.send_packet(cmd.model_dump())

if __name__ == "__main__":
    agent = Agent()
    asyncio.run(agent.start())