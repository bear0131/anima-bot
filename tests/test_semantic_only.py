import sys
import os
import shutil
import time
from datetime import datetime
from dotenv import load_dotenv

# 确保能导入 agent 模块
sys.path.append(os.getcwd())

try:
    from agent.capabilities.memory import MemoryCapability
    from agent.schema import Event
except ImportError:
    print("❌ 找不到模块，请确保在项目根目录下运行。")
    sys.exit(1)

load_dotenv()

def run_deep_test():
    print("\n" + "="*80)
    print("🧪 Embedding 语义理解深度测试 (Dataset++ | Top-3)")
    print("="*80)

    # 1. 强制清理环境
    db_path = os.getenv("MEMORY_DB_PATH", "./memory_db")
    if os.path.exists(db_path):
        try:
            shutil.rmtree(db_path)
            print(f"🧹 已清空旧数据库: {db_path}")
            time.sleep(1) 
        except Exception as e:
            print(f"⚠️ 清理失败: {e}")

    # 2. 初始化
    mem = MemoryCapability()
    
    # 3. 准备测试数据 (精心设计的“地狱级”混淆项)
    dataset = [
        # --- A. 物品存放 (颜色、位置、容器混淆) ---
        ("user", "I put the diamonds in the chest under the red bed."),
        ("user", "The redstone is in the barrel next to the red bed."), # 干扰：都有 red bed
        ("user", "The iron ingots are stored in the barrel near the furnace."),
        ("user", "I threw the useless iron pickaxe into the lava."),    # 干扰：都有 iron
        ("user", "Please put the rotten flesh in the trash can outside."),
        ("user", "The emeralds are in the green shulker box on the roof."),
        ("user", "My sword is in the chest, not the barrel."),          # 否定句测试
        
        # --- B. 人物喜好 (主语、宾语、情感混淆) ---
        ("chat", "Alice says she loves eating pumpkin pie."),
        ("chat", "Bob says he hates pumpkin pie but loves cooked porkchop."),
        ("chat", "Charlie is allergic to porkchop, he prefers bread."), # 干扰：都有 porkchop
        ("chat", "Dave thinks pumpkin pie is too sweet."),              # 干扰：对 pumpkin pie 的负面评价
        ("chat", "Alice gave Bob a golden apple."),
        ("chat", "Bob gave Alice a diamond sword."),

        # --- C. 地点坐标 (数字极为接近) ---
        ("bot", "I found a village at coordinates (100, 200)."),
        ("bot", "There is a dangerous lava pool at (100, 500)."),       # 干扰：Y轴不同
        ("bot", "The pillager outpost is at (100, 200), wait, no, that's the village."), # 纠正型干扰
        ("bot", "Our main base is located at (0, 64, 0)."),
        ("bot", "The mining shaft entrance is at (10, 64, 10)."),       # 干扰：接近 base
        ("bot", "Don't go to (999, 999), it's a wasteland."),

        # --- D. 游戏规则与指令 (因果关系) ---
        ("system", "To activate the portal, you must light the obsidian with flint and steel."),
        ("system", "If you sleep in the nether, the bed will explode."),
        ("system", "You need obsidian to build the portal frame."),     # 干扰：都有 obsidian
        ("system", "Flint and steel is used to burn trees."),           # 干扰：都有 flint and steel
        
        # --- E. 时间与状态 (新旧信息混淆) ---
        ("bot", "My current health is 20 (Full)."),
        ("bot", "Five minutes ago, my health was 2 (Critical)."),
        ("bot", "I am currently holding a diamond sword."),
        ("bot", "I used to hold a wooden shovel.")
    ]

    print(f"\n📥 正在存入 {len(dataset)} 条复杂记忆...")
    for src, content in dataset:
        mem.add_event(Event(
            type="chat", 
            content=content, 
            source=src,
            timestamp=datetime.now()
        ))
    
    print("✅ 存入完毕，开始测试 Top-3 检索...\n")

    # 4. 测试用例
    test_cases = [
        {
            "query": "Where are the diamonds?", 
            "target_keyword": "red bed",  # 核心依据
            "distractor": "barrel"        # 红石在 barrel 旁边，钻石在 chest 里面
        },
        {
            "query": "What does Bob like to eat?", 
            "target_keyword": "porkchop",
            "distractor": "pumpkin pie"   # Bob 讨厌这个
        },
        {
            "query": "Is (100, 200) safe?", 
            "target_keyword": "village",
            "distractor": "outpost"       # 只有村庄是确定的，outpost 是口误
        },
        {
            "query": "How do I light the portal?", 
            "target_keyword": "flint and steel",
            "distractor": "obsidian"      # 它是材料，不是点火工具
        },
        {
            "query": "What is my current health?", 
            "target_keyword": "20",
            "distractor": "2"             # 那是之前的血量
        }
    ]

    # 5. 执行测试
    for case in test_cases:
        print(f"🔸 提问: \"{case['query']}\"")
        print(f"   (寻找: '{case['target_keyword']}' | 需排除: '{case['distractor']}')")
        
        results = mem.retrieve(case['query'], k=3) # <--- 获取前三名
        
        if not results:
            print("   ❌ 未找到任何记忆")
            continue

        # 打印 Top 3
        found_target_in_top1 = False
        for i, res in enumerate(results):
            rank = i + 1
            is_target = case['target_keyword'].lower() in res.lower()
            is_distractor = case['distractor'].lower() in res.lower()
            
            # 格式化输出
            marker = "  "
            if is_target: 
                marker = "✅"
                if rank == 1: found_target_in_top1 = True
            elif is_distractor:
                marker = "⚠️" # 警告：这是干扰项
            
            print(f"   {marker} [Rank {rank}] {res}")

        # 评价
        if found_target_in_top1:
            print("   🌟 完美! 正确答案排第一。")
        else:
            print("   🤔 还有优化空间 (第一名不是最佳答案)。")
            
        print("-" * 60)

if __name__ == "__main__":
    run_deep_test()