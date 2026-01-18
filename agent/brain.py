import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
from interfaces.protocol import IncomingEvent

from agent.capabilities.chat_capability import ChatCapability


class Brain:
    def __init__(self):
        self.caps = [
            ChatCapability(),
        ]

    async def think(self, event: IncomingEvent) -> Dict[str, Any] | None:
        """
        处理事件并返回第一个决策。
        """
        async for result in self.think_stream(event):
            return result
        return None

    async def think_stream(self, event: IncomingEvent, context: list, current_frame: Optional[str]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式处理事件，按完成顺序产出结果。
        """
        active_caps = []
        has_exclusive = False

        for cap in self.caps:
            can_process, is_exclusive = await cap.can_handle(event)
            if can_process:
                active_caps.append((cap, is_exclusive))
                if is_exclusive:
                    has_exclusive = True

        if not active_caps:
            return

        if has_exclusive:
            exclusive_cap = next(cap for cap, exclusive in active_caps if exclusive)
            result = await exclusive_cap.run(event, context, current_frame)
            yield result
            return

        tasks = {}
        for cap, _ in active_caps:
            task = asyncio.create_task(cap.run(event, context, current_frame))
            tasks[task] = cap

        for finished_task in asyncio.as_completed(tasks.keys()):
            try:
                result = await finished_task
                yield result
            except Exception as e:
                print(f"Capability Error: {e}")
