"""
统一的日志系统，支持同时输出到控制台和 WebSocket
"""
import logging
import asyncio
from datetime import datetime
from typing import Set
import json
from functools import partial


class WebSocketLogHandler(logging.Handler):
    """将日志发送到 WebSocket 客户端"""

    def __init__(self):
        super().__init__()
        self.clients: Set[asyncio.Queue] = set()
        self.loop = None

    def _get_loop(self):
        """延迟获取事件循环"""
        if self.loop is None:
            try:
                self.loop = asyncio.get_event_loop()
            except RuntimeError:
                self.loop = asyncio.new_event_loop()
        return self.loop

    def add_client(self, queue: asyncio.Queue):
        """添加一个客户端队列"""
        self.clients.add(queue)

    def remove_client(self, queue: asyncio.Queue):
        """移除一个客户端队列"""
        self.clients.discard(queue)

    def emit(self, record):
        """发送日志到所有客户端"""
        try:
            if not self.clients:
                return  # 没有客户端，不处理

            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "source": record.name,
                "message": self.format(record),
            }

            loop = self._get_loop()

            # 异步发送到所有客户端
            for queue in self.clients:
                try:
                    if loop.is_running():
                        loop.call_soon_threadsafe(
                            partial(queue.put_nowait, log_entry)
                        )
                except Exception:
                    pass  # 静默失败，避免日志系统产生错误
        except Exception:
            self.handleError(record)


# 全局 logger 实例
_ws_handler = WebSocketLogHandler()
_ws_handler.setFormatter(
    logging.Formatter('[%(name)s] %(message)s')
)

# 控制台 handler
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)


def get_logger(name: str) -> logging.Logger:
    """
    获取一个配置好的 logger

    用法:
        from agent.logger import get_logger
        logger = get_logger("core")
        logger.info("Hello world")
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if not logger.handlers:
        logger.addHandler(_console_handler)
        logger.addHandler(_ws_handler)
        logger.setLevel(logging.INFO)

    return logger


def get_ws_handler() -> WebSocketLogHandler:
    """获取 WebSocket handler，用于 server.py"""
    return _ws_handler
