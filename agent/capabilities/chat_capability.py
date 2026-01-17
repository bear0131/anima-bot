import os
from openai import AsyncOpenAI
from typing import Tuple
from dotenv import load_dotenv
from interfaces.protocol import IncomingEvent

load_dotenv()


class ChatCapability:
    def __init__(self):
        prompts_dir = os.getenv("PROMPT_PATH", "agent/prompts")
        prompt_path = os.path.join(prompts_dir, "persona.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

        self.client = AsyncOpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

    async def can_handle(self, event: IncomingEvent) -> Tuple[bool, bool]:
        can_process = event.type == "chat"
        is_exclusive = can_process
        return can_process, is_exclusive

    async def run(self, event: IncomingEvent, context: list) -> dict:
        context.append({"role": "user", "content": event.content})
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "system", "content": self.system_prompt}]+context,
            temperature=0.8,
            max_tokens=500,
        )

        content = response.choices[0].message.content
        context.append({"role": "assistant", "content": content})

        return {
            "type": "talk",
            "content": content,
        }
