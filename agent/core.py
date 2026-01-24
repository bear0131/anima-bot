import os
import asyncio
from dotenv import load_dotenv
import uvicorn
from interfaces import server
from interfaces.protocol import IncomingEvent, OutgoingCommand
from interfaces.js_process_manager import JSProcessManager
from agent.main_agent import MainAgent
from agent.schema import Event, AgentState
from agent.memory import Memory
from openai import AsyncOpenAI

load_dotenv()

class Agent:
    def __init__(self):
        # 1. 初始化队列
        self.event_queue = asyncio.Queue()
        # 把队列挂载到 Server 模块上
        server.set_queue(self.event_queue)

        self.agent_state = AgentState()
        self.llm_client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") # 兼容第三方/中转
        )

        # 获取用于记忆整理的模型名称 (默认用 mini 省钱)
        self.memory_model = os.getenv("MEMORY_MODEL_NAME", "Qwen3-VL-30B-A3B-Instruct")

        # 3. 初始化 Memory (传入刚创建的 client 和模型名)
        self.memory = Memory(
            agent_state=self.agent_state,
            llm_client=self.llm_client,
            model_name=self.memory_model
        )
        self.main_agent = MainAgent()

        # 初始化 JS 进程管理器
        # 从环境变量读取命令行参数
        js_extra_args = []
        if os.getenv("HEADLESS") == "false":
            js_extra_args.append("--headless=false")
        if os.getenv("PRISMARINE_VIEWER") == "false":
            js_extra_args.append("--prismarine_viewer=false")

        self.js_manager = JSProcessManager(extra_args=js_extra_args)
        
    async def start(self):
        # 启动 Server (作为一个后台 Task)
        # 注意：这里使用 uvicorn 的配置来在 asyncio 循环里跑
        config = uvicorn.Config(server.app, host="0.0.0.0", port=8000, log_level="info")
        server_instance = uvicorn.Server(config)
        asyncio.create_task(server_instance.serve())

        print("Agent Core Started. Starting JS process...")

        # 启动 JS 进程
        await self.js_manager.start()

        # 等待 JS 端就绪
        ready = await self.js_manager.wait_until_ready(timeout=60)
        if not ready:
            print("[Agent] JS process failed to become ready, shutting down")
            await self.js_manager.stop()
            return

        print("[Agent] JS process ready. Starting main loop...")

        # 启动主循环
        try:
            await self.main_loop()
        finally:
            # 清理 JS 进程
            await self.js_manager.cleanup()

    async def main_loop(self):
        while True:
            try:
                # 缩短一点超时时间，或者直接等待
                incoming_event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # 只要检查是否活着，打印日志即可，不要干预
                # 如果 JSProcessManager 正在重启中，is_alive 也是 False，这是正常的
                if not await self.js_manager.is_alive():
                    #TODO 可以检查一下 server 是否有连接，确认是不是真的断了很久
                    pass 
                continue

            # print(f"[Core] Received: {incoming_event.type}")

            # 转换 IncomingEvent -> Event
            event = Event(
                type=incoming_event.type,
                content=incoming_event.content,
                source=incoming_event.source,
                metadata=incoming_event.metadata
            )

            if event.type == 'screenshot':
                self.agent_state.last_screenshot = event.content

            elif event.type == 'observation':
                self.agent_state.update_mc_state(event.content)

            elif event.type == 'chat':
                # 1. 将 chat 事件加入 memory
                self.memory.add_event(event)
                print(f"\n{'='*60}")
                print(f"[Core] 📥 收到聊天事件: {event.content}")
                print(f"{'='*60}")
                # 2. 调用 main_agent 处理
                async for decision in self.main_agent.think_stream(self.memory):
                    print(f"[Core] 📤 决策: {decision['type']} - {decision.get('content', '')[:100]}")
                    await self.execute_decision(decision)

            elif event.type == 'code_run_result':
                # 1. 构建结果描述
                print(f"\n{'='*60}")
                if incoming_event.error:
                    result_desc = f"代码执行失败: {incoming_event.error}"
                    if incoming_event.content:
                        result_desc += f"\n错误详情:\n{incoming_event.content}"
                    print(f"[Core] ❌ 代码执行失败: {incoming_event.error}")
                else:
                    result_desc = f"代码执行成功!"
                    if incoming_event.content:
                        result_desc += f"\n返回结果:\n{incoming_event.content}"
                    print(f"[Core] ✅ 代码执行成功")
                    if incoming_event.content:
                        print(f"[Core] 📄 返回内容:\n{incoming_event.content}")
                print(f"{'='*60}\n")

                # 2. 更新 event content 为可读的描述
                event.content = result_desc

                # 3. 将 code_run_result 事件加入 memory
                self.memory.add_event(event)

                # 4. 调用 main_agent 继续思考（基于执行结果）
                # 此时 last_event 是 code_run_result，main_agent 需要能处理这种情况
                async for decision in self.main_agent.think_stream(self.memory):
                    print(f"[Core] 📤 决策: {decision['type']} - {decision.get('content', '')[:100]}")
                    await self.execute_decision(decision)

            self.event_queue.task_done()

    def record_command(self, cmd: OutgoingCommand):
        self.memory.add_event(Event(
            type=cmd.type,
            content=cmd.payload,
            source='bot',
            metadata={}
        ))

    async def execute_decision(self, decision):
        print(f"[Exec] Doing: {decision}")

        cmd = OutgoingCommand(
            type=decision['type'],
            target='minecraft',
            payload=decision['content'],
        )

        self.record_command(cmd)

        await server.send_packet(cmd.model_dump())

if __name__ == "__main__":
    agent = Agent()
    asyncio.run(agent.start())