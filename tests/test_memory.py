import sys
import os
import time
import shutil
from datetime import datetime
from dotenv import load_dotenv

# 确保能导入 agent 模块
sys.path.append(os.getcwd())

try:
    from agent.capabilities.memory import MemoryCapability
    from agent.schema import Event
except ImportError as e:
    print("❌ 导入错误: 找不到模块。请确保你在项目根目录下运行，并且 agent 文件夹里有 __init__.py")
    print(f"详细错误: {e}")
    sys.exit(1)

# 加载环境变量
load_dotenv()

def print_header(text):
    print(f"\n{'='*60}")
    print(f"🛠️  {text}")
    print(f"{'='*60}")

def test_memory_system():
    # ---------------------------------------------------------
    # 1. 初始化
    # ---------------------------------------------------------
    print_header("初始化 MemoryCapability")
    
    # ⚠️ 为了测试纯净性，建议测试前清理掉旧数据库（可选）
    # if os.path.exists("./memory_db"):
    #     shutil.rmtree("./memory_db")
    #     print("🧹 已清理旧的数据库文件")

    try:
        mem_cap = MemoryCapability()
        print("✅ MemoryCapability 初始化成功")
        print(f"   - Embedding Model: {mem_cap.ef.model_name}")
        print(f"   - Database Path: {os.environ.get('MEMORY_DB_PATH', './memory_db')}")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return

    # ---------------------------------------------------------
    # 2. 基础存储与语义检索测试
    # ---------------------------------------------------------
    print_header("测试存储与语义检索 (Embedding 效果)")
    
    # 模拟一些游戏内的事件
    test_events = [
        ("user", "My favorite food is baked potato."),
        ("bot", "I built a small wooden house at coordinates (100, 64, -200)."),
        ("system", "The zombie dropped a rare iron carrot."),
        ("user", "Never dig straight down, it is dangerous.")
    ]

    print("📥 正在存入记忆...")
    for source, content in test_events:
        event = Event(
            type="chat" if source == "user" else "log",
            content=content,
            source=source,
            timestamp=datetime.now()
        )
        mem_cap.add_event(event)
        print(f"   - 存入: [{source}] {content}")

    print("\n🔍 正在进行语义检索...")
    
    queries = [
        ("What does the user like to eat?", "baked potato"), # 语义匹配
        ("Where is my home?", "wooden house"),               # 语义匹配
        ("mining safety advice", "dig straight down")        # 语义匹配
    ]

    for q, expected_keyword in queries:
        print(f"\n   ❓ 提问: '{q}'")
        results = mem_cap.retrieve(q, k=1)
        
        if results:
            top_result = results[0]
            print(f"   💡 回忆结果: {top_result}")
            if expected_keyword.lower() in top_result.lower():
                print("   ✅ 匹配成功")
            else:
                print(f"   ⚠️ 匹配可能不准确 (预期包含: '{expected_keyword}')")
        else:
            print("   ❌ 未找到相关记忆")
    return

    # ---------------------------------------------------------
    # 3. 权重与访问次数更新测试
    # ---------------------------------------------------------
    print_header("测试权重更新逻辑")

    # 我们无法直接从外部读取私有 metadata，但我们可以通过 hack 方式验证
    # 或者通过再次检索，理论上被检索过的记忆会保持高权重
    
    target_query = "What does the user like to eat?"
    
    # 获取该条记忆的 ID (为了验证 occur_num)
    # 这里我们直接查询 collection 内部来看状态
    results = mem_cap.collection.query(query_texts=[target_query], n_results=1)
    
    if results['metadatas'] and results['metadatas'][0]:
        meta_before = results['metadatas'][0][0]
        occur_before = meta_before.get('occur_num', 0)
        print(f"   📊 检索前 occur_num: {occur_before}")
        
        # 执行一次检索
        print(f"   🔄 执行 retrieve('{target_query}')...")
        mem_cap.retrieve(target_query, k=1)
        
        # 再次查询内部状态
        results_after = mem_cap.collection.query(query_texts=[target_query], n_results=1)
        meta_after = results_after['metadatas'][0][0]
        occur_after = meta_after.get('occur_num', 0)
        print(f"   📊 检索后 occur_num: {occur_after}")
        
        if occur_after > occur_before:
            print("   ✅ 访问计数器成功增加")
        else:
            print("   ❌ 访问计数器未增加")

    # ---------------------------------------------------------
    # 4. 容量修剪 (Pruning) 测试
    # ---------------------------------------------------------
    print_header("测试容量溢出与修剪 (Pruning)")

    # ⚠️ 强制修改实例参数以触发修剪
    mem_cap.max_capacity = 5    # 设得很小
    mem_cap.prune_batch_size = 2 # 每次删 2 个
    
    print(f"   ⚙️ 临时调整 max_capacity = {mem_cap.max_capacity}")
    print(f"   ⚙️ 当前记忆数量: {mem_cap.collection.count()}")
    
    # 填充无用数据直到溢出
    print("   📥 正在快速填充数据以触发修剪...")
    
    for i in range(10):
        # 模拟时间流逝
        mem_cap.global_tick += 10 # 这里的 delta_time 会很大，加速权重衰减
        
        event = Event(
            type="system_log", 
            content=f"Useless noise log number {i}", 
            source="system"
        )
        mem_cap.add_event(event)
        
        current_count = mem_cap.collection.count()
        print(f"      - 添加第 {i+1} 条噪音 (当前总数: {current_count})")
        
        # 如果当前数量回落，说明触发了 pruning
        if current_count <= mem_cap.max_capacity and i > 2:
             print(f"   ✂️ 触发修剪！当前数量回落至: {current_count}")

    final_count = mem_cap.collection.count()
    print(f"\n   📊 最终记忆数量: {final_count}")
    
    if final_count <= mem_cap.max_capacity:
        print("   ✅ 修剪机制工作正常 (数量控制在上限内)")
    else:
        print(f"   ❌ 修剪机制未触发或失败 (当前: {final_count}, 上限: {mem_cap.max_capacity})")
        
    # 验证重要记忆是否还在 (因为之前检索过 "food"，它的权重应该很高，不容易被删)
    print("\n   🧐 验证重要记忆是否幸存...")
    check_food = mem_cap.retrieve("food", k=1)
    if check_food and "potato" in check_food[0]:
        print("   ✅ 重要记忆 (Potato) 幸存！(权重机制生效)")
    else:
        print("   ⚠️ 重要记忆丢失 (可能被随机噪音挤掉了，或者权重衰减过快)")

if __name__ == "__main__":
    test_memory_system()