
import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
)

response = client.chat.completions.create(
    model="gemini-3-flash-preview",
    messages=[
        {   "role": "system",
            "content": "You are a helpful assistant."
        },
        {
            "role": "user",
            "content": "你会用 mineflayer 写 bot 代码吗，你不依赖 setcontrolstate 和 pathfinder 写一个向前走一格的代码"
        }
    ]
)

print(response.choices[0].message.content)