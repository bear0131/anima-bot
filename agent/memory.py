from collections import deque
from typing import List, Dict, Optional
import json
import asyncio
import time
from datetime import datetime
import dotenv
import os

from agent.schema import Event, AgentState, MemoryNode

dotenv.load_dotenv()
bot_username = dotenv.get_key('.env', 'BOT_USERNAME') or 'animabot'

class Memory:
    def __init__(self, agent_state: AgentState, llm_client, model_name: str):
        self.state = agent_state
        self.llm_client = llm_client # 需要传入 LLM 客户端用于重构记忆
        self.model_name = model_name

        # --- 配置参数 ---
        self.level1_limit = 50       # Level 1 容量 (原汁原味的 Event)
        self.consolidate_batch = 50  # 每积累多少条新 Event 触发一次 Level 2 重构
        self.level2_limit = 150       # Level 2 最大保留条数 (Pruning 阈值)
        self.min_importance = 10     # Level 2 最小重要性阈值，低于此直接删除

        # --- Level 1: 短期工作记忆 ---
        self.level1_events: deque[Event] = deque(maxlen=self.level1_limit)

        # --- Level 2: 长期语义记忆 ---
        self.level2_nodes: List[MemoryNode] = []

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
        # 1. 过滤：code_run_request 包含大量代码，且通常紧接着 code_run_result，可以不记
        if event.type == "code_run_request":
            return

        # 2. 加入 Level 1 (供 ChatContext 实时使用)
        self.level1_events.append(event)

        # 3. 加入缓冲区 (供 Level 2 重构使用)
        self.consolidation_buffer.append(event)

        # 4. 检查是否需要触发 Level 2 重构
        if len(self.consolidation_buffer) >= self.consolidate_batch:
            # 触发异步重构，不要阻塞主线程
            asyncio.create_task(self._reconstruct_level2())

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
                {"id": n.id, "content": n.content, "importance": n.importance} 
                for n in self.level2_nodes
            ]
            
            new_events_text = ""
            for e in self.consolidation_buffer:
                sender = e.metadata.get('user', e.source)
                new_events_text += f"[{e.type}] {sender}: {e.content}\n"

            # 2. 清空缓冲区
            self.consolidation_buffer.clear()

            # --- 修改开始：拆分 Prompt ---
            
            # A. 系统指令 (System Prompt) - 只有指令和格式
            system_instruction = """
            You are the objective memory archivist for a Minecraft Bot.
            
            ### CORE OBJECTIVES:
            1. **CHAT**: Retain key user instructions and conversation context.
            2. **NON-CHAT** (Actions/Logs): Record ONLY factual states with future utility. 
               - **NO EVALUATIONS**: DO NOT use subjective adjectives (e.g., "excellent", "failed", "smart", "good"). DO NOT interpret capabilities (e.g., never write "Bot showed replaceability"). 
               - **FACTS ONLY**: Write exactly what happened (e.g., "Crafted a diamond sword", "Found a village at 100,200", "Died by Zombie").
            3. **MERGE**: Aggressively collapse repetitive events into a single entry. 
               - Bad: [Node 1: Mined iron, Node 2: Mined iron]
               - Good: [Node 1: Mined iron deposits]
            4. **PRUNE**: Discard routine navigation logs or temporary errors unless they indicate a permanent blocker.

            ### FORMAT RULES:
            - **Style**: Use concise, telegraphic English (Subject-Verb-Object).
            - **Output**: Return strictly valid JSON with no markdown formatting.
            - **Structure**: {"memories": [{"content": "string", "importance": 0-100}]}
            """

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
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_data} # <--- 这里加上了 user 消息，解决了报错
                    ],
                    response_format={"type": "json_object"} 
                )
                
                content = response.choices[0].message.content

                print("content: ", content)

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
                current_time = datetime.now().timestamp()

                for item in raw_list:
                    # 有时候 LLM 可能会生成字符串而不是对象，做个防御
                    if not isinstance(item, dict):
                        continue
                        
                    text = item.get("content")
                    score = float(item.get("importance", 50))
                    
                    if score < self.min_importance:
                        continue 

                    node = MemoryNode(
                        content=text,
                        importance=score,
                        last_updated=current_time
                    )
                    new_nodes.append(node)

                new_nodes.sort(key=lambda x: x.importance, reverse=True)
                self.level2_nodes = new_nodes[:self.level2_limit]

                print(f"🧠 [Memory Consolidation] Refactored Level 2. Count: {len(self.level2_nodes)}")

            except Exception as e:
                print(f"❌ Memory consolidation failed: {e}")

    def render_llm_context(self, include_image=True) -> List[Dict]:
        """
        渲染 Context 给 Chat LLM。
        结构：Level 2 (Summary) -> Level 1 (Raw Events) -> MC State
        """
        messages = []

        # --- 层级 2: 长期语义记忆 (精炼后的知识) ---
        if self.level2_nodes:
            # 按重要性排序展示
            sorted_nodes = sorted(self.level2_nodes, key=lambda x: x.importance, reverse=True)
            memory_text = "### 🧠 Long-term Knowledge (Summarized)\n"
            for node in sorted_nodes:
                memory_text += f"- {node.content} (Imp: {node.importance})\n"
            print("memory text: ", memory_text)
            messages.append({"role": "system", "content": memory_text})

        # --- 层级 1: 短期工作记忆 (原始 Event 流) ---
        # 这里不需要 System 前缀，直接当作对话历史
        for event in self.level1_events:
            if event.type == "chat":
                if event.source == 'bot':
                    messages.append({"role": "assistant", "content": event.content})
                else:
                    username = event.metadata.get('user', 'unknown')
                    messages.append({"role": "user", "content": f"[Chat] {username}: {event.content}"})

            elif event.type == "code_run_request":
                messages.append({"role": "assistant", "content": f"[Action Start] {event.content}"})
            
            elif event.type == "code_run_result":
                # 结果可以保留，作为近期操作的反馈
                messages.append({"role": "system", "content": f"[Action Result] {event.content}"})
            
            elif event.type == "error":
                messages.append({"role": "system", "content": f"[Error] {event.content}"})
            
            # code_run_request 已经被 filter 掉了，不会出现在这里

        # --- 游戏状态 (保持不变) ---
        messages.append({"role": "system", "content": self.render_state_for_prompt()})

        # =================================================================================
        # 🟢 [新增] 调试输出：在添加图片前打印纯文本 Context
        # =================================================================================
        if os.getenv("DEBUG_LLM_CONTEXT", "false").lower() == "true":
            print("\n" + "="*50)
            print("🔍 [DEBUG] LLM Context Messages (Pre-Visual):")
            # 使用 json.dumps 格式化打印，方便查看结构
            try:
                print(json.dumps(messages, ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"Error printing debug context: {e}")
                print(messages)
            print("="*50 + "\n")
        # =================================================================================


        # --- 视觉 (保持不变) ---
        if include_image and self.state.last_screenshot:
            print("add image!")
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

    # ... render_state_for_prompt 保持不变 ...
    def render_state_for_prompt(self) -> str:
        # (直接复制之前的代码即可)
        if not self.state.mc_state:
            return "当前状态: 未知\n"
        mc = self.state.mc_state
        lines = [f"### 当前游戏状态"]
        lines.append(f"位置: {mc.position}" if mc.position else "位置: 未知")
        lines.append(f"生命: {mc.health}/20, 饥饿: {mc.hunger}/20")
        if mc.inventory:
            items = [f"{n}x{c}" for n, c in mc.inventory.items()]
            lines.append(f"物品: {', '.join(items)}")
        return '\n'.join(lines) + '\n'