import os
import json
import openai
import asyncio
from openai import AsyncOpenAI
from typing import Dict, Any
from agent.memory import Memory
from agent.clean_content import remove_think_tags

class CodingTool:
    """
    Coding Tool - 生成 Minecraft JavaScript 代码
    被主 agent 通过 tool call 调用，直接返回代码（不 yield）
    """

    def __init__(self):
        prompts_dir = os.getenv("PROMPT_PATH", "agent/prompts")
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        self.primitives_dir = os.path.join(
            current_file_dir, "../../mineflayer/control_primitives_context"
        )

        prompt_path = os.path.join(prompts_dir, "coding_system.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self._system_template = f.read()

        self._programs_context = self._load_control_primitives([
            "exploreUntil", "mineBlock", "craftItem",
            "placeItem", "smeltItem", "killMob"
        ])

        self.client = AsyncOpenAI(
            base_url=os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model_name = os.getenv("CODING_MODEL_NAME", "gpt-4o-2024-08-06")

    def _load_control_primitives(self, primitive_names) -> str:
        """加载控制原语代码"""
        programs = []
        for name in primitive_names:
            path = os.path.join(self.primitives_dir, f"{name}.js")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    programs.append(f.read())
        return "\n\n".join(programs)

    async def generate_code(self, task_description: str, memory: Memory) -> Dict[str, Any]:
        """
        生成 Minecraft JavaScript 代码

        Args:
            task_description: 任务描述（从 tool call 参数传入）
            memory: 记忆对象（用于获取游戏状态和上下文）

        Returns:
            Dict with type="code_run_request", content, reason, metadata
        """
        # 准备 system prompt
        system_content = self._system_template.replace("{programs}", self._programs_context)

        # 准备用户消息
        # 注意：这里不使用 render_llm_context，因为代码信息不应该进主 memory
        # 只需要当前游戏状态即可
        game_state = memory.render_state_for_prompt()

        user_content = f"""### 任务
{task_description}

### 当前游戏状态
{game_state}

请生成相应的 JavaScript 代码。"""

        max_retries = 3
        retry_delay = 5 # 秒

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_content}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    timeout=10.0, 
                    reasoning_effort="low", 
                )
                break
            except openai.APIConnectionError as e:
                print(f"⚠️ 网络连接错误: {e} - Retrying...")
                await asyncio.sleep(retry_delay)

        print(f"response: {response}")

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

        return {
            "type": "code_run_request",
            "content": code,
            "reason": plan,
            "metadata": {"source": "coding_tool"}
        }
