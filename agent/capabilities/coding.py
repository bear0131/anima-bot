import os
import json
import glob
from openai import AsyncOpenAI
from typing import Tuple, List, Dict
from agent.capabilities.base import Capability
from agent.short_memory import ShortTermMemory

class CodingCapability(Capability):
    def __init__(self):
        # === 1. 初始化路径 ===
        self.prompts_dir = os.getenv("PROMPT_PATH", "agent/prompts")
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        self.primitives_dir = os.path.join(
            current_file_dir, 
            "../../mineflayer/control_primitives_context"
        )
        
        # === 2. 加载 System Prompt 模板 ===
        # 假设 coding_system.txt 里有 {programs} 占位符
        prompt_path = os.path.join(self.prompts_dir, "coding_system.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self._system_template = f.read()

        # === 3. 预加载 Control Primitives (Voyager 的 JS 源码) ===
        # 这里把所有基础技能读出来，拼成一个大字符串

        # 这里硬编码了基础技能列表，和 Voyager 保持一致
        base_skills = [
            "exploreUntil", "mineBlock", "craftItem", 
            "placeItem", "smeltItem", "killMob"
        ]
        self._programs_context = self._load_control_primitives(base_skills)

        # === 4. LLM Client ===
        self.client = AsyncOpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model_name = os.getenv("CODING_MODEL_NAME", "gpt-4o-2024-08-06")

    def _load_control_primitives(self, primitive_names=None) -> str:
        """
        读取所有 .js 文件内容
        Args:
            primitive_names: 可选的原语名称列表，如果为 None 则加载所有
        Returns:
            str: 所有原语代码拼接后的字符串
        """
        programs = []

        if primitive_names is None:
            # 如果没有指定列表，则扫描目录获取所有 .js 文件
            if os.path.exists(self.primitives_dir):
                primitive_names = [
                    primitive[:-3]
                    for primitive in os.listdir(self.primitives_dir)
                    if primitive.endswith(".js")
                ]
            else:
                print(f"[Error] Primitives directory not found: {self.primitives_dir}")
                return ""

        for skill_name in primitive_names:
            path = os.path.join(self.primitives_dir, f"{skill_name}.js")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    programs.append(f.read())
            else:
                print(f"[Warn] Primitive not found: {path}")

        return "\n\n".join(programs)

    async def can_handle(self, memory: ShortTermMemory) -> Tuple[bool, bool]:
        last_event = memory.get_last_event()
        if last_event is None:
            can_process = False
        else:
            can_process = last_event.type == "chat"
        is_exclusive = False
        return can_process, is_exclusive

    async def get_decision(self, memory: ShortTermMemory) -> dict:
        """
        生成代码的核心逻辑
        """
        print("Coding receive task:", memory.get_last_event().content)

        # 1. 组装 System Prompt (填入 JS 库)
        system_content = self._system_template.replace("{programs}", self._programs_context)
        
        # 2. 组装 User Message (Voyager 的那一大堆状态)
        memory_context = memory.render_llm_context(
            include_image=False,
        )
        # 暂时不给 coding 加图片。

        # 3. 调 LLM (使用 JSON Mode)
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "system", "content": system_content}] + memory_context, 
            response_format={"type": "json_object"}, # 关键：强制 JSON
            temperature=0.0, # 写代码要严谨
        )

        result_json = json.loads(response.choices[0].message.content)

        print(f"====== return json ======\n{result_json}\n====================\n")

        # 从 LLM 响应中提取字段
        explain = result_json.get("explain", "")
        plan = result_json.get("plan", "")
        code = result_json.get("code", "")  # 修改为使用 "code" 字段

        return {
            "type": "code_run_request",
            "content": code,
            "reason": plan,
        } 