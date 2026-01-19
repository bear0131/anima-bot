from pydantic import BaseModel
from typing import Optional, Any, Dict, Literal

# 1. 从 Node.js 发给 Python 的消息格式
class IncomingEvent(BaseModel):
    source: str       # "minecraft"
    type: str         # "chat", "spawn", "death", "error", "observation", "screenshot"
    content: Any      # 具体的文本或数据
    metadata: Optional[Dict] = {}

# 2. 从 Python 发给 Node.js 的指令格式
class OutgoingCommand(BaseModel):
    target: str       # "minecraft"
    type: Literal["chat", "code_run_request", "get_observation"]  # 新增类型
    payload: Any      # 要说的话，或者要执行的代码字符串，或者 None