import os
import json
import openai
import asyncio
import time
from openai import AsyncOpenAI
from typing import Dict, Any
from agent.memory import CodeMemory
from agent.clean_content import remove_think_tags
from agent.logger import get_logger
from agent.schema import Event, AgentState

logger = get_logger("core")

class CodingTool:
    """
    Coding Tool - 生成 Minecraft JavaScript 代码
    被主 agent 通过 tool call 调用，直接返回代码（不 yield）
    """

    def __init__(self, agent_state: AgentState, core_event_queue: asyncio.Queue):
        prompts_dir = os.getenv("PROMPT_PATH", "agent/prompts")
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        self.primitives_dir = os.path.join(
            current_file_dir, "../../mineflayer/control_primitives_context"
        )

        prompt_path = os.path.join(prompts_dir, "coding_system.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self._system_template = f.read()

        self._programs_context = self._load_control_primitives([
            "smeltItem", "killMob"
        ])

        self.agent_state = agent_state
        self.client = AsyncOpenAI(
            base_url=os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model_name = os.getenv("CODING_MODEL_NAME", "gpt-4o-2024-08-06")
        self.core_event_queue = core_event_queue

        self.llm_client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )

        # 获取用于记忆整理的模型名称
        self.memory_model = os.getenv("MEMORY_MODEL_NAME")
        self.memory = CodeMemory(
            agent_state=self.agent_state,
            llm_client=self.llm_client,
            model_name=self.memory_model
        )

        self.running_time = 0
        self.running_count = 0
        self.task_id = 0

    def _load_control_primitives(self, primitive_names) -> str:
        """加载控制原语代码"""
        programs = []
        for name in primitive_names:
            path = os.path.join(self.primitives_dir, f"{name}.js")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    programs.append(f.read())
        return "\n\n".join(programs)

    async def receive_result(self, event: Event, first_time=False):

        task_description = ""
        if first_time:
            task_description = f"总任务: {event.metadata['main_goal']}\n请基于此生成代码，直到完成总任务。"
        else:
            task_description = f"总任务: {event.metadata['main_goal']}\n上次返回的结果: {event.content}\n\n请基于此继续生成代码，直到完成总任务。"
        self.running_count += 1
        if time.time() - self.running_time > 60:
            task_description += "\n\n⚠️ 注意：距离上次返回已经超过60秒了"
        elif self.running_count > 5:
            task_description += "\n\n⚠️ 注意：距离上次返回已经轮询5次了"

        if first_time:
            await self.memory.add_event(Event(
                source='user',
                type='tool_call',
                content=event.content
            ))
        else:
            await self.memory.add_event(Event(
                source='coding_tool',
                type='code_run_result',
                content=event.content
            ))

        if event.metadata["task_id"] != self.task_id:
            logger.warning(f"Received result for task_id {event.metadata['task_id']} but current task_id is {self.task_id}, ignoring...")
            return

        code, plan = await self.generate_code(task_description)
        
        await self.memory.add_event(Event(
            type="code_run_request",
            content={
                "plan": plan,
                "code": code
            },
            source="coding_tool",
            metadata={"main_goal": event.metadata["main_goal"]},
        ))

        if code == "":
            return_context = self.memory.render_return_llm_context()
            return_context.append({"role": "assistant", "content": f"[Mission End] {plan}"})
            asyncio.create_task(self.memory.refresh_memory())
            return_event = Event(
                type="task_done",
                content=return_context,
                source="coding_tool"
            )
        else:
            return_event = Event(
                type="code_run_request",
                content=code,
                source="coding_tool",
                metadata={"task_id": event.metadata["task_id"], "main_goal": event.metadata["main_goal"]},
            )
        
        await self.core_event_queue.put(return_event)
            
    async def tool_call(self, event: Event):

        await self.interrupt() # TODO

        async with self.memory.lock:
            pass
        self.task_id += 1
        task_event = event
        task_event.metadata["task_id"] = self.task_id
        task_event.metadata["main_goal"] = event.content

        self.running_time = time.time()
        self.running_count = 0

        await self.receive_result(task_event, first_time=True)


    async def interrupt(self):
        # TODO: implement interrupt
        pass

    async def generate_code(self, task_description: str) -> tuple[str, str]:
        """
        生成 Minecraft JavaScript 代码

        Args:
            task_description: 任务描述（从 tool call 参数传入）
            memory: 记忆对象（用于获取游戏状态和上下文）

        Returns:
            Dict with type="code_run_request", content, reason, metadata
        """
        # 准备 system prompt
        system_content = self._system_template

        # 准备用户消息
        messages = [{"role": "system", "content": system_content}]
        history_messages = await self.memory.render_llm_context()
        messages.extend(history_messages)
        messages.append({"role": "user", "content": f"### 任务\n{task_description}\n\n请生成相应的 JavaScript 代码。"})

        
        #print(f"coding_tool messages: ")
        #for mp in history_messages[:-1]:
        #    print(f"role: {mp["role"]}")
        #    s = "\n".join(line for line in mp["content"].splitlines() if '可见的方块' not in line)
        #    print(f"content: {s}")

        max_retries = 3
        retry_delay = 5 # 秒

        for _ in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    timeout=10.0,
                    #reasoning_effort="low",
                )
                print("token: ", response.usage.total_tokens)
                break
            except openai.APIConnectionError as e:
                print(f"⚠️ 网络连接错误: {e} - Retrying...")
                await asyncio.sleep(retry_delay)

        try:
            result_json = json.loads(remove_think_tags(response.choices[0].message.content))
            code = result_json.get("code", "")
            plan = result_json.get("plan", "")
        except Exception as e:
            code = "// 解析失败\n" + str(e)
            plan = f"JSON 解析错误: {str(e)}"
        print(f"\n{'='*60}")
        print(f"[Coding Tool] 💻 生成的代码:")
        print(f"  📋 计划: {plan}")
        print(f"  📜 代码:\n{code}")
        print(f"{'='*60}\n")

        return code, plan
    