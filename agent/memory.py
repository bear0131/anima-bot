from collections import deque
from typing import List, Dict, Optional, Set
import asyncio
import dotenv

from agent.schema import Event, AgentState
# 引入 MemoryCapability 的类型提示 (如果导致循环引用可以用 TYPE_CHECKING)
from agent.long_memory import MemoryCapability

dotenv.load_dotenv()
bot_username = dotenv.get_key('.env', 'BOT_USERNAME') or 'animabot'

class Memory:
    def __init__(self, agent_state: AgentState, memory_capability: MemoryCapability, max_history=1):
        """
        Args:
            agent_state: 代理的当前状态对象
            memory_capability: 长期记忆能力的实例 (用于检索)
            max_history: 短期记忆保留的事件数量
        """
        self.events: deque[Event] = deque(maxlen=max_history)
        self.state = agent_state
        
        # 持有长期记忆能力的引用
        self.memory_capability = memory_capability
        
        # 缓存的“当前脑海中的长期记忆”
        # 它是动态变化的，随着短期记忆的变化而刷新
        self.relevant_memories: List[str] = []

    def add_event(self, event: Event):
        """
        添加事件到短期记忆。
        如果记忆已满，溢出的旧事件会自动转存到长期记忆。
        """
        # 1. 检查当前队列是否已满
        if len(self.events) >= self.events.maxlen:
            # 2. 手动弹出最旧的一个事件 (FIFO)
            oldest_event = self.events.popleft()
            
            # 3. 决定是否要存入长期记忆
            # 不是所有鸡毛蒜皮的小事都要记一辈子，这里加个过滤器
            if self._should_save_to_ltm(oldest_event):
                try:
                    # 调用 MemoryCapability 存入向量库
                    # 注意：假设 memory_capability.add_event 是同步的 (ChromaDB add 是同步的)
                    # 如果你的 add_event 是 async 的，这里需要用 asyncio.create_task 包装
                    print("add event in long memory: ", oldest_event)
                    self.memory_capability.add_event(oldest_event)
                    # print(f"💾 [Memory Transfer] Moved event to LTM: {oldest_event.content[:30]}...")
                except Exception as e:
                    print(f"⚠️ Failed to save memory to LTM: {e}")

        # 4. 将新事件加入短期记忆
        self.events.append(event)

    def _should_save_to_ltm(self, event: Event) -> bool:
        """
        [过滤器] 判断一个即将被移出短期记忆的事件，是否值得存入长期记忆。
        """
        # 策略 1: 聊天记录通常比较重要 (特别是 User 说的)
        if event.type == "chat":
            return True
        
        # 策略 2: 代码运行成功的结果可能包含重要信息（如考察环境的结果）
        if event.type == "code_run_done":
            return True
            
        # 策略 3: 视觉总结（如果你有的话）
        if event.type == "visual_summary":
            return True

        # 策略 4: 忽略系统垃圾日志、报错信息、运行请求等
        # "code_run_request" 通常只是代码，不如 result 重要
        # "system_log" 可能太琐碎
        # "error" 除非经常报错，否则不需要记太久
        return False

    def get_last_event(self) -> Optional[Event]:
        """获取最后一个事件"""
        return self.events[-1] if self.events else None 

    def refresh_relevant_memories(self):
        """
        【核心功能】主动联想
        根据短期记忆中最近的几条事件，去长期记忆库中检索相关信息。
        应该在 Brain 每次做决策前调用一次。
        """
        if not self.events:
            return

        # 1. 策略：提取最近的 1-2 条由 User 发出的 chat 或 request
        #    我们不需要每一条 log 都去检索，那太慢且会有噪音。
        #    只关注用户说了什么，或者 Bot 刚做了什么重要决定。
        queries = []
        lookback_count = 0
        max_lookback = 3 # 只看最近 3 条里的有效信息
        
        # 倒序遍历
        for event in reversed(self.events):
            if lookback_count >= max_lookback:
                break
            
            # 提取 User 的聊天内容作为检索 Query
            if event.type == "chat" and event.source != "bot":
                queries.append(event.content)
                lookback_count += 1
            
            # 也可以提取代码运行请求 (任务目标)
            elif event.type == "code_run_request":
                queries.append(event.content)
                lookback_count += 1

        if not queries:
            # 如果最近全是系统日志或Bot自言自语，保持上次的记忆或清空，这里选择保留旧的或清空皆可
            # 为了防止记忆残留干扰新话题，选择不做新检索 (保持不变) 或 清空
            # 这里选择：如果没有有效Query，就不检索了，节省资源
            return

        # 2. 执行检索 (使用 set 去重)
        combined_memories: Set[str] = set()
        
        for q in queries:
            # 调用 capability 的 retrieve (它会自动处理权重更新)
            # 每个 query 找 Top-2 即可，不用太多
            results = self.memory_capability.retrieve(query=str(q), k=2)
            for mem in results:
                combined_memories.add(mem)

        # 3. 更新缓存
        self.relevant_memories = list(combined_memories)
        
        # (可选) 打印调试信息，看看它联想到了什么
        # if self.relevant_memories:
        #     print(f"🧠 [Memory Association] Based on '{queries[0]}...', recalled: {len(self.relevant_memories)} items.")

    def render_state_for_prompt(self) -> str:
        """渲染 MC 状态为文本"""
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
        
        if mc.inventory:
            items = [f"{name}x{count}" for name, count in mc.inventory.items()]
            lines.append(f"物品栏: {', '.join(items)}")

        return '\n'.join(lines) + '\n'

    def render_llm_context(self, include_image=True) -> List[Dict]:
        """
        渲染 OpenAI 格式的上下文。
        自动包含：长期记忆(System) -> 短期记忆(History) -> 当前状态(System) -> 视觉(User)
        """
        messages = []

        # --- 1. 长期记忆注入 (自动获取 self.relevant_memories) ---
        self.refresh_relevant_memories()
        if self.relevant_memories:
            memory_text = "### 🧠 Recalled Memories (Related to current context)\n"
            for i, mem in enumerate(self.relevant_memories):
                memory_text += f"{i+1}. {mem}\n"
            
            messages.append({
                "role": "system", 
                "content": memory_text
            })

        # --- 2. 短期记忆历史 ---
        for event in self.events:
            if event.type == "chat":
                if event.source == 'bot':
                    messages.append({"role": "assistant", "content": event.content})
                else:
                    username = event.metadata.get('user', 'unknown')
                    messages.append({"role": "user", "content": f"[Chat] {username}: {event.content}"})
            elif event.type == "code_run_request":
                messages.append({"role": "system", "content": f"[System] Executing code: {event.content}"})
            elif event.type == "code_run_done":
                messages.append({"role": "system", "content": f"[System] Code finished. Result: {event.content}"})
            elif event.type == "error":
                messages.append({"role": "system", "content": f"[Error] {event.content}"})

        # --- 3. 当前状态 ---
        messages.append({"role": "system", "content": self.render_state_for_prompt()})

        # --- 4. 视觉输入 ---
        if include_image and self.state.last_screenshot:
            messages.append({
                "role": "user", 
                "content": [
                    {"type": "text", "text": "Current View:"},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{self.state.last_screenshot}",
                        "detail": "low"
                    }}
                ]
            })

        return messages