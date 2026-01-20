import sys
import os
import time
from datetime import datetime
from dotenv import load_dotenv

# 确保能导入项目模块
sys.path.append(os.getcwd())

try:
    from agent.long_memory import MemoryCapability
    from agent.schema import Event
except ImportError:
    print("❌ 错误: 找不到 agent 模块。请确保你在项目根目录下运行此脚本。")
    sys.exit(1)

load_dotenv()

# --- 颜色代码 ---
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"
MAGENTA = "\033[95m"

def main():
    print(f"{CYAN}="*60)
    print(" 🧠 实时读写记忆测试工具 (Store & Retrieve)")
    print(f"={RESET}"*60)

    try:
        mem_cap = MemoryCapability()
        print(f"✅ 初始化成功! 当前记忆总数: {GREEN}{mem_cap.collection.count()}{RESET}")
    except Exception as e:
        print(f"{RED}❌ 初始化失败: {e}{RESET}")
        return

    print(f"\n{YELLOW}💡 机制: 你的输入会先作为【检索词】寻找旧记忆，随后作为【新记忆】存入数据库。{RESET}")
    print(f"{YELLOW}   输入 'q' 退出。{RESET}")
    print("-" * 60)

    while True:
        try:
            # 1. 用户输入
            user_input = input(f"\n{CYAN}你 (User): {RESET}").strip()
            
            if not user_input:
                continue
            if user_input.lower() in ['q', 'quit', 'exit']:
                break

            # ---------------------------------------------------
            # 步骤 A: 检索 (Retrieval)
            # ---------------------------------------------------
            start_time = time.time()
            results = mem_cap.retrieve(user_input, k=3)
            search_duration = (time.time() - start_time) * 1000

            print(f"\n{MAGENTA}💡 [记忆联想] (Top 3，耗时 {search_duration:.1f}ms):{RESET}")
            if not results:
                print(f"   {RED}📭 脑子里没有相关印象。{RESET}")
            else:
                for i, content in enumerate(results):
                    # 截断太长的文本以便显示
                    display_text = content if len(content) < 150 else content[:147] + "..."
                    print(f"   {YELLOW}[{i+1}]{RESET} {display_text}")

            # ---------------------------------------------------
            # 步骤 B: 存储 (Storage)
            # ---------------------------------------------------
            # 将用户的输入构造为一个 Event 对象
            new_event = Event(
                type="chat",
                content=user_input,
                source="user",
                timestamp=datetime.now(),
                metadata={"user": "Tester"}
            )
            
            # 存入数据库
            mem_cap.add_event(new_event)
            print(f"{GREEN}💾 [动作] 该句话已作为新记忆存入。总记忆数: {mem_cap.collection.count()}{RESET}")
            print("-" * 60)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"{RED}⚠️ 发生错误: {e}{RESET}")

    print("\n👋 记忆测试结束。")

if __name__ == "__main__":
    main()