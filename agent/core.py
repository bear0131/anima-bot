import os
import asyncio
from dotenv import load_dotenv
import uvicorn
from interfaces import server
from interfaces.protocol import IncomingEvent, OutgoingCommand
from agent.brain import Brain
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

        self.agent_state = AgentState()

        # 3. 初始化 Memory (传入刚创建的 client 和模型名)
        self.memory = Memory(
            agent_state=self.agent_state,
            llm_client=self.llm_client,
            model_name=self.memory_model
        )
        self.brain = Brain()
        
    async def start(self):
        # 启动 Server (作为一个后台 Task)
        # 注意：这里使用 uvicorn 的配置来在 asyncio 循环里跑
        config = uvicorn.Config(server.app, host="0.0.0.0", port=8000, log_level="info")
        server_instance = uvicorn.Server(config)
        server_task = asyncio.create_task(server_instance.serve())
        
        print("Agent Core Started. Waiting for events...")
        
        # 启动主循环
        await self.main_loop()

    async def main_loop(self):
        while True:
            incoming_event = await self.event_queue.get()

            print(f"[Core] Received: {incoming_event.type}")

            if incoming_event.type == 'code_run_done':
                print(f'CODE RUN DONE! \n{incoming_event.content}')

            if incoming_event.error:
                print(f'[Core] ERROR!\n{incoming_event.error}\n{incoming_event.content}')

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
                self.memory.add_event(event)
                async for decision in self.brain.think_stream(self.memory):
                    print(f"[Core] Got decision: {decision}")
                    await self.execute_decision(decision)

            elif event.type == 'execution_done':
                pass

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