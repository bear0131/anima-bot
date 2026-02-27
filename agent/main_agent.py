import asyncio
import json
import os
import time
import uuid
import openai
from openai import AsyncOpenAI
from typing import AsyncGenerator, Dict, Any, Optional, List
from dotenv import load_dotenv
from agent.memory import Memory
from agent.tools.coding_tool import CodingTool
from agent.clean_content import remove_think_tags

load_dotenv()

# 模块级全局变量：存储最近的 LLM 请求（避免类重新定义时丢失数据）
_llm_requests: List[Dict] = []
_max_requests: int = 20

def get_llm_requests() -> List[Dict]:
    """获取 LLM 请求历史（全局函数）"""
    return _llm_requests.copy()

class MainAgent:
    _max_requests = 20  # 保留类变量用于实例访问

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

    def _save_llm_request(self, messages: List[Dict], response: Dict, latency: float):
        """保存 LLM 请求到历史记录"""
        global _llm_requests
        request_id = str(uuid.uuid4())

        try:
            # 格式化响应
            formatted_response = {
                "content": response.choices[0].message.content or "",
                "tool_calls": []
            }
            if response.choices[0].message.tool_calls:
                for tc in response.choices[0].message.tool_calls:
                    formatted_response["tool_calls"].append({
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    })

            request_data = {
                "id": request_id,
                "timestamp": time.time(),
                "model": self.chat_model,
                "messages": messages,
                "response": formatted_response,
                "latency": latency
            }

            # 添加到列表开头
            _llm_requests.insert(0, request_data)

            # 限制数量
            if len(_llm_requests) > _max_requests:
                _llm_requests.pop()
        except Exception as e:
            print(f"[ERROR] Failed to save LLM request: {e}")
            import traceback
            traceback.print_exc()

    async def think_stream(self, memory: Memory) -> AsyncGenerator[Dict[str, Any], None]:
        """
        主思考单次调用：
        1. 从 memory 渲染完整上下文
        2. 调用 LLM (带计时)
        3. 处理 tool calls 或 文本回复
        """
        # 构建初始上下文：system prompt + 历史（不含图片）
        conversation_context = [{"role": "system", "content": self.chat_system_prompt}]
        history_messages = memory.render_llm_context(include_image=True)
        conversation_context.extend(history_messages)

        # 检查 last_event (逻辑保持不变)
        last_event = memory.get_last_event()
        if last_event and last_event.type == "chat":
            pass

        # [新增] 1. 开始计时
        start_time = time.time()

        # 调用 LLM（单次调用，不循环）

        max_retries = 3
        retry_delay = 5 # 秒

        print(f"messages: ")
        for mp in conversation_context[1:-1]:
            print(f"role: {mp["role"]}")
            print(f"content: {mp["content"]}")
        for attempt in range(max_retries):
            try:
                # === 原有的 API 调用代码 ===
                response = await self.client.chat.completions.create(
                    model=self.chat_model,
                    messages=conversation_context,
                    tools=self._get_tools_definition(),
                    temperature=0.8,
                    max_tokens=10000,
                )
                break
                # =========================

            except openai.InternalServerError as e:
                error_msg = str(e)
                # 检测是不是 "正在加载" 这种错误
                if "正在加载" in error_msg or "Loading" in error_msg:
                    print(f"⚠️ 模型正在加载中 (Attempt {attempt+1}/{max_retries})... 等待 {retry_delay} 秒后重试")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2 # 指数退避，下次多等一会
                else:
                    # 如果是其他严重的服务器错误，也建议重试几次
                    print(f"⚠️ 服务器内部错误 (500): {e} - Retrying...")
                    await asyncio.sleep(retry_delay)
            
            except openai.APIConnectionError as e:
                print(f"⚠️ 网络连接错误: {e} - Retrying...")
                await asyncio.sleep(retry_delay)

            except Exception as e:
                # 其他未预料的错误，直接抛出，不重试
                print(f"❌ 严重错误: {e}")
                raise e
        

        # 结束计时并计算延迟
        end_time = time.time()
        latency = end_time - start_time

        # 保存 LLM 请求记录
        self._save_llm_request(conversation_context, response, latency)

        message = response.choices[0].message
        print(f"\n{'='*60}")
        print(f"[Main Agent] 🤖 LLM 响应 (耗时: {latency:.2f}s):") # [修改] 打印耗时
        if message.content:
            print(f"  📝 文本回复: {remove_think_tags(message.content)}")
        if message.tool_calls:
            print(f"  🔧 工具调用: {len(message.tool_calls)} 个")
            for tc in message.tool_calls:
                print(f"     - {tc.function.name}: {tc.function.arguments}")
        print(f"{'='*60}\n")

        # 如果有文本回复，先 yield 给用户
        if message.content:
            yield {
                "type": "chat",
                "content": remove_think_tags(message.content),
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
                    print(f"calling task: {task_description}")
                    code_result = await self.coding_tool.generate_code(
                        task_description=task_description,
                        memory=memory
                    )
                    
                    # [可选] 如果你也想在代码生成的返回中包含之前的 LLM 思考延迟，可以加进去
                    # code_result["llm_latency"] = latency 

                    # yield code run request
                    yield code_result

            # 注意：这里不再继续调用 LLM，直接返回

    def _get_tools_definition(self) -> List[Dict[str, Any]]:
        # ... (保持不变)
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