import os
import uuid
import json
import logging
from typing import List, Tuple, Any, Dict, Optional
from datetime import datetime

# 向量数据库依赖
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from openai import OpenAI  # 使用官方 OpenAI 客户端

# 系统依赖
from dotenv import load_dotenv
from agent.capabilities.base import Capability
from agent.schema import Event

load_dotenv()

class ParateraEmbeddingFunction(EmbeddingFunction):
    """
    自定义 Embedding 函数，通过 Paratera 接口调用 GLM-Embedding-3
    """
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.client = OpenAI(
            api_key=api_key, 
            base_url=base_url
        )
        self.model_name = model_name

    def __call__(self, input: Documents) -> Embeddings:
        # 移除换行符以提升 Embedding 质量
        input = [text.replace("\n", " ") for text in input]
        
        try:
            response = self.client.embeddings.create(
                input=input,
                model=self.model_name
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            # 简单的错误打印，防止 silent fail
            print(f"Error generating embedding: {e}")
            raise e


class MemoryCapability():
    def __init__(self):
        # 1. 初始化配置参数
        self.logger = logging.getLogger("MemoryCapability")
        
        self.max_capacity = int(os.getenv("MEMORY_MAX_CAPACITY", 10000))
        self.prune_batch_size = 100
        
        # 权重衰减参数
        self.decay_base = 0.9995
        self.decay_resistance = 0.5
        self.global_tick = 0 

        # 2. 初始化 ChromaDB
        db_path = os.getenv("MEMORY_DB_PATH", "./memory_db")
        self.client = chromadb.PersistentClient(path=db_path)
        
        # 3. 初始化 Embedding Function (Paratera / GLM-3)
        # 直接复用 OPENAI_API_KEY
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set!")

        # 你的测试代码中使用的是这个 URL
        base_url = os.getenv("OPENAI_EMBEDDING_BASE_URL")
        model_name = os.getenv("EMBEDDING_MODEL_NAME")
        
        self.ef = ParateraEmbeddingFunction(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name
        )
        
        # 初始化 Collection
        self.collection = self.client.get_or_create_collection(
            name="long_term_memory",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"}
        )

        # 恢复 tick
        if self.collection.count() > 0:
            self.global_tick = self.collection.count()

    # --- 核心功能 1: 存储 ---
    def add_event(self, event: Event):
        print("add event: ", event)
        self.global_tick += 1
        current_tick = self.global_tick

        if self.collection.count() >= self.max_capacity:
            self._prune_memory()

        content_str = self._serialize_event_content(event)
        
        metadata = {
            "type": event.type,
            "source": event.source,
            "created_at_tick": current_tick,
            "last_accessed_tick": current_tick,
            "occur_num": 1,
            "base_weight": 100,
            "raw_timestamp": event.timestamp.isoformat()
        }

        mem_id = str(uuid.uuid4())
        
        self.collection.add(
            documents=[content_str],
            metadatas=[metadata],
            ids=[mem_id]
        )

    # --- 核心功能 2: 提取 ---
    def retrieve(self, query: str, k: int = 3) -> List[str]:
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )

        retrieved_contents = []
        ids_to_update = []
        metadatas_to_update = []
        
        if results['ids'] and results['ids'][0]:
            ids_list = results['ids'][0]
            docs_list = results['documents'][0]
            metas_list = results['metadatas'][0]

            for i, doc_id in enumerate(ids_list):
                content = docs_list[i]
                meta = metas_list[i]
                
                retrieved_contents.append(content)
                
                # 更新访问数据
                new_occur = meta.get("occur_num", 0) + 1
                meta["occur_num"] = new_occur
                meta["last_accessed_tick"] = self.global_tick
                
                ids_to_update.append(doc_id)
                metadatas_to_update.append(meta)

        if ids_to_update:
            self.collection.update(
                ids=ids_to_update,
                metadatas=metadatas_to_update
            )

        return retrieved_contents

    # --- 内部逻辑 ---
    def _calculate_weight(self, last_tick: int, occur_num: int) -> float:
        delta_time = self.global_tick - last_tick
        if delta_time <= 0:
            return 100.0
        
        base_loss = 1.0 - self.decay_base
        actual_loss = base_loss / (1 + self.decay_resistance * occur_num)
        retention_rate = 1.0 - actual_loss
        
        weight = 100.0 * (retention_rate ** delta_time)
        return weight

    def _prune_memory(self):
        all_data = self.collection.get(include=["metadatas"])
        if not all_data["ids"]:
            return

        candidates = []
        ids = all_data["ids"]
        metas = all_data["metadatas"]

        for i, doc_id in enumerate(ids):
            meta = metas[i]
            last_tick = meta.get("last_accessed_tick", 0)
            occur_num = meta.get("occur_num", 1)
            w = self._calculate_weight(last_tick, occur_num)
            candidates.append({"id": doc_id, "weight": w})

        candidates.sort(key=lambda x: x["weight"])
        ids_to_delete = [item["id"] for item in candidates[:self.prune_batch_size]]
        
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)

    def _serialize_event_content(self, event: Event) -> str:
        parts = []
        prefix = f"[{event.source.upper()}] "
        parts.append(prefix)
        if isinstance(event.content, str):
            parts.append(event.content)
        elif isinstance(event.content, dict):
            parts.append(json.dumps(event.content, ensure_ascii=False))
        else:
            parts.append(str(event.content))
        return "".join(parts)