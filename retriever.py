"""
混合检索器 - 向量检索 + BM25 关键词检索 + Rerank

功能:
- VectorRetriever: 基于 ChromaDB 的向量检索
- BM25Retriever: 基于 rank-bm25 的关键词检索
- HybridFusion: 结果融合（RRF 或加权）
- Reranker: BGE Reranker 重排序

用法:
    from retriever import HybridRetriever

    retriever = HybridRetriever(chroma_path="./chroma_db", api_key=api_key)
    results = retriever.retrieve(query="出差报销标准", top_k=5)
"""

import os
import json
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import math


@dataclass
class RetrieveResult:
    """检索结果"""
    text: str                   # 文本内容
    score: float                # 综合得分
    vector_score: float = 0.0   # 向量得分
    keyword_score: float = 0.0  # 关键词得分
    metadata: Dict = field(default_factory=dict)  # 元数据
    source: str = ""            # 来源：vector/keyword/fusion


class VectorRetriever:
    """向量检索器 - 基于 ChromaDB"""

    def __init__(self, chroma_path: str, collection_name: str = "legal_docs",
                 embedding_model: str = "BAAI/bge-large-zh-v1.5",
                 cache_embeddings: bool = True):
        """
        初始化向量检索器

        Args:
            chroma_path: ChromaDB 数据路径
            collection_name: 集合名称
            embedding_model: Embedding 模型（bge-large-zh-v1.5 = 1024 维，中文优化）
            cache_embeddings: 是否缓存 embedding 结果
        """
        self.chroma_path = chroma_path
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.cache_embeddings = cache_embeddings

        self._client = None
        self._collection = None
        self._embedding_func = None

        # Query embedding 缓存（避免重复计算）
        self._query_embedding_cache: Dict[str, List[float]] = {}

    def _get_collection(self):
        """懒加载 ChromaDB 集合（使用 BGE 本地模型）"""
        if self._collection is None:
            import chromadb
            from chromadb.api.types import EmbeddingFunction

            # 初始化客户端
            self._client = chromadb.PersistentClient(path=self.chroma_path)

            # BGE Embedding 函数（本地模型）
            class BGEEmbeddingFunction(EmbeddingFunction):
                def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5",
                             cache_embeddings: bool = True):
                    self.model_name = model_name
                    self.cache_embeddings = cache_embeddings
                    self._embedding_cache: Dict[str, List[float]] = {}
                    self._cache_max_size = 1000
                    self._model = None

                    # 设置国内镜像源（解决 Hugging Face 连接问题）
                    import os
                    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

                def _get_model(self):
                    """懒加载 BGE 模型"""
                    if self._model is None:
                        try:
                            from FlagEmbedding import FlagModel
                            self._model = FlagModel(
                                self.model_name,
                                query_instruction_for_retrieval="为这个句子生成表示以用于检索：",
                                use_fp16=False
                            )
                        except ImportError:
                            print("[ERROR] FlagEmbedding 未安装，BGE 模型无法加载。请运行: pip install FlagEmbedding>=1.2.0")
                            raise
                    return self._model

                def __call__(self, input: list[str]) -> list[list[float]]:
                    """生成 embedding（支持批量处理和缓存）"""
                    model = self._get_model()

                    # 从缓存获取已知的 embedding
                    cached_results = {}
                    texts_to_compute = []

                    if self.cache_embeddings:
                        for i, text in enumerate(input):
                            text_hash = hash(text)
                            if text_hash in self._embedding_cache:
                                cached_results[i] = self._embedding_cache[text_hash]
                            else:
                                texts_to_compute.append((i, text))

                        # 如果没有需要计算的，直接返回缓存结果
                        if not texts_to_compute:
                            return [cached_results[i] for i in range(len(input))]

                    # 批量计算 embedding
                    MAX_BATCH_SIZE = 25
                    all_embeddings = {}

                    # 分批次处理
                    for batch_idx in range(0, len(texts_to_compute), MAX_BATCH_SIZE):
                        batch = texts_to_compute[batch_idx:batch_idx + MAX_BATCH_SIZE]
                        batch_texts = [text for _, text in batch]

                        embeddings = model.encode(batch_texts)

                        # 存储结果并缓存
                        for local_idx, (orig_idx, text) in enumerate(batch):
                            embedding = embeddings[local_idx].tolist() if hasattr(embeddings[local_idx], 'tolist') else list(embeddings[local_idx])
                            all_embeddings[orig_idx] = embedding

                            # 缓存 embedding
                            if self.cache_embeddings and len(self._embedding_cache) < self._cache_max_size:
                                text_hash = hash(text)
                                self._embedding_cache[text_hash] = embedding

                    # 合并缓存结果和新计算的结果
                    final_results = []
                    for i in range(len(input)):
                        if i in cached_results:
                            final_results.append(cached_results[i])
                        elif i in all_embeddings:
                            final_results.append(all_embeddings[i])

                    return final_results

            self._embedding_func = BGEEmbeddingFunction(
                model_name="BAAI/bge-large-zh-v1.5",
                cache_embeddings=self.cache_embeddings
            )

            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self._embedding_func,
            )

        return self._collection

    def search(self, query: str, k: int = 10,
               filter_metadata: Optional[Dict] = None) -> List[RetrieveResult]:
        """
        向量检索

        Args:
            query: 查询文本
            k: 返回结果数量
            filter_metadata: 元数据过滤条件

        Returns:
            RetrieveResult 列表
        """
        collection = self._get_collection()

        # 构建 where 过滤条件
        where = None
        if filter_metadata:
            where = self._build_where_filter(filter_metadata)

        # 查询
        results = collection.query(
            query_texts=[query],
            n_results=k,
            include=["documents", "metadatas", "distances"],
            where=where,
        )

        # 转换为 RetrieveResult
        retrieve_results = []
        if results["documents"] and results["documents"][0]:
            for doc, metadata, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            ):
                # 距离转相似度分数
                similarity = 1 - distance

                retrieve_results.append(RetrieveResult(
                    text=doc,
                    score=similarity,
                    vector_score=similarity,
                    keyword_score=0.0,
                    metadata=metadata or {},
                    source="vector"
                ))

        return retrieve_results

    def _build_where_filter(self, filters: Dict) -> Dict:
        """
        构建 ChromaDB where 过滤条件

        Args:
            filters: 过滤条件字典

        Returns:
            ChromaDB where 格式
        """
        # 简单实现：$eq 过滤
        # 扩展：支持 $in, $ne, $gt, $lt 等
        conditions = []
        for key, value in filters.items():
            if isinstance(value, list):
                # $in 条件
                conditions.append({key: {"$in": value}})
            else:
                conditions.append({key: {"$eq": value}})

        if len(conditions) == 1:
            return conditions[0]
        elif len(conditions) > 1:
            return {"$and": conditions}
        return None


class BM25Retriever:
    """BM25 关键词检索器"""

    def __init__(self, documents: Optional[List[str]] = None,
                 language: str = "zh"):
        """
        初始化 BM25 检索器

        Args:
            documents: 文档列表（用于构建索引）
            language: 语言（zh/en）
        """
        self.documents = documents or []
        self.language = language
        self._bm25 = None
        self._doc_ids = []

        if self.documents:
            self._build_index()

    def _tokenize(self, text: str) -> List[str]:
        """
        分词

        中文使用 jieba，英文使用空格分词
        """
        if self.language == "zh":
            try:
                import jieba
                return list(jieba.cut(text))
            except ImportError:
                # jieba 不可用时，按字符分词
                return list(text)
        else:
            return text.lower().split()

    def _build_index(self):
        """构建 BM25 索引"""
        from rank_bm25 import BM25Okapi

        # 分词
        tokenized_docs = [self._tokenize(doc) for doc in self.documents]

        # 构建 BM25 模型
        self._bm25 = BM25Okapi(tokenized_docs)

    def add_documents(self, documents: List[str], doc_ids: Optional[List[str]] = None):
        """
        添加文档到索引

        Args:
            documents: 文档列表
            doc_ids: 文档 ID 列表
        """
        self.documents = documents
        self._doc_ids = doc_ids or [str(i) for i in range(len(documents))]
        self._build_index()

    def search(self, query: str, k: int = 10) -> List[RetrieveResult]:
        """
        BM25 检索

        Args:
            query: 查询文本
            k: 返回结果数量

        Returns:
            RetrieveResult 列表
        """
        if not self._bm25:
            return []

        # 分词查询
        query_tokens = self._tokenize(query)

        # 获取 BM25 分数
        scores = self._bm25.get_scores(query_tokens)

        # 获取 top-k
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:k]

        # 构建结果
        results = []
        for idx in top_indices:
            if scores[idx] > 0:  # 只返回有分数的结果
                results.append(RetrieveResult(
                    text=self.documents[idx],
                    score=scores[idx] / 10.0,  # 归一化到 0-1 范围
                    vector_score=0.0,
                    keyword_score=scores[idx] / 10.0,
                    metadata={"doc_id": self._doc_ids[idx] if idx < len(self._doc_ids) else str(idx)},
                    source="keyword"
                ))

        return results


class HybridFusion:
    """混合检索结果融合器"""

    def __init__(self, method: str = "rrf",
                 vector_weight: float = 0.5,
                 keyword_weight: float = 0.5,
                 k: int = 60):
        """
        初始化融合器

        Args:
            method: 融合方法 ("rrf" | "weighted")
            vector_weight: 向量权重 (weighted 模式)
            keyword_weight: 关键词权重 (weighted 模式)
            k: RRF 常数
        """
        self.method = method
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.k = k

    def merge(self, vector_results: List[RetrieveResult],
              keyword_results: List[RetrieveResult],
              top_k: int = 10) -> List[RetrieveResult]:
        """
        融合两个检索结果

        Args:
            vector_results: 向量检索结果
            keyword_results: 关键词检索结果
            top_k: 返回结果数量

        Returns:
            融合后的结果
        """
        if self.method == "rrf":
            return self._rrf_merge(vector_results, keyword_results, top_k)
        else:
            return self._weighted_merge(vector_results, keyword_results, top_k)

    def _rrf_merge(self, vector_results: List[RetrieveResult],
                   keyword_results: List[RetrieveResult],
                   top_k: int) -> List[RetrieveResult]:
        """
        Reciprocal Rank Fusion (RRF) 融合

        RRF 分数 = 1 / (k + rank)
        """
        # 计算 RRF 分数
        rrf_scores = {}

        # 向量结果
        for rank, result in enumerate(vector_results[:top_k * 2]):
            doc_id = id(result.text)  # 用文本内容作为唯一标识
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (self.k + rank + 1)

        # 关键词结果
        for rank, result in enumerate(keyword_results[:top_k * 2]):
            doc_id = id(result.text)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (self.k + rank + 1)

        # 合并结果并重新排序
        all_results = {}
        for result in vector_results + keyword_results:
            doc_id = id(result.text)
            if doc_id not in all_results:
                all_results[doc_id] = result

        # 设置融合分数
        for doc_id, result in all_results.items():
            result.score = rrf_scores.get(doc_id, 0)

        # 按 RRF 分数排序
        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x.score,
            reverse=True
        )

        # 更新来源标记
        for result in sorted_results[:top_k]:
            result.source = "fusion"

        return sorted_results[:top_k]

    def _weighted_merge(self, vector_results: List[RetrieveResult],
                        keyword_results: List[RetrieveResult],
                        top_k: int) -> List[RetrieveResult]:
        """
        加权融合

        综合分数 = vector_weight * vector_score + keyword_weight * keyword_score
        """
        # 合并结果
        all_results = {}

        for result in vector_results:
            doc_id = id(result.text)
            all_results[doc_id] = result

        for result in keyword_results:
            doc_id = id(result.text)
            if doc_id in all_results:
                # 合并分数
                all_results[doc_id].keyword_score = result.keyword_score
            else:
                all_results[doc_id] = result

        # 计算加权分数
        for result in all_results.values():
            result.score = (
                self.vector_weight * result.vector_score +
                self.keyword_weight * result.keyword_score
            )

        # 排序
        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x.score,
            reverse=True
        )

        # 更新来源标记
        for result in sorted_results[:top_k]:
            result.source = "fusion"

        return sorted_results[:top_k]


class Reranker:
    """重排序器 - 使用 BGE Reranker"""

    def __init__(self, model_name: str = "bge-reranker-v2-m3-zh"):
        """
        初始化重排序器

        Args:
            model_name: 模型名称
        """
        self.model_name = model_name
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        """懒加载模型"""
        if self._model is None:
            try:
                from FlagEmbedding import FlagReranker
                self._model = FlagReranker(self.model_name, use_fp16=False)
            except ImportError:
                print("[WARN] FlagEmbedding 未安装，Rerank 功能不可用")
                return None
        return self._model

    def rerank(self, query: str, documents: List[RetrieveResult],
               top_n: int = 5) -> List[RetrieveResult]:
        """
        重排序

        Args:
            query: 查询
            documents: 待排序文档列表
            top_n: 返回数量

        Returns:
            重排序后的结果
        """
        if not documents:
            return []

        model = self._load_model()
        if model is None:
            # 模型不可用时，按原分数返回
            return sorted(documents, key=lambda x: x.score, reverse=True)[:top_n]

        # 准备输入
        pairs = [[query, doc.text] for doc in documents]

        # 获取分数
        try:
            scores = model.compute_score(pairs)

            # 处理单分数和多分数情况
            if isinstance(scores, (int, float)):
                scores = [scores] * len(documents)
            elif isinstance(scores, list) and len(scores) == 1 and isinstance(scores[0], (int, float)):
                scores = scores * len(documents)
            elif hasattr(scores, 'tolist'):
                scores = scores.tolist()

            # 确保分数是列表
            if not isinstance(scores, list):
                scores = [float(scores)] * len(documents)

            # 设置重排分数
            for i, doc in enumerate(documents):
                if i < len(scores):
                    doc.score = scores[i]

            # 排序
            sorted_docs = sorted(documents, key=lambda x: x.score, reverse=True)

            # 更新来源标记
            for doc in sorted_docs[:top_n]:
                doc.source = "rerank"

            return sorted_docs[:top_n]

        except Exception as e:
            print(f"[WARN] Rerank 失败：{e}")
            return sorted(documents, key=lambda x: x.score, reverse=True)[:top_n]


class HybridRetriever:
    """
    混合检索器 - 整合向量、关键词、融合和重排序
    """

    def __init__(self, chroma_path: str, collection_name: str = "legal_docs",
                 use_rerank: bool = True,
                 vector_weight: float = 0.5,
                 keyword_weight: float = 0.5,
                 embedding_model: str = "BAAI/bge-large-zh-v1.5",
                 bm25_max_docs: int = 5000,  # BM25 索引最大文档数
                 precompute_bm25: bool = True,  # 是否预计算 BM25 索引
                 cache_embeddings: bool = True,  # 是否缓存 embedding
                 ):
        """
        初始化混合检索器

        Args:
            chroma_path: ChromaDB 路径
            collection_name: 集合名称
            use_rerank: 是否启用 Rerank
            vector_weight: 向量权重
            keyword_weight: 关键词权重
            embedding_model: Embedding 模型（bge-large-zh-v1.5 = 1024 维，中文优化）
            bm25_max_docs: BM25 索引最大文档数（限制内存占用）
            precompute_bm25: 是否预计算 BM25 索引（启动时加载）
            cache_embeddings: 是否缓存 embedding 结果
        """
        self.chroma_path = chroma_path
        self.collection_name = collection_name
        self.use_rerank = use_rerank
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.embedding_model = embedding_model
        self.bm25_max_docs = bm25_max_docs
        self.precompute_bm25 = precompute_bm25
        self.cache_embeddings = cache_embeddings

        # 初始化子组件
        self.vector_retriever = VectorRetriever(
            chroma_path=chroma_path,
            collection_name=collection_name,
            embedding_model=embedding_model,
            cache_embeddings=cache_embeddings
        )
        self.bm25_retriever = None  # 延迟初始化
        self.fusion = HybridFusion(
            method="weighted",
            vector_weight=vector_weight,
            keyword_weight=keyword_weight
        )
        self.reranker = Reranker() if use_rerank else None

        self._bm25_documents = []
        self._bm25_loaded = False

        # Embedding 缓存（LRU 缓存）
        self._embedding_cache: Dict[str, List[float]] = {}
        self._embedding_cache_max_size = 1000

    def _ensure_bm25_index(self):
        """确保 BM25 索引已加载（优化版）"""
        if not self._bm25_loaded:
            # 从 ChromaDB 加载所有文档
            collection = self.vector_retriever._get_collection()
            all_docs = collection.get(include=["documents"])

            if all_docs and all_docs["documents"]:
                # 限制 BM25 索引大小，避免内存溢出
                total_docs = len(all_docs["documents"])
                if total_docs > self.bm25_max_docs:
                    print(f"[INFO] 文档总数 {total_docs} 超过限制 {self.bm25_max_docs}，仅加载最新的 {self.bm25_max_docs} 个文档")
                    # 只加载最新的文档（假设后面的文档是最近添加的）
                    self._bm25_documents = all_docs["documents"][-self.bm25_max_docs:]
                else:
                    self._bm25_documents = all_docs["documents"]

                # 构建 BM25 索引
                self.bm25_retriever = BM25Retriever(documents=self._bm25_documents)
                self._bm25_loaded = True
                print(f"[INFO] BM25 索引加载完成，共 {len(self._bm25_documents)} 个文档")

    def retrieve(self, query: str, top_k: int = 5,
                 rerank_top_n: int = 20,
                 filter_metadata: Optional[Dict] = None,
                 use_hybrid: bool = True) -> List[Dict]:
        """
        执行混合检索（优化版）

        Args:
            query: 查询
            top_k: 返回数量
            rerank_top_n: Rerank 候选数量
            filter_metadata: 元数据过滤
            use_hybrid: 是否使用混合检索

        Returns:
            检索结果（字典列表）
        """
        # 1. 向量检索
        vector_results = self.vector_retriever.search(
            query, k=rerank_top_n, filter_metadata=filter_metadata
        )

        # 2. 关键词检索（可选）- 异步加载
        keyword_results = []
        if use_hybrid:
            # 仅在未预计算时延迟加载
            if not self.precompute_bm25:
                self._ensure_bm25_index()
            if self.bm25_retriever:
                keyword_results = self.bm25_retriever.search(query, k=rerank_top_n)

        # 3. 融合
        if use_hybrid and keyword_results:
            fused_results = self.fusion.merge(
                vector_results, keyword_results, top_k=rerank_top_n
            )
        else:
            fused_results = vector_results

        # 4. Rerank（可选）
        if self.use_rerank and self.reranker and len(fused_results) > 1:
            final_results = self.reranker.rerank(query, fused_results, top_n=top_k)
        else:
            # 按分数排序
            final_results = sorted(fused_results, key=lambda x: x.score, reverse=True)[:top_k]

        # 5. 转换为字典格式
        return [
            {
                "text": result.text,
                "score": result.score,
                "vector_score": result.vector_score,
                "keyword_score": result.keyword_score,
                "metadata": result.metadata,
                "source": result.source,
            }
            for result in final_results
        ]

    def retrieve_with_context(self, query: str, top_k: int = 5, **kwargs) -> Tuple[str, List[Dict]]:
        """
        检索并返回上下文和引用

        Args:
            query: 查询
            top_k: 返回数量
            **kwargs: 其他参数

        Returns:
            (上下文文本，引用列表)
        """
        results = self.retrieve(query, top_k=top_k, **kwargs)

        # 构建上下文
        context_parts = []
        citations = []

        for idx, result in enumerate(results):
            context_parts.append(f"[{idx + 1}] {result['text']}")

            # 计算综合相似度
            similarity = result['score']

            # 获取页码信息
            # 优先从 metadata 获取 page_num，如果没有则从 section_title 中提取
            page_num = result['metadata'].get('page_num')
            if page_num is None:
                # 从 section_title 中提取页码（格式："第 X 页" 或 "第 X ҳ"）
                section_title = result['metadata'].get('section_title', '')
                import re
                match = re.search(r'第\s*(\d+)\s*(页|ҳ)', section_title)
                if match:
                    page_num = int(match.group(1))
                else:
                    page_num = 1

            page_range = result['metadata'].get('page_range', str(page_num))

            # 构建完整的引用溯源信息
            citation = {
                "id": idx + 1,
                "file_name": result['metadata'].get('file_name', '未知'),
                "section_title": result['metadata'].get('section_title', ''),
                "hierarchy_path": result['metadata'].get('hierarchy_path', ''),  # 层级路径
                "similarity": round(similarity * 100, 1) if similarity < 1 else round(similarity, 3),
                "chunk_id": result['metadata'].get('chunk_id', 0),
                "doc_id": result['metadata'].get('doc_id', ''),
                "source_path": result['metadata'].get('source_path', ''),
                "page_num": page_num,
                "page_range": page_range,  # 页码范围（如 "3-5"）
                "chunk_text": result['text'],
                "search_source": result['source'],  # vector/keyword/fusion/rerank
                # 格式化后的引用字符串，用于直接显示
                "citation_label": f"{result['metadata'].get('file_name', '未知')} 第 {page_num} 页",
            }
            citations.append(citation)

        context = "\n\n".join(context_parts)
        return context, citations


# ==================== 便捷函数 ====================

_default_retriever: Optional[HybridRetriever] = None


def get_retriever(chroma_path: str = "./chroma_db",
                  collection_name: str = "legal_docs",
                  use_rerank: bool = True) -> HybridRetriever:
    """获取全局检索器实例（单例模式）"""
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = HybridRetriever(
            chroma_path=chroma_path,
            collection_name=collection_name,
            use_rerank=use_rerank
        )
    return _default_retriever


def hybrid_search(query: str, top_k: int = 5,
                  chroma_path: str = "./chroma_db") -> List[Dict]:
    """
    便捷函数：执行混合检索

    Args:
        query: 查询
        top_k: 返回数量
        chroma_path: ChromaDB 路径

    Returns:
        检索结果列表
    """
    retriever = get_retriever(chroma_path=chroma_path)
    return retriever.retrieve(query, top_k=top_k)


# ==================== 命令行测试 ====================

if __name__ == "__main__":
    # 测试（BGE 本地模型，无需 API Key）
    retriever = HybridRetriever(
        chroma_path="./chroma_db",
        collection_name="legal_docs",
        use_rerank=False  # 先测试不启用 rerank
    )

    query = "出差报销标准"
    print(f"\n查询：{query}\n")

    results = retriever.retrieve(query, top_k=5)

    print(f"检索到 {len(results)} 条结果:\n")
    for i, result in enumerate(results):
        print(f"[{i + 1}] 分数：{result['score']:.4f} (向量：{result['vector_score']:.4f}, 关键词：{result['keyword_score']:.4f})")
        print(f"    来源：{result['source']}")
        print(f"    文件：{result['metadata'].get('file_name', '未知')}")
        print(f"    章节：{result['metadata'].get('section_title', '')}")
        print(f"    内容：{result['text'][:100]}...\n")