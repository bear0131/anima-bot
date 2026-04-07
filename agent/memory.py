from collections import deque
from typing import List, Dict, Optional
import json
import asyncio
import time
from datetime import datetime
import dotenv
import os
import copy

from agent.schema import Event, AgentState, MemoryNode

dotenv.load_dotenv()
bot_username = dotenv.get_key('.env', 'BOT_USERNAME') or 'animabot'
world_name = dotenv.get_key('.env', 'WORLD_NAME') or 'default_world'

class ChatMemory:
    def __init__(self, agent_state: AgentState, llm_client, model_name: str):
        self.state = agent_state
        self.llm_client = llm_client # 需要传入 LLM 客户端用于重构记忆
        self.model_name = model_name
        self.initial_time = int(datetime.now().timestamp())
        self.running_time = 0

        self.memory_dir = os.path.join('memory', world_name)
        self.memory_file = os.path.join(self.memory_dir, 'memory_chat.json')
        os.makedirs(self.memory_dir, exist_ok=True)

        prompts_dir = os.getenv("PROMPT_PATH", "agent/prompts")
        prompt_path = os.path.join(prompts_dir, "chat_memory.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_instruction = f.read()

        # --- 配置参数 ---
        self.level1_limit = 5       # Level 1 容量 (原汁原味的 Event)
        self.consolidate_batch = 5  # 每积累多少条新 Event 触发一次 Level 2 重构
        self.level2_limit = 150       # Level 2 最大保留条数 (Pruning 阈值)
        self.min_importance = 5     # Level 2 最小重要性阈值，低于此直接删除

        # --- Level 1: 短期工作记忆 ---
        self.level1_events: deque[Event] = deque(maxlen=self.level1_limit)

        # --- Level 2: 长期语义记忆 ---
        self.level2_nodes: List[MemoryNode] = []
        self._load_memory() # 启动时加载记忆

        # --- 缓冲区: 用于积累待重构的 Event ---
        self.consolidation_buffer: List[Event] = []

        # 锁: 防止重构时并发写入导致数据错乱
        self.lock = asyncio.Lock()
    
    def get_last_event(self) -> Optional[Event]:
        """
        获取 Level 1 (短期工作记忆) 中的最后一个事件。
        通常用于 Brain 判断当前 tick 发生了什么，或者用于 Capability 检查触发条件。
        """
        # level1_events 是一个 deque，[-1] 就是最新加入的那条
        return self.level1_events[-1] if self.level1_events else None

    def add_event(self, event: Event):
        """
        添加事件。
        1. 过滤垃圾事件。
        2. 加入 Level 1 (Deque)。
        3. 加入缓冲区，如果满则触发 Level 2 重构。
        """
        _event = copy.copy(event)
        if _event.type != "task_done":
            _event.content = _event.content + '\n' + self.state.render_state()
        # 2. 加入 Level 1 (供 ChatContext 实时使用)
        self.level1_events.append(_event)

        # 3. 加入缓冲区 (供 Level 2 重构使用)
        self.consolidation_buffer.append(_event)

        # 4. 检查是否需要触发 Level 2 重构
        if len(self.consolidation_buffer) >= self.consolidate_batch:
            # 触发异步重构，不要阻塞主线程
            asyncio.create_task(self._reconstruct_level2())

    def _load_memory(self):
        """从文件加载 Level 2 记忆。"""
        if not os.path.exists(self.memory_file):
            print("No memory file found. Starting with a fresh memory.")
            return
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # 检查是否是新的字典格式
                if isinstance(data, dict) and 'running_time' in data and 'nodes' in data:
                    self.running_time = data['running_time']
                    nodes_data = data['nodes']
                    print(f"[Memory] Loaded running_time: {self.running_time}")
                else:
                    # 兼容旧的列表格式
                    print("[Memory][WARNING] Invalid memory format (expected dict with 'running_time' and 'nodes').")
                    nodes_data = []
                
                self.level2_nodes = [MemoryNode(**node_data) for node_data in nodes_data]
                print(f"🧠 Loaded {len(self.level2_nodes)} memories from {self.memory_file}")
        except (json.JSONDecodeError, TypeError) as e:
            print(f"[Memory][ERROR] Error loading memory file: {e}. Starting with a fresh memory.")
            self.level2_nodes = []

    def _save_memory(self):
        """将当前 Level 2 记忆保存到文件。"""
        try:
            
            data_to_save = {
                'running_time': self.running_time + int(datetime.now().timestamp()) - self.initial_time,
                'nodes': [node.model_dump() for node in self.level2_nodes]
            }

            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"❌ Failed to save memory: {e}")

    async def _reconstruct_level2(self):
        """
        【核心】重构 Level 2 记忆。
        LLM 读取 (Level 2 + Buffer) -> 输出 (New Level 2)
        """
        async with self.lock:
            if not self.consolidation_buffer:
                return
            
            # 1. 准备输入数据
            current_memories = [
                {"id": n.id, "content": n.content, "importance": n.importance, "time": n.time} 
                for n in self.level2_nodes
            ]
            
            new_events_text = ""
            for e in self.consolidation_buffer:
                sender = e.metadata.get('user', e.source)
                event_time = int(e.timestamp.timestamp()) - self.initial_time + self.running_time
                new_events_text += f"[{e.type}] {sender}: {e.content} at time {event_time}\n"

            # 2. 清空缓冲区
            self.consolidation_buffer.clear()

            # --- 修改开始：拆分 Prompt ---
            
            # A. 系统指令 (System Prompt) - 只有指令和格式
            
            # B. 用户数据 (User Prompt) - 只有数据
            user_data = f"""
            ### Current Knowledge Base (Level 2 Memory):
            {json.dumps(current_memories, ensure_ascii=False, indent=2)}

            ### Recent Events (New Information):
            {new_events_text}
            
            Please consolidate these memories now.
            """

            try:
                if not self.llm_client:
                    print("⚠️ No LLM client provided for memory consolidation.")
                    return

                # C. 发送请求 (包含 system 和 user)
                response = await self.llm_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        # Gemini 建议将 System Instruction 放在第一条 User 消息中，或者使用专门的参数
                        {"role": "user", "content": f"SYSTEM: {self.system_instruction}\n\nDATA: {user_data}"}
                    ],
                    response_format={"type": "json_object"} 
                )
                
                content = response.choices[0].message.content

                #print("content: ", content)

                result = json.loads(content)
                
                # --- 修改开始：更稳健的 JSON 解析逻辑 ---
                
                raw_list = []
                
                # 情况 1: LLM 直接返回了列表 (e.g. [{"content":...}, ...])
                if isinstance(result, list):
                    raw_list = result
                
                # 情况 2: LLM 返回了字典 (e.g. {"memories": [...]})
                elif isinstance(result, dict):
                    # 尝试从常见 Key 中提取，如果没有就取第一个值
                    raw_list = result.get("memories") or result.get("nodes")
                    if not raw_list:
                        # 最后的兜底：取字典里的第一个 value
                        first_value = next(iter(result.values()), [])
                        if isinstance(first_value, list):
                            raw_list = first_value
                
                # 安全检查：确保 raw_list 确实是列表
                if not isinstance(raw_list, list):
                    print(f"⚠️ Memory consolidation warning: LLM output format unexpected: {type(result)}")
                    raw_list = []

                # --- 修改结束 ---

                new_nodes = []

                for item in raw_list:
                    # 有时候 LLM 可能会生成字符串而不是对象，做个防御
                    if not isinstance(item, dict):
                        continue
                        
                    text = item.get("content")
                    time = item.get("time", int(datetime.now().timestamp()) - self.initial_time)
                    score = float(item.get("importance", 50))
                    
                    if score < self.min_importance:
                        continue 

                    node = MemoryNode(
                        content=text,
                        importance=score,
                        time=time
                    )
                    new_nodes.append(node)

                new_nodes.sort(key=lambda x: x.importance, reverse=True)
                self.level2_nodes = new_nodes[:self.level2_limit]

                self._save_memory()

                print(f"🧠 [Memory Consolidation] Refactored Level 2. Count: {len(self.level2_nodes)}")

            except Exception as e:
                print(f"❌ Memory consolidation failed: {e}")

    async def render_llm_context(self, include_image=True) -> List[Dict]:

        messages = []

        # --- 1. Level 2 记忆 (原本是 System) ---
        if self.level2_nodes:
            sorted_nodes = sorted(self.level2_nodes, key=lambda x: x.importance, reverse=True)
            memory_text = "### 🧠 Long-term Knowledge (Summarized)\n"
            for node in sorted_nodes:
                memory_text += f"- {node.content} (Imp: {node.importance}, Time: {node.time})\n"
            # 转化规则：System 内容并入后续的第一条 User 消息，或标记为 User
            messages.append({"role": "user", "content": memory_text})
        level1_events = self.level1_events.copy()
        last_id = -1
        for i in range(len(level1_events)):
            if level1_events[i].type == "task_done":
                if last_id != -1:
                    level1_events[last_id].content = level1_events[last_id].content[-1]
                last_id = i
        # --- 2. Level 1 事件流 ---
        for event in level1_events:
            if event.type == 'bot_chat':
                messages.append({"role": "assistant", "content": event.content})
            elif event.type == 'user_chat':
                username = event.metadata.get('user', 'unknown')
                messages.append({"role": "user", "content": f"[Chat] {username}: {event.content}"})
                
            elif event.type == "tool_call":
                messages.append({"role": "assistant", "content": f"[Mission Start] {event.content}"})
                
            elif event.type == "task_done":
                messages.append({"role": "assistant", "content": f"[Mission Log Start ->] {event.content} [<- Mission Log End]"})

        # --- 3. 游戏状态 (原本是 System) ---
        # 转化规则：并入最后一条 User 消息
        state_prompt = await self.state.render_state_for_prompt(vision=True)

        # 检查最后一条消息是否为 user，如果是则合并，如果不是则新建
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] += f"\n{state_prompt}"
        else:
            messages.append({"role": "user", "content": state_prompt})

        await self.state.wait_for_image()        

        # --- 4. 图像内容 ---
        if include_image and self.state.last_screenshot_front:
            img_msg_front = {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "前方的视野:"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{self.state.last_screenshot_front}",
                            "detail": "low"
                        }
                    }
                ]
            }
            messages.append(img_msg_front)

        return messages

# --------------------------------------------------------------------------------------------------------

class CodeMemory:
    def __init__(self, agent_state: AgentState, llm_client, model_name: str):
        self.state = agent_state
        self.llm_client = llm_client
        self.model_name = model_name

        self.memory_dir = os.path.join('memory', world_name)
        self.memory_file = os.path.join(self.memory_dir, 'memory_code.json')
        os.makedirs(self.memory_dir, exist_ok=True)

        prompts_dir = os.getenv("PROMPT_PATH", "agent/prompts")
        prompt_path = os.path.join(prompts_dir, "code_memory.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_instruction = f.read()

        # --- 配置参数 ---
        self.level2_limit = 20
        self.min_importance = 5

        # --- Level 1: 短期工作记忆 ---
        # 取消容量限制，改为普通列表
        self.level1_events: List[Event] = []

        # --- Level 2: 长期语义记忆 ---
        self.level2_nodes: List[MemoryNode] = []
        self._load_memory()

        # 锁: 防止重构时并发写入导致数据错乱
        self.lock = asyncio.Lock()

    def get_last_event(self) -> Optional[Event]:
        """
        获取 Level 1 中最后一个事件。
        """
        return self.level1_events[-1] if self.level1_events else None

    async def add_event(self, event: Event):
        """
        添加事件到 Level 1。
        不再自动触发长期记忆重构。
        """
        _event = copy.copy(event)
        if type(_event.content) == dict:
            _event.content["state"] = self.state.render_state()
        else:
            _event.content = _event.content + '\n' + self.state.render_state()
        self.level1_events.append(_event)

    def _load_memory(self):
        """从文件加载 Level 2 记忆。"""
        if not os.path.exists(self.memory_file):
            print("No memory file found. Starting with a fresh memory.")
            return
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.level2_nodes = [MemoryNode(**node_data) for node_data in data]
                print(f"🧠 Loaded {len(self.level2_nodes)} memories from {self.memory_file}")
        except (json.JSONDecodeError, TypeError) as e:
            print(f"❌ Error loading memory file: {e}. Starting with a fresh memory.")
            self.level2_nodes = []

    def _save_memory(self):
        """将当前 Level 2 记忆保存到文件。"""
        try:
            data_to_save = [node.model_dump() for node in self.level2_nodes]
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"❌ Failed to save memory: {e}")

    async def refresh_memory(self):
        """
        主动刷新长期记忆。
        外部可显式调用这个接口。

        参数:
            events: 指定要用于重构的事件列表。
                    如果不传，则默认使用全部 level1_events。
        """
        async with self.lock:
            target_events = list(self.level1_events)
            self.level1_events.clear()

            if not target_events:
                print("Warning: No events to consolidate.")
                return

            current_memories = [
                {"id": n.id, "content": n.content, "importance": n.importance}
                for n in self.level2_nodes
            ]

            new_events_text = ""
            for e in target_events:
                sender = e.metadata.get('user', e.source) if getattr(e, "metadata", None) else e.source
                new_events_text += f"[{e.type}] {sender}: {e.content}\n"

            user_data = f"""
            ### Current Knowledge Base (Level 2 Memory):
            {json.dumps(current_memories, ensure_ascii=False, indent=2)}

            ### Recent Events (New Information):
            {new_events_text}
            
            Please consolidate these memories now.
            """

            try:
                if not self.llm_client:
                    print("⚠️ No LLM client provided for memory consolidation.")
                    return
                print("memory refresh begin")

                response = await self.llm_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "user", "content": f"SYSTEM: {self.system_instruction}\n\nDATA: {user_data}"}
                    ],
                    response_format={"type": "json_object"}
                )
                print("memory refresh get response")

                content = response.choices[0].message.content
                result = json.loads(content)

                raw_list = []

                if isinstance(result, list):
                    raw_list = result
                elif isinstance(result, dict):
                    raw_list = result.get("memories") or result.get("nodes")
                    if not raw_list:
                        first_value = next(iter(result.values()), [])
                        if isinstance(first_value, list):
                            raw_list = first_value

                if not isinstance(raw_list, list):
                    print(f"⚠️ Memory consolidation warning: LLM output format unexpected: {type(result)}")
                    raw_list = []

                new_nodes = []

                for item in raw_list:
                    if not isinstance(item, dict):
                        continue

                    text = item.get("content")
                    if not text:
                        continue

                    try:
                        score = float(item.get("importance", 50))
                    except (TypeError, ValueError):
                        score = 50

                    if score < self.min_importance:
                        continue

                    node = MemoryNode(
                        content=text,
                        importance=score
                    )
                    new_nodes.append(node)

                new_nodes.sort(key=lambda x: x.importance, reverse=True)
                self.level2_nodes = new_nodes[:self.level2_limit]

                self._save_memory()
                print(f"🧠 [Memory Refresh] Refactored Level 2. Count: {len(self.level2_nodes)}")

            except Exception as e:
                print(f"❌ Memory refresh failed: {e}")

    async def render_llm_context(self, include_image=True) -> List[Dict]:
        messages = []

        if self.level2_nodes:
            sorted_nodes = sorted(self.level2_nodes, key=lambda x: x.importance, reverse=True)
            memory_text = "### 🧠 Long-term Knowledge (Summarized)\n"
            for node in sorted_nodes:
                memory_text += f"- {node.content} (Imp: {node.importance})\n"
            messages.append({"role": "user", "content": memory_text})

        event_list = deque(maxlen=6)

        for event in self.level1_events:
            if event.type == "tool_call":
                messages.append({"role": "assistant", "content": f"[Mission Start] {event.content}"})

            elif event.type == "code_run_request":
                event_list.append(event)

            elif event.type in ["code_run_result", "error"]:
                event_list.append(event)
        
        for event in event_list:
            if event.type == "code_run_request":
                messages.append({"role": "assistant", "content": f"[Action Start] {event.content}"})

            elif event.type in ["code_run_result", "error"]:
                messages.append({"role": "user", "content": f"[{event.type.upper()}] {event.content}"})

        state_prompt = await self.state.render_state_for_prompt(vision=True)

        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] += f"\n{state_prompt}"
        else:
            messages.append({"role": "user", "content": state_prompt})
        

        await self.state.wait_for_image()

        if include_image and self.state.last_screenshot_front:
            img_msg_front = {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "前方的视野:"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{self.state.last_screenshot_front}",
                            "detail": "low"
                        }
                    }
                ]
            }
            messages.append(img_msg_front)

        return messages
    
    def render_return_llm_context(self) -> List[Dict]:
        messages = []

        for event in self.level1_events:
            if event.type == "code_run_request":
                messages.append({"role": "assistant", "content": f"[Action Start] {event.content}"})

            elif event.type in ["code_run_result", "error"]:
                messages.append({"role": "user", "content": f"[{event.type.upper()}] {event.content}"})

        return messages