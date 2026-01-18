import os
from openai import AsyncOpenAI
from typing import Optional, Tuple
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
        self.model_name = os.getenv("CHAT_MODEL_NAME", "gpt-4o-mini")

    async def can_handle(self, event: IncomingEvent) -> Tuple[bool, bool]:
        can_process = event.type == "chat"
        is_exclusive = can_process
        return can_process, is_exclusive

    async def run(self, event: IncomingEvent, context: list, current_frame: Optional[str] = None) -> dict:
        """
        current_frame: Base64 字符串 (不带 data:image 前缀的话需要在这里加)
        """

        current_user = event.metadata.get("user", "Unknown")
        
        # 1. 准备当前回合的用户消息，放在 system 和 history 后
        current_turn_content = []
        
        # 如果有视觉记忆，先把图片放进去
        if current_frame:
            current_turn_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{current_frame}", # 假设是 jpeg
                    "detail": "low" # 使用 low 模式（65 tokens），仅关注大体环境
                }
            })
            # 添加一句提示，让 AI 明确这是背景信息
            current_turn_content.append({
                "type": "text",
                "text": "(System Note: The image above is your current POV.)"
            })

        # 再把用户的聊天内容放进去
        current_turn_content.append({
            "type": "text",
            "text": f"{current_user} says: {event.content}"
        })

        # 2. 组装发给 OpenAI 的完整消息列表
        # 顺序：System -> History -> Current(Image + Text)
        messages_payload = [
            {"role": "system", "content": self.system_prompt}
        ] + context + [
            {"role": "user", "content": current_turn_content}
        ]

        # 3. 调用 API
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages_payload,
            temperature=0.8,
            max_tokens=500,
        )

        reply_text = response.choices[0].message.content

        # 4. 更新历史记录 (注意！)
        # 我们**只存文本**进历史记录，不存图片 Base64，否则几次对话后内存和Token都会爆炸
        context.append({"role": "user", "content": f"{current_user}: {event.content}"})
        context.append({"role": "assistant", "content": reply_text})

        return {
            "type": "talk",
            "content": reply_text,
        }
