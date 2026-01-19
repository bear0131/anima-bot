import os
from openai import AsyncOpenAI
from typing import Optional, Tuple
from dotenv import load_dotenv
from agent.capabilities.base import Capability
from agent.schema import Event
from agent.short_memory import ShortTermMemory

load_dotenv()

class ChatCapability(Capability):
    def __init__(self):
        prompts_dir = os.getenv("PROMPT_PATH", "agent/prompts")
        prompt_path = os.path.join(prompts_dir, "persona.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

        self.client = AsyncOpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model_name = os.getenv("CHAT_MODEL_NAME", "gpt-4o-mini")

    async def can_handle(self, memory: ShortTermMemory) -> Tuple[bool, bool]:
        can_process = memory.get_last_event().type == "chat"
        is_exclusive = can_process
        return can_process, is_exclusive

    async def get_decision(
        self,
        memory: ShortTermMemory,
    ) -> dict:
        """
        处理聊天事件
        """
        # 1. 使用 memory 渲染 OpenAI 格式的消息
        messages_payload = memory.render_llm_context(
            include_image=True,
        )

        # 2. 在最前面插入 system prompt
        messages_payload = [{"role": "system", "content": self.system_prompt}] + messages_payload

        # print("\n" + "="*50)
        # print("Payload Debug - 打印完整消息内容:")
        # print("="*50)
        # for i, msg in enumerate(messages_payload):
        #     print(f"\n[消息 {i+1}]")
        #     print(f"Role: {msg['role']}")
        #     content_str = str(msg['content'])
        #     if len(content_str) > 120:
        #         content_str = content_str[:120] + "... (truncated)"
        #     print(f"Content: {content_str}")
        #     print("-" * 50)
        # print("="*50 + "\n")

        # 3. 调用 API
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages_payload,
            temperature=0.8,
            max_tokens=500,
        )

        reply_text = response.choices[0].message.content

        return {
            "type": "chat",
            "content": reply_text,
        }
