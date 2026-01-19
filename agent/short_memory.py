from collections import deque
from agent.schema import Event, AgentState, MCState
from typing import List, Dict, Optional
import asyncio
import json
from interfaces.server import send_packet

import dotenv

dotenv.load_dotenv()
bot_username = dotenv.get_key('.env', 'BOT_USERNAME') or 'animabot'

class ShortTermMemory:
    def __init__(self, agent_state: AgentState, max_history=20):
        self.events: deque[Event] = deque(maxlen=max_history)
        self.state = agent_state

    def add_event(self, event: Event):
        """
        添加事件到记忆中
        """
        self.events.append(event)
    
    def get_last_event(self) -> Optional[Event]:
        """
        获取最后一个事件

        Returns:
            Optional[Event]: 最后一个事件，如果记忆为空则返回 None
        """
        return self.events[-1] if self.events else None 

    def render_state_for_prompt(self) -> str:
        """渲染 MC 状态为文本
        
        Returns:
            str: 格式化的状态描述
        """
        if not self.state.mc_state:
            return "当前状态: 未知\n"

        mc = self.state.mc_state
        lines = []
        
        lines.append(f"### 当前游戏状态")
        lines.append(f"位置: x={mc.position.get('x', 0):.1f}, y={mc.position.get('y', 0):.1f}, z={mc.position.get('z', 0):.1f}" if mc.position else "位置: 未知")
        lines.append(f"生物群系: {mc.biome or '未知'}")
        lines.append(f"时间: {mc.time_of_day or '未知'}")
        lines.append(f"生命值: {mc.health or 0:.1f}/20")
        lines.append(f"饥饿值: {mc.hunger or 0:.1f}/20")
        
        if mc.equipment:
            safe_equipment = [(item or "none") for item in mc.equipment]
            lines.append(f"装备: {', '.join(safe_equipment)}")
        
        if mc.nearby_blocks:
            lines.append(f"周围方块: {', '.join(mc.nearby_blocks[:10])}")  # 限制数量
        
        if mc.entities:
            sorted_entities = sorted(mc.entities.items(), key=lambda x: x[1])
            entities_str = ', '.join([f"{name}({dist:.1f}m)" for name, dist in sorted_entities[:5]])
            lines.append(f"附近实体: {entities_str}")
        
        if mc.inventory:
            items = [f"{name}x{count}" for name, count in mc.inventory.items()]
            lines.append(f"物品栏 ({mc.inventory_used or 0}/36): {', '.join(items)}")

        return '\n'.join(lines) + '\n'

    def render_llm_context(self, include_image=True) -> List[Dict]:
        """
        核心：将 Event流 + 状态板 -> 渲染成 OpenAI 格式
        """
        messages = []
        
        # 1. 插入历史事件
        for event in self.events:
            if event.type == "chat":
                if event.source == 'bot':
                    messages.append({"role": "assistant", "content": event.content})
                else:
                    username = event.metadata.get('user', 'unknown')
                    messages.append({"role": "user", "content": f"[Chat] {username}: {event.content}"})
            elif event.type == "code_run_request":
                messages.append({"role": "system", "content": f"[System] 开始运行代码: {event.content}"})
            elif event.type == "code_run_done":
                messages.append({"role": "system", "content": f"[System] 代码运行结束. 结果: {event.content}"})
            elif event.type == "error":
                messages.append({"role": "system", "content": f"[Error] {event.content}"})

        # 2. 当前状态
        messages.append({"role": "system", "content": self.render_state_for_prompt()})

        # 3. 插入图片
        if include_image and self.state.last_screenshot:
            messages.append({
                "role": "user", 
                "content": [
                    {"type": "text", "text": "这是你现在看到的景象:"},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{self.state.last_screenshot}",
                        "detail": "low"
                    }}
                ]
            })

        return messages
