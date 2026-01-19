import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
from interfaces.protocol import IncomingEvent
from agent.short_memory import ShortTermMemory

from agent.capabilities.chat_capability import ChatCapability


class Brain:
    def __init__(self):
        self.caps = [
            ChatCapability(),
        ]

    async def think_stream(self, memory: ShortTermMemory) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式处理事件，按完成顺序产出结果。
        """
        active_caps = []
        has_exclusive = False

        for cap in self.caps:
            can_process, is_exclusive = await cap.can_handle(memory)
            if can_process:
                active_caps.append((cap, is_exclusive))
                if is_exclusive:
                    has_exclusive = True

        if not active_caps:
            return

        if has_exclusive:
            exclusive_cap = next(cap for cap, exclusive in active_caps if exclusive)
            decision = await exclusive_cap.get_decision(memory)
            yield decision
            return

        tasks = {}
        for cap, _ in active_caps:
            task = asyncio.create_task(cap.get_decision(memory))
            tasks[task] = cap

        for finished_task in asyncio.as_completed(tasks.keys()):
            try:
                decision = await finished_task
                yield decision
            except Exception as e:
                print(f"Capability Error: {e}")
