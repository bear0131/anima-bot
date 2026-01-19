import os
import chromadb
import pandas as pd  # 如果没有安装 pandas，代码里有备用显示方案
from datetime import datetime

# 设置 pandas 显示选项，防止内容被截断（如果你装了 pandas）
try:
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_colwidth', 50)
    pd.set_option('display.width', 1000)
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

def inspect_db():
    db_path = "./memory_db"
    
    if not os.path.exists(db_path):
        print(f"❌ 错误: 找不到数据库文件夹 {db_path}")
        return

    print(f"📂 正在读取数据库: {db_path} ...")

    # 1. 连接数据库
    client = chromadb.PersistentClient(path=db_path)
    
    # 2. 获取集合 (Collection)
    try:
        # 注意：这里不需要提供 embedding_function，因为我们只读文本，不计算向量
        collection = client.get_collection("long_term_memory")
    except Exception as e:
        print(f"❌ 无法读取集合: {e}")
        print("可能原因：数据库是空的，或者集合名称不对。")
        return

    # 3. 获取所有数据
    # include=['metadatas', 'documents'] 表示我们只看元数据和文本，不看那一长串的向量数字
    data = collection.get(include=['metadatas', 'documents'])
    
    count = len(data['ids'])
    print(f"✅ 成功连接！当前共有 {count} 条记忆。\n")

    if count == 0:
        print("📭 数据库是空的。")
        return

    # 4. 格式化数据以便展示
    rows = []
    for i in range(count):
        meta = data['metadatas'][i]
        doc = data['documents'][i]
        doc_id = data['ids'][i]
        
        # 把数据整理成一行
        row = {
            "ID (前8位)": doc_id[:8],
            "来源": meta.get("source", "N/A"),
            "类型": meta.get("type", "N/A"),
            "内容 (Content)": doc,
            "权重 (W)": f"{meta.get('base_weight', 0):.1f}", # 注意：这是存入时的基准，动态权重是算出来的
            "出现次数": meta.get("occur_num", 0),
            "Tick (创建/访问)": f"{meta.get('created_at_tick')}/{meta.get('last_accessed_tick')}"
        }
        rows.append(row)

    # 5. 打印输出
    if HAS_PANDAS:
        df = pd.DataFrame(rows)
        # 按 Tick 倒序排列，看最新的
        if "Tick (创建/访问)" in df.columns:
             # 简单的排序可能因为字符串格式不太准，但够用了
             pass 
        print(df)
    else:
        # 如果没装 pandas，用普通文本打印
        print("-" * 80)
        for r in rows:
            print(f"ID: {r['ID (前8位)']} | [{r['来源']}]")
            print(f"内容: {r['内容 (Content)']}")
            print(f"状态: 次数={r['出现次数']}, Tick={r['Tick (创建/访问)']}")
            print("-" * 80)

if __name__ == "__main__":
    inspect_db()