import asyncio
from dotenv import load_dotenv
import uvicorn
from interfaces import server
from agent.brain import Brain

load_dotenv()

class Agent:
    def __init__(self):
        # 1. 初始化队列
        self.event_queue = asyncio.Queue()
        # 把队列挂载到 Server 模块上
        server.set_queue(self.event_queue)

        self.latest_visual_frame = None 

        self.context = []

        # 2. 初始化大脑
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
            event = await self.event_queue.get()
            
            print(f"[Core] Received: {event.type}")

            if event.type == 'frame':
                self.latest_visual_frame = event.content
            else:
                async for decision in self.brain.think_stream(event, self.context, self.latest_visual_frame):
                    print(f"[Core] Got decision: {decision}")
                    await self.execute_decision(decision)
            
            self.event_queue.task_done()

    async def execute_decision(self, decision):
        print(f"[Exec] Doing: {decision}")
        
        if decision['type'] == 'talk':
            payload = {
                "target": "minecraft",
                "type": "chat",
                "payload": decision['content']
            }
            await server.send_packet(payload)
            
        elif decision['type'] == 'run_code':
            payload = {
                "target": "minecraft",
                "type": "run_code",
                "payload": decision['code']
            }
            await server.send_packet(payload)

if __name__ == "__main__":
    agent = Agent()
    asyncio.run(agent.start())