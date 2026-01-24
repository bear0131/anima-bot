import asyncio
import os
import sys
import signal
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class JSProcessManager:
    """
    管理 Node.js/Mineflayer 进程的生命周期

    职责：
    - 启动/停止 JS 子进程
    - 监控进程输出
    - 检测崩溃并自动重启
    - 优雅退出处理
    """

    def __init__(
        self,
        node_path: str = "node",
        js_entry: str = "mineflayer/index.js",
        extra_args: list[str] | None = None,
        max_restarts: int = 5,
        restart_delay: float = 2.0,
        ready_timeout: float = 60.0,
    ):
        self.node_path = node_path
        self.js_entry = js_entry
        self.extra_args = extra_args or []
        self.max_restarts = max_restarts
        self.restart_delay = restart_delay
        self.ready_timeout = ready_timeout

        # 运行时状态
        self.process: Optional[asyncio.subprocess.Process] = None
        self.restart_count = 0
        self._restart_lock = asyncio.Lock()
        self._monitor_tasks: list[asyncio.Task] = []
        self._ready_event = asyncio.Event()
        self._stopping = False  # 标记是否正在主动停止/重启中（区分主动停止和意外崩溃）

    def _build_command(self) -> list[str]:
        """构建启动命令"""
        cmd = [self.node_path, self.js_entry]

        # 添加额外的命令行参数
        cmd.extend(self.extra_args)

        # 兼容旧的环境变量方式（向后兼容）
        if os.getenv("HEADLESS") == "false" and "--headless" not in str(self.extra_args):
            cmd.append("--headless=false")
        if os.getenv("PRISMARINE_VIEWER") == "false" and "--prismarine_viewer" not in str(self.extra_args):
            cmd.append("--prismarine_viewer=false")

        return cmd

    def _create_env(self) -> dict[str, str]:
        """创建子进程环境变量（继承当前进程 + .env）"""
        env = os.environ.copy()

        # 确保项目根目录在 PATH 中（用于 node 依赖查找）
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if "NODE_PATH" not in env:
            node_modules = os.path.join(project_root, "mineflayer", "node_modules")
            if os.path.exists(node_modules):
                env["NODE_PATH"] = node_modules

        return env

    async def start(self) -> None:
        """启动 JS 进程"""
        if self.process is not None:
            logger.warning("[JSManager] Process already running")
            return

        self._stopping = False  # 启动时重置标记

        cmd = self._build_command()
        env = self._create_env()

        logger.info(f"[JSManager] Starting: {' '.join(cmd)}")

        try:
            # 创建子进程
            # Windows 需要 CREATE_NEW_PROCESS_GROUP 以便能够发送信号
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = 0  # 不使用 CREATE_NEW_PROCESS_GROUP，避免信号处理问题

            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                creationflags=creation_flags,
            )

            logger.info(f"[JSManager] Process started with PID: {self.process.pid}")

            # 重置就绪事件
            self._ready_event.clear()

            # 启动输出监控任务
            self._monitor_tasks = [
                asyncio.create_task(self._read_stream(self.process.stdout, "[JS-OUT]")),
                asyncio.create_task(self._read_stream(self.process.stderr, "[JS-ERR]")),
                asyncio.create_task(self._monitor_process()),
            ]

        except Exception as e:
            logger.error(f"[JSManager] Failed to start process: {e}")
            raise

    async def _read_stream(self, stream: asyncio.StreamReader, prefix: str) -> None:
        """读取并打印子进程输出"""
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break

                decoded = line.decode("utf-8", errors="ignore").rstrip()
                print(f"{prefix} {decoded}")

                # 检测就绪标记
                if "Bot is ready" in decoded:
                    logger.info("[JSManager] Bot ready detected")
                    self._ready_event.set()

                # 检测严重错误（可以触发重启）
                if "UNCAUGHT EXCEPTION" in decoded or "CRITICAL" in decoded:
                    logger.warning(f"[JSManager] Critical error detected in output")

        except Exception as e:
            logger.error(f"[JSManager] Error reading stream: {e}")

    async def _monitor_process(self) -> None:
        """监控进程退出状态"""
        # 等待进程退出
        await self.process.wait()
        exit_code = self.process.returncode

        # 清理引用（要在判断重启逻辑之前清理，否则 restart 会以为还在运行）
        self.process = None

        # 取消流读取任务
        for task in self._monitor_tasks:
            # 排除当前任务自己（如果有的话），避免取消自身导致后面的代码不执行
            if not task.done() and task != asyncio.current_task():
                task.cancel()

        # 核心修复：自动重启逻辑
        if not self._stopping:
            logger.error(f"[JSManager] Process crashed unexpectedly with code: {exit_code}")
            logger.info(f"[JSManager] Attempting auto-restart in {self.restart_delay}s...")

            # 启动一个后台任务去执行重启，避免阻塞
            asyncio.create_task(self._trigger_restart())
        else:
            logger.info(f"[JSManager] Process stopped gracefully (Code: {exit_code})")

    async def _trigger_restart(self) -> None:
        """内部辅助方法：处理自动重启流程"""
        try:
            await asyncio.sleep(self.restart_delay)
            # 调用 restart，它内部会再次调用 start -> 再次启动监控
            await self.restart()
        except Exception as e:
            logger.error(f"[JSManager] Auto-restart failed: {e}")

    async def stop(self) -> None:
        """停止 JS 进程（优雅退出）"""
        if self.process is None:
            logger.warning("[JSManager] No process to stop")
            return

        self._stopping = True  # 告诉监控器这是主动停止
        logger.info("[JSManager] Stopping process...")

        try:
            # 尝试优雅退出（发送信号）
            if sys.platform == "win32":
                self.process.terminate()
            else:
                self.process.send_signal(signal.SIGTERM)

            # 等待最多 5 秒
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                logger.info("[JSManager] Process terminated gracefully")
            except asyncio.TimeoutError:
                logger.warning("[JSManager] Process did not exit in time, forcing kill")
                self.process.kill()
                await self.process.wait()
                logger.info("[JSManager] Process killed")

        except Exception as e:
            logger.error(f"[JSManager] Error stopping process: {e}")
            # 强制清理
            if self.process:
                self.process.kill()

        finally:
            self.process = None

    async def restart(self) -> None:
        """重启 JS 进程"""
        async with self._restart_lock:
            logger.info("[JSManager] Restarting process...")

            # 停止旧进程
            await self.stop()

            # 等待一段时间
            await asyncio.sleep(self.restart_delay)

            # 增加重启计数
            self.restart_count += 1

            if self.restart_count > self.max_restarts:
                logger.error(
                    f"[JSManager] Max restarts ({self.max_restarts}) exceeded, giving up"
                )
                raise RuntimeError("JS process restart limit exceeded")

            logger.info(f"[JSManager] Restart attempt {self.restart_count}/{self.max_restarts}")

            # 启动新进程
            await self.start()

            # 等待就绪
            await self.wait_until_ready(timeout=self.ready_timeout)

    async def is_alive(self) -> bool:
        """检查进程是否存活"""
        if self.process is None:
            return False

        # 检查退出码（None 表示仍在运行）
        return self.process.returncode is None

    async def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """
        等待 JS 端就绪

        就绪条件：
        - 输出包含 "Bot is ready"
        - 或者 WebSocket 连接建立（由 server.py 检测）

        Returns:
            是否在超时时间内就绪
        """
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
            logger.info("[JSManager] Bot is ready")
            return True
        except asyncio.TimeoutError:
            logger.error(f"[JSManager] Timeout waiting for ready (>{timeout}s)")
            return False

    async def cleanup(self) -> None:
        """清理资源（用于退出时）"""
        logger.info("[JSManager] Cleaning up...")

        # 取消所有监控任务
        for task in self._monitor_tasks:
            if not task.done():
                task.cancel()

        # 停止进程
        await self.stop()
