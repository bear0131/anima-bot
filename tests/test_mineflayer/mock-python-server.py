#!/usr/bin/env python3
"""
Anima-Bot JS端测试工具

用途：
    启动一个临时的 WebSocket Server，模拟 Python 后端
    让 anima-bot 的 Node.js 端连接上来，然后可以发送测试指令

用法：
    # 1. 先启动这个测试服务器
    python test-anima-bot.py

    # 2. 然后在另一个终端启动 anima-bot
    cd anima-bot/mineflayer
    node index.js

    # 3. 在测试服务器中输入指令
"""

import asyncio
import json
import sys
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn


# ANSI 颜色代码
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_success(msg):
    print(f"{Colors.OKGREEN}✓{Colors.ENDC} {msg}")


def print_error(msg):
    print(f"{Colors.FAIL}✗{Colors.ENDC} {msg}")


def print_info(msg):
    print(f"{Colors.OKCYAN}ℹ{Colors.ENDC} {msg}")


def print_warning(msg):
    print(f"{Colors.WARNING}⚠{Colors.ENDC} {msg}")


class AnimaBotTestServer:
    """Anima-Bot 测试服务器"""

    def __init__(self, host="localhost", port=8000):
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False
        self.app = FastAPI()
        self.setup_routes()

    def setup_routes(self):
        """设置路由"""
        @self.app.websocket("/ws/minecraft")
        async def websocket_endpoint(websocket: WebSocket):
            self.websocket = websocket
            self.connected = True

            await websocket.accept()
            print_success(f"Anima-Bot 已连接!")
            print_info("输入 'help' 查看可用命令\n")

            try:
                while True:
                    # 接收消息
                    data = await websocket.receive_json()
                    await self.handle_message(data)
            except WebSocketDisconnect:
                print_error("连接已断开")
                self.connected = False
            except Exception as e:
                print_error(f"错误: {e}")
                self.connected = False

    async def handle_message(self, data):
        """处理收到的消息"""
        source = data.get('source', 'unknown')
        msg_type = data.get('type', 'unknown')

        # 格式化输出
        if source == 'minecraft':
            if msg_type == 'chat':
                user = data.get('user', 'system')
                content = data.get('content', '')
                print(f"{Colors.OKBLUE}[聊天]{Colors.ENDC} {Colors.BOLD}{user}{Colors.ENDC}: {content}")
            elif msg_type == 'code_run_result':
                error = data.get('error')
                if error:
                    print_error(f"代码执行失败: {error}")
                else:
                    print_success("代码执行成功")
                    content = data.get('content', '')
                    if content:
                        print(f"  输出: {content[:200]}")
            else:
                pass
                # print(f"{Colors.OKCYAN}[{msg_type}]{Colors.ENDC} {json.dumps(data, ensure_ascii=False)[:100]}")
        else:
            print(f"{Colors.WARNING}[其他]{Colors.ENDC} {json.dumps(data, ensure_ascii=False)[:100]}")

    async def send_chat(self, message):
        """发送聊天消息"""
        if not self.connected:
            print_error("未连接到 Anima-Bot")
            return False

        command = {
            "target": "minecraft",
            "type": "chat",
            "payload": message
        }
        await self.websocket.send_json(command)
        print_info(f"发送聊天: {message}")
        return True

    async def send_code(self, code):
        """发送执行代码命令"""
        if not self.connected:
            print_error("未连接到 Anima-Bot")
            return False

        command = {
            "target": "minecraft",
            "type": "code_run_request",
            "payload": code
        }
        await self.websocket.send_json(command)
        print_info(f"发送代码: {code[:60]}...")
        return True

    async def run_test_file(self, filepath):
        """运行测试文件"""
        path = Path(filepath)
        if not path.exists():
            print_error(f"文件不存在: {filepath}")
            return False

        code = path.read_text(encoding='utf-8')
        print_info(f"运行测试文件: {filepath}")
        return await self.send_code(code)

    async def run_test_suite(self, suite_dir):
        """运行测试套件"""
        suite_path = Path(suite_dir)
        if not suite_path.exists():
            print_error(f"测试目录不存在: {suite_dir}")
            return

        test_files = list(suite_path.glob("*.js"))
        if not test_files:
            print_warning(f"没有找到测试文件 (*.js) 在 {suite_dir}")
            return

        print_info(f"运行测试套件: {len(test_files)} 个测试")

        for i, test_file in enumerate(sorted(test_files), 1):
            print(f"\n{Colors.BOLD}测试 {i}/{len(test_files)}: {test_file.name}{Colors.ENDC}")
            await self.run_test_file(test_file)

            # 等待执行完成
            await asyncio.sleep(3)

        print(f"\n{Colors.OKGREEN}测试套件完成{Colors.ENDC}")

    async def interactive_mode(self):
        """交互式命令行"""
        print("\n" + "="*60)
        print(f"{Colors.BOLD}🎮 Anima-Bot 测试控制台{Colors.ENDC}")
        print("="*60)
        print(f"  {Colors.OKGREEN}code <JavaScript代码>{Colors.ENDC}     - 执行代码")
        print(f"  {Colors.OKGREEN}file <路径>{Colors.ENDC}                - 运行测试文件")
        print(f"  {Colors.OKGREEN}suite <目录>{Colors.ENDC}               - 运行测试套件")
        print(f"  {Colors.OKGREEN}chat <消息>{Colors.ENDC}                - 发送聊天")
        print(f"  {Colors.OKGREEN}help{Colors.ENDC}                       - 显示帮助")
        print(f"  {Colors.OKGREEN}quit{Colors.ENDC}                       - 退出")
        print("="*60 + "\n")

        # 获取当前事件循环
        loop = asyncio.get_running_loop()

        while True:
            try:
                # =========================================================
                # [关键修改] 使用 run_in_executor 把阻塞的 input 扔到线程池
                # 这样主线程的 EventLoop 依然可以处理 WebSocket 数据
                # =========================================================
                prompt = f"{Colors.BOLD}👉 {Colors.ENDC}"
                cmd_input = await loop.run_in_executor(None, input, prompt)
                
                cmd_input = cmd_input.strip()

                if not cmd_input:
                    continue

                parts = cmd_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if command in ['quit', 'exit', 'q']:
                    print_info("退出测试服务器")
                    break

                elif command == 'help':
                    self.show_help()

                elif command == 'code':
                    if args:
                        await self.send_code(args)
                    else:
                        print_error("用法: code <JavaScript代码>")

                elif command == 'file':
                    if args:
                        await self.run_test_file(args)
                    else:
                        print_error("用法: file <文件路径>")

                elif command == 'suite':
                    if args:
                        await self.run_test_suite(args)
                    else:
                        print_error("用法: suite <目录路径>")

                elif command == 'chat':
                    if args:
                        await self.send_chat(args)
                    else:
                        print_error("用法: chat <消息>")

                else:
                    print_error(f"未知命令: {command}")
                    print("输入 'help' 查看可用命令")

            except (EOFError, KeyboardInterrupt):
                print("\n")
                break

    def show_help(self):
        """显示帮助信息"""
        print(f"\n{Colors.BOLD}可用命令:{Colors.ENDC}\n")
        print(f"  {Colors.OKGREEN}code await mineBlock(bot, 'oak_log', 3){Colors.ENDC}")
        print(f"    - 执行 JavaScript 代码\n")
        print(f"  {Colors.OKGREEN}file test-script.js{Colors.ENDC}")
        print(f"    - 运行测试文件\n")
        print(f"  {Colors.OKGREEN}suite tests/{Colors.ENDC}")
        print(f"    - 运行测试套件目录中的所有 .js 文件\n")
        print(f"  {Colors.OKGREEN}chat Hello World{Colors.ENDC}")
        print(f"    - 发送聊天消息\n")
        print(f"  {Colors.OKGREEN}quit{Colors.ENDC}")
        print(f"    - 退出测试服务器\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Anima-Bot JS端测试服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用步骤:
  1. 启动测试服务器: python test-anima-bot.py
  2. 启动 anima-bot: node anima-bot/mineflayer/index.js
  3. 在测试服务器中输入命令进行测试

示例命令:
  code await mineBlock(bot, 'oak_log', 3)
  file test-script.js
  suite tests/
  chat Hello
        """
    )

    parser.add_argument('--host', default='localhost',
                       help='服务器地址 (默认: localhost)')
    parser.add_argument('--port', type=int, default=8000,
                       help='服务器端口 (默认: 8000)')

    args = parser.parse_args()

    server = AnimaBotTestServer(args.host, args.port)

    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}Anima-Bot 测试服务器{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"\n{Colors.BOLD}启动 WebSocket Server{Colors.ENDC}")
    print(f"  地址: {Colors.OKCYAN}ws://{args.host}:{args.port}{Colors.ENDC}")
    print(f"  路径: {Colors.OKCYAN}/ws/minecraft{Colors.ENDC}")
    print(f"\n{Colors.WARNING}等待 Anima-Bot 连接...{Colors.ENDC}")
    print(f"{Colors.WARNING}(在另一个终端运行: node anima-bot/mineflayer/index.js){Colors.ENDC}\n")

    # 在后台运行交互模式，同时运行服务器
    async def run_server_and_interactive():
        # 启动 uvicorn 服务器（不阻塞）
        config = uvicorn.Config(server.app, host=args.host, port=args.port, log_level="error")
        server_instance = uvicorn.Server(config)

        # 创建服务器任务
        server_task = asyncio.create_task(server_instance.serve())

        # 运行交互模式
        await server.interactive_mode()

        # 交互模式结束后，关闭服务器
        server_instance.should_exit = True
        await server_task

    try:
        asyncio.run(run_server_and_interactive())
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}服务器已停止{Colors.ENDC}")


if __name__ == "__main__":
    main()