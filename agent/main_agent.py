import asyncio
import json
import os
from openai import AsyncOpenAI
from typing import AsyncGenerator, Dict, Any, Optional, List
from dotenv import load_dotenv
from agent.memory import Memory
from agent.tools.coding_tool import CodingTool

load_dotenv()

class MainAgent:
    def __init__(self):
        # 加载 chat prompt
        prompts_dir = "agent/prompts"
        with open(f"{prompts_dir}/chat_system.txt", encoding="utf-8") as f:
            self.chat_system_prompt = f.read()

        self.client = AsyncOpenAI(
            base_url=os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.chat_model = os.getenv("CHAT_MODEL_NAME", "gpt-4o-mini")
        self.coding_tool = CodingTool()

    async def think_stream(self, memory: Memory) -> AsyncGenerator[Dict[str, Any], None]:
        """
        主思考单次调用：
        1. 从 memory 渲染完整上下文（包括历史对话、游戏状态等）
        2. 调用 LLM，支持 tool calls
        3. 如果有 tool call，调用 coding tool 并 yield code run request，然后立即返回
        4. 如果有文本回复，yield 后继续
        5. 不再进行多轮循环，每次调用只处理一次 LLM 响应

        注意：不再假设 last_event 一定是 chat 事件，
        调用方需要在需要时将事件添加到 memory 中
        """
        # 构建初始上下文：system prompt + 历史（不含图片）
        conversation_context = [{"role": "system", "content": self.chat_system_prompt}]
        history_messages = memory.render_llm_context(include_image=False)
        conversation_context.extend(history_messages)

        # 如果 last_event 是 chat 且还未在 history 中，需要手动添加
        # render_llm_context 已经处理了 level1_events 中的 chat，所以通常不需要额外处理
        last_event = memory.get_last_event()
        if last_event and last_event.type == "chat":
            # 检查这个 chat 事件是否已经在 history 中了
            # level1_events 包含所有短期事件，render_llm_context 会处理它们
            # 所以这里我们不需要额外添加
            pass

        # 调用 LLM（单次调用，不循环）
        response = await self.client.chat.completions.create(
            model=self.chat_model,
            messages=conversation_context,
            tools=self._get_tools_definition(),
            temperature=0.8,
            max_tokens=2000,
        )

        message = response.choices[0].message
        print(f"\n{'='*60}")
        print(f"[Main Agent] 🤖 LLM 响应:")
        if message.content:
            print(f"  📝 文本回复: {message.content}")
        if message.tool_calls:
            print(f"  🔧 工具调用: {len(message.tool_calls)} 个")
            for tc in message.tool_calls:
                print(f"     - {tc.function.name}: {tc.function.arguments}")
        print(f"{'='*60}\n")

        # 如果有文本回复，先 yield 给用户
        if message.content:
            yield {
                "type": "chat",
                "content": message.content
            }

        # 检查是否有 tool calls
        if message.tool_calls:
            # 处理所有 tool calls
            for tool_call in message.tool_calls:
                # 执行 tool call
                if tool_call.function.name == "execute_minecraft_code":
                    # 解析参数
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        task_description = arguments.get("task", "")
                    except:
                        # 如果解析失败，尝试从 last_event 获取
                        task_description = last_event.content if last_event else ""

                    # 调用 coding tool
                    code_result = await self.coding_tool.generate_code(
                        task_description=task_description,
                        memory=memory
                    )

                    # yield code run request
                    yield code_result

            # 注意：这里不再继续调用 LLM，直接返回
            # 下次调用时，memory 中已经有了 code_run_request 事件
            # 调用方（core）需要在收到 code_run_result 后再次调用 think_stream

    def _get_tools_definition(self) -> List[Dict[str, Any]]:
        """
        定义可用的工具
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "execute_minecraft_code",
                    "description": "在 Minecraft 世界中执行操作，如移动、挖矿、合成、放置方块等。当用户请求需要在游戏中执行动作时调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "需要执行的任务描述，例如：挖 10 个石头，合成一个木镐，走到坐标 (100, 64, 200)"
                            }
                        },
                        "required": ["task"]
                    }
                }
            }
        ]