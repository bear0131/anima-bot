from pydantic import BaseModel
from typing import Optional, Any, Dict, Literal

# 1. 从 Node.js 发给 Python 的消息格式
class IncomingEvent(BaseModel):
    source: str       # "minecraft"
    type: str         # "chat", "observation", "screenshot", "code_run_result"
    content: Optional[Any] = None  # 具体的文本或数据（code run done 执行成功时可省略）
    metadata: Optional[Dict] = {}
    error: Optional[str] = None  # 错误信息，None 表示无错误

# 2. 从 Python 发给 Node.js 的指令格式
class OutgoingCommand(BaseModel):
    target: str       # "minecraft"
    type: Literal["code_run_request", "get_observation", "bot_chat"]  # 指令类型
    payload: Any      # 要说的话，或者要执行的代码字符串，或者 None
    metadata: Optional[Dict] = {}  # 可选的额外信息
