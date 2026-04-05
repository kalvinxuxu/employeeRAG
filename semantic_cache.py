"""
语义缓存 (Semantic Cache) - 基于向量相似度的问题缓存系统

功能:
- 使用向量相似度判断问题是否已回答过
- 如果新问题的语义与缓存中的问题高度相似，直接返回缓存结果
- 避免重复请求大模型，显著降低响应时间

用法:
    cache = SemanticCache(similarity_threshold=0.95)

    # 尝试从缓存获取
    cached = cache.get(user_query)
    if cached:
        return cached.answer  # 直接返回缓存答案

    # 调用 LLM 生成答案
    answer = call_llm(query, context)

    # 保存到缓存
    cache.set(user_query, answer, context)
"""

import os
import json
import hashlib
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import chromadb
from chromadb.api.types import EmbeddingFunction


@dataclass
class CacheEntry:
    """缓存条目"""
    question: str                    # 原始问题
    answer: str                      # 缓存的答案
    context_hash: str                # 上下文的哈希
    created_at: datetime             # 创建时间
    hit_count: int = 0               # 命中次数
    embedding: Optional[List[float]] = None  # 问题的向量
    metadata: Dict = field(default_factory=dict)  # 元数据


class BGEEmbeddingFunction:
    """BGE Embedding 函数，用于语义缓存（本地模型）"""

    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        self.model_name = model_name
        self._model = None

        # 设置国内镜像源（解决 Hugging Face 连接问题）
        import os
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

    def name(self) -> str:
        """返回 embedding 函数名称，ChromaDB 要求"""
        return self.model_name

    def _get_model(self):
        """懒加载 BGE 模型"""
        if self._model is None:
            from FlagEmbedding import FlagModel
            self._model = FlagModel(
                self.model_name,
                query_instruction_for_retrieval="为这个句子生成表示以用于检索：",
                use_fp16=False
            )
        return self._model

    def __call__(self, input: list[str]) -> list[list[float]]:
        """生成 embedding"""
        model = self._get_model()
        MAX_BATCH_SIZE = 10
        all_embeddings = []

        for i in range(0, len(input), MAX_BATCH_SIZE):
            batch = input[i:i + MAX_BATCH_SIZE]
            embeddings = model.encode(batch)
            all_embeddings.extend([emb.tolist() if hasattr(emb, 'tolist') else list(emb) for emb in embeddings])

        return all_embeddings

    def embed_query(self, input: str) -> list[float]:
        """为单个查询生成 embedding"""
        model = self._get_model()
        embedding = model.encode(input)
        return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

    def embed_documents(self, documents: List[str]) -> list[list[float]]:
        """为多个文档生成 embedding"""
        return self(documents)


class SemanticCache:
    """语义缓存系统"""

    def __init__(
        self,
        cache_path: str = "./semantic_cache",
        collection_name: str = "question_cache",
        similarity_threshold: float = 0.95,
        embedding_model: str = "BAAI/bge-large-zh-v1.5",  # 中文优化 Embedding
        max_cache_size: int = 10000,
        ttl_days: Optional[int] = None,  # 缓存有效期（天），None 表示永久
    ):
        """
        初始化语义缓存

        Args:
            cache_path: 缓存数据路径
            collection_name: 集合名称
            similarity_threshold: 相似度阈值（高于此值认为问题相同）
            embedding_model: Embedding 模型
            max_cache_size: 最大缓存条目数
            ttl_days: 缓存有效期（天）
        """
        self.cache_path = cache_path
        self.collection_name = collection_name
        self.similarity_threshold = similarity_threshold
        self.embedding_model = embedding_model
        self.max_cache_size = max_cache_size
        self.ttl_days = ttl_days

        self._client = None
        self._collection = None
        self._embedding_func = None

        # 内存缓存（加速频繁访问）
        self._memory_cache: Dict[str, CacheEntry] = {}

    def _get_client(self):
        """懒加载 ChromaDB 客户端"""
        if self._client is None:
            self._client = chromadb.PersistentClient(path=self.cache_path)
        return self._client

    def _get_embedding_func(self):
        """懒加载 Embedding 函数"""
        if self._embedding_func is None:
            self._embedding_func = BGEEmbeddingFunction(
                model_name=self.embedding_model
            )
        return self._embedding_func

    def _get_collection(self):
        """懒加载 ChromaDB 集合"""
        if self._collection is None:
            client = self._get_client()
            embedding_func = self._get_embedding_func()

            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=embedding_func,
                metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
            )
        return self._collection

    def _compute_context_hash(self, context: str) -> str:
        """计算上下文的哈希值"""
        return hashlib.md5(context.encode()).hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """检查缓存是否过期"""
        if self.ttl_days is None:
            return False
        expiry_time = entry.created_at + timedelta(days=self.ttl_days)
        return datetime.now() > expiry_time

    def _cleanup_if_needed(self):
        """如果缓存超出大小限制，清理旧缓存"""
        collection = self._get_collection()
        current_size = collection.count()

        if current_size >= self.max_cache_size:
            # 删除最旧的 10% 缓存
            delete_count = max(1, int(self.max_cache_size * 0.1))

            # 获取最旧的条目
            all_data = collection.get(
                include=["metadatas"],
                limit=delete_count
            )

            if all_data and all_data["ids"]:
                collection.delete(ids=all_data["ids"][:delete_count])

    def get(self, question: str) -> Optional[CacheEntry]:
        """
        从缓存获取答案

        Args:
            question: 用户问题

        Returns:
            缓存条目，如果未命中则返回 None
        """
        collection = self._get_collection()

        # 查询最相似的问题
        results = collection.query(
            query_texts=[question],
            n_results=1,
            include=["documents", "metadatas", "distances"]
        )

        if not results["documents"] or not results["documents"][0]:
            return None

        # 检查相似度
        distance = results["distances"][0][0]
        similarity = 1 - distance

        if similarity < self.similarity_threshold:
            return None

        # 获取缓存条目
        metadata = results["metadatas"][0][0]
        answer = metadata.get("answer", "")  # 答案现在存在元数据里

        # 检查是否过期
        created_at = datetime.fromisoformat(metadata.get("created_at"))
        entry = CacheEntry(
            question=question,
            answer=answer,
            context_hash=metadata.get("context_hash", ""),
            created_at=created_at,
            hit_count=metadata.get("hit_count", 0) + 1,
            metadata=metadata
        )

        if self._is_expired(entry):
            return None

        # 更新命中次数
        entry.hit_count += 1
        self._update_entry(entry)

        # 更新内存缓存
        self._memory_cache[question] = entry

        return entry

    def set(self, question: str, answer: str, context: Optional[str] = None,
            metadata: Optional[Dict] = None):
        """
        保存答案到缓存

        Args:
            question: 用户问题
            answer: AI 回答
            context: 检索到的上下文（可选）
            metadata: 其他元数据
        """
        collection = self._get_collection()

        # 生成唯一 ID
        cache_id = hashlib.md5(f"{question}:{datetime.now().isoformat()}".encode()).hexdigest()
        context_hash = self._compute_context_hash(context) if context else ""

        # 保存元数据
        entry_metadata = {
            "question": question,
            "context_hash": context_hash,
            "created_at": datetime.now().isoformat(),
            "hit_count": 0,
            **(metadata or {})
        }

        # 添加到 ChromaDB
        # documents 应该是问题（用于向量搜索），答案存储在元数据中
        collection.add(
            ids=[cache_id],
            documents=[question],  # 问题用于向量搜索
            metadatas=[{**entry_metadata, "answer": answer}]  # 答案存在元数据里
        )

        # 更新内存缓存
        self._memory_cache[question] = CacheEntry(
            question=question,
            answer=answer,
            context_hash=context_hash,
            created_at=datetime.now(),
            hit_count=0,
            metadata=entry_metadata
        )

        # 清理超出大小的缓存
        self._cleanup_if_needed()

    def _update_entry(self, entry: CacheEntry):
        """更新缓存条目"""
        collection = self._get_collection()

        # 查找对应的 ID
        results = collection.peek(limit=self.max_cache_size)

        for i, meta in enumerate(results.get("metadatas", [])):
            if meta and meta.get("question") == entry.question:
                cache_id = results["ids"][i]

                # 更新元数据
                update_metadata = {
                    "hit_count": entry.hit_count,
                    "last_accessed": datetime.now().isoformat(),
                }

                collection.update(
                    ids=[cache_id],
                    metadatas=[update_metadata]
                )
                break

    def clear(self):
        """清空缓存"""
        collection = self._get_collection()
        collection.delete(where={})
        self._memory_cache.clear()

    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        collection = self._get_collection()
        total_entries = collection.count()

        # 计算平均命中次数
        all_metadata = collection.get(include=["metadatas"])
        total_hits = sum(
            meta.get("hit_count", 0)
            for meta in all_metadata.get("metadatas", [])
        )

        return {
            "total_entries": total_entries,
            "total_hits": total_hits,
            "hit_rate": total_hits / max(total_entries, 1),
            "memory_cache_size": len(self._memory_cache),
            "similarity_threshold": self.similarity_threshold,
            "max_cache_size": self.max_cache_size,
        }

    def delete_expired(self) -> int:
        """删除过期缓存，返回删除数量"""
        if self.ttl_days is None:
            return 0

        collection = self._get_collection()
        all_data = collection.get(include=["metadatas"])

        deleted_count = 0
        ids_to_delete = []

        for i, metadata in enumerate(all_data.get("metadatas", [])):
            if metadata and "created_at" in metadata:
                created_at = datetime.fromisoformat(metadata["created_at"])
                entry = CacheEntry(
                    question="",
                    answer="",
                    context_hash="",
                    created_at=created_at
                )
                if self._is_expired(entry):
                    ids_to_delete.append(all_data["ids"][i])

        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            deleted_count = len(ids_to_delete)

        return deleted_count


# ==================== 全局缓存实例 ====================

_default_cache: Optional[SemanticCache] = None


def get_cache(
    similarity_threshold: float = 0.95,
    cache_path: str = "./semantic_cache"
) -> SemanticCache:
    """获取全局语义缓存实例（单例模式）"""
    global _default_cache
    if _default_cache is None:
        _default_cache = SemanticCache(
            similarity_threshold=similarity_threshold,
            cache_path=cache_path
        )
    return _default_cache


def cached_answer(
    question: str,
    answer_generator,
    context: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    便捷函数：从缓存获取答案，如果未命中则生成并缓存

    Args:
        question: 用户问题
        answer_generator: 答案生成函数 (context) -> str
        context: 检索到的上下文

    Returns:
        (答案，是否来自缓存)
    """
    cache = get_cache()

    # 尝试从缓存获取
    cached_entry = cache.get(question)
    if cached_entry:
        return cached_entry.answer, True

    # 生成新答案
    answer = answer_generator(context)

    # 保存到缓存
    cache.set(question, answer, context)

    return answer, False
