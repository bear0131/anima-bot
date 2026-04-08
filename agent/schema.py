from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, Literal, List
from datetime import datetime
import uuid
import time
import math
import asyncio

class Event(BaseModel):
    """系统内部流转的通用事件格式"""
    type: str          # "user_chat", "bot_chat", "tool_call", "observation", "screenshot", "task_done", "code_run_request", "code_run_result"
    content: Any       # 主要内容
    source: str        # "minecraft", "system", "bot"
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Optional[Dict] = {}

class MemoryNode(BaseModel):
    """Level 2 记忆节点：经过 LLM 提炼的信息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str        # 提炼后的事实/知识，例如 "Steve likes apples."
    importance: float   # 有效程度/重要性 (0-100)
    time: int = -1
    
    # 辅助字段，用于你的 f 函数计算
    decay_factor: float = 1.0  # 衰减因子

class MCState(BaseModel):
    """Minecraft 游戏状态（原始数据）"""
    # 从 status observation 获取
    biome: Optional[str] = None
    time_of_day: Optional[str] = None
    health: Optional[float] = None
    hunger: Optional[float] = None
    position: Optional[Dict[str, float]] = None  # {"x": 0, "y": 0, "z": 0}
    equipment: Optional[list] = None
    entities: Optional[Dict[str, float]] = None  # {entity_name: distance}
    nearby_items: Optional[list] = None  # [item_name1, item_name2, ...]
    yaw: Optional[float] = None
    pitch: Optional[float] = None
    
    # 从 inventory observation 获取
    inventory: Optional[Dict[str, int]] = None  # {item_name: count}
    inventory_used: Optional[int] = None
    
    # 从 voxels observation 获取
    nearby_blocks: Optional[list] = None  # [block_name1, block_name2, ...]
    visible_blocks: Optional[list] = None  # [block_name1, block_name2, ...]
    
    # 从 chests observation 获取
    chests: Optional[Dict] = None
    
    # 其他元数据
    raw_observation: Optional[Dict] = None  # 保留原始数据用于调试


class AgentState(BaseModel):
    """全局状态黑板"""
    status: str = "IDLE"
    mc_state: Optional[MCState] = None
    screenshots: Optional[List[str]] = None
    timestamp_state: Optional[float] = None
    timestamp_screenshot: Optional[float] = None
    
    def update_mc_state(self, observation_data: str):
        """从 observation JSON 字符串更新状态"""
        import json
        
        try:
            obs_list = json.loads(observation_data)
            # 找到最后一个 "observe" 事件
            observe_event = None
            for event_type, event_data in obs_list:
                if event_type == "observe":
                    observe_event = event_data
                    break
            
            if not observe_event:
                print("[Warning] No observe event found")
                return
            
            # 提取状态数据
            status = observe_event.get("status", {})
            inventory = observe_event.get("inventory", {})
            voxels = observe_event.get("voxels", {})
            visible_blocks = observe_event.get("visibleBlocks", [])
            chests = observe_event.get("chests", {})
            
            self.mc_state = MCState(
                biome=status.get("biome"),
                time_of_day=status.get("timeOfDay"),
                health=status.get("health"),
                hunger=status.get("food"),
                position=status.get("position"),
                equipment=status.get("equipment"),
                entities=status.get("entities"),
                yaw=status.get("yaw"),
                pitch=status.get("pitch"),
                nearby_items=status.get("nearbyItems"),
                inventory=inventory,
                inventory_used=status.get("inventoryUsed"),
                nearby_blocks=voxels.get("surrounding_blocks") if isinstance(voxels, dict) else voxels,
                visible_blocks=visible_blocks,
                chests=chests,
                raw_observation=observe_event,
            )
        except Exception as e:
            print(f"[Error] Failed to parse observation: {e}")
    
    def render_state(self) -> str:
        if not self.mc_state:
            return "状态: 未知\n"

        mc = self.mc_state
        last_lines = [f"### 游戏状态"]
        last_lines.append(f"位置: ({math.floor(mc.position['x'])},{math.floor(mc.position['y'])},{math.floor(mc.position['z'])})" if mc.position else "位置: 未知")
        last_lines.append(f"生命: {mc.health}/20, 饥饿: {mc.hunger}/20")

        newyaw = mc.yaw
        if newyaw < 0:
            newyaw += 2 * math.pi

        last_lines.append(f"我当前正看向 偏航角 yaw:{mc.yaw}, 俯仰角 pitch:{mc.pitch}")

        if mc.pitch < -math.pi / 4:
            last_lines.append("目前我正在朝下看")
        if mc.pitch > math.pi / 4:
            last_lines.append("目前我正在朝上看")

        if mc.inventory:
            items = [f"{n}x{c}" for n, c in mc.inventory.items()]
            last_lines.append(f"物品: {', '.join(items)}")
        last_lines = '\n'.join(last_lines) + '\n'
        return last_lines
    
    async def render_state_for_prompt(self, vision: bool) -> str:
        call_time_ms = int(time.time() * 1000)

        timeout = 60.0
        elapsed = 0.0
        poll_interval = 0.1
        while elapsed < timeout:
            if self.timestamp_state and int(self.timestamp_state.timestamp() * 1000) >= call_time_ms:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        if elapsed >= timeout:
            print(f"⚠️ [Warning] render_llm_context: 等待最新状态超时 ({timeout}s)，将使用当前缓存的数据。")

        if not self.mc_state:
            return "当前状态: 未知\n"

        mc = self.mc_state
        lines = [f"### 当前游戏状态"]
        lines.append(f"位置: ({mc.position['x']},{mc.position['y']},{mc.position['z']})" if mc.position else "位置: 未知")
        lines.append(f"生命: {mc.health}/20, 饥饿: {mc.hunger}/20")
        if vision:
            lines.append(f"可见的方块: {mc.visible_blocks}")
        lines.append(f"附近的掉落物: {mc.nearby_items}")

        newyaw = mc.yaw
        if newyaw < 0:
            newyaw += 2 * math.pi

        lines.append(f"我当前正看向 偏航角 yaw:{mc.yaw}, 俯仰角 pitch:{mc.pitch}")

        if mc.pitch < -math.pi / 4:
            lines.append("目前我正在朝下看")
        if mc.pitch > math.pi / 4:
            lines.append("目前我正在朝上看")

        if mc.inventory:
            items = [f"{n}x{c}" for n, c in mc.inventory.items()]
            lines.append(f"物品: {', '.join(items)}")
        lines = '\n'.join(lines) + '\n'
        return lines

    async def wait_for_image(self):
        call_time_ms = int(time.time() * 1000)
        timeout = 60.0
        elapsed = 0.0
        poll_interval = 0.1
        while elapsed < timeout:
            if self.timestamp_screenshot and int(self.timestamp_screenshot.timestamp() * 1000) >= call_time_ms:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        if elapsed >= timeout:
            print(f"⚠️ [Warning] render_llm_context: 等待最新截图超时 ({timeout}s)，将使用当前缓存的数据。")

# 感觉暂时用不上这个。
# class Decision(BaseModel):
#     """Capability 做出的决策"""
#     type: str # "talk", "code_run_request", "stop"
#     content: Any
#     reason: str
#     blocking: bool = False
#     wait_for_task_id: Optional[str] = None # 如果需要等待某个长任务结束
