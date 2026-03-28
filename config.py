"""
统一配置管理模块

功能:
- 集中管理所有配置参数
- 支持从环境变量加载配置
- 提供配置验证

用法:
    from config import get_config

    config = get_config()
    print(config.chunk_size)
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ChromaConfig:
    """ChromaDB 配置"""
    path: str = "./chroma_db"
    collection_name: str = "legal_docs"


@dataclass
class DashScopeConfig:
    """DashScope 配置"""
    api_key: Optional[str] = None
    embedding_model: str = "text-embedding-v3"
    llm_model: str = "qwen-plus"

    def __post_init__(self):
        if self.api_key is None:
            self.api_key = os.getenv("DASHSCOPE_API_KEY")


@dataclass
class ChunkConfig:
    """分块配置"""
    chunk_size: int = 500
    chunk_overlap: int = 100
    min_chunk_size: int = 100
    overlap_ratio: float = 0.1  # 10% 重叠
    use_recursive: bool = True  # 使用递归层级切片


@dataclass
class RetrievalConfig:
    """检索配置"""
    use_hybrid: bool = True       # 使用混合检索
    use_rerank: bool = False      # 使用 Rerank（需要 FlagEmbedding）
    rerank_top_n: int = 20        # Rerank 候选数
    top_k: int = 5                # 最终返回数
    vector_weight: float = 0.5    # 向量权重
    keyword_weight: float = 0.5   # 关键词权重
    rrf_k: int = 60               # RRF 常数


@dataclass
class CacheConfig:
    """语义缓存配置"""
    use_cache: bool = True                    # 是否启用语义缓存
    cache_path: str = "./semantic_cache"      # 缓存数据路径
    similarity_threshold: float = 0.95        # 相似度阈值
    max_cache_size: int = 10000               # 最大缓存条目数
    ttl_days: Optional[int] = 7               # 缓存有效期（天）
    embedding_model: str = "text-embedding-v3"  # Embedding 模型


@dataclass
class StreamingConfig:
    """流式输出配置"""
    use_streaming: bool = True                # 是否启用流式输出
    stream_chunk_size: int = 1                # 流式输出块大小（字符数）
    stream_delay: float = 0.01                # 流式输出延迟（秒）


@dataclass
class IngestConfig:
    """Ingest 配置"""
    input_dir: str = "./data"
    metadata_file: str = "./data/ingest_metadata.json"
    pdf_extensions: list = field(default_factory=lambda: [".pdf"])


@dataclass
class AppConfig:
    """应用主配置"""
    # 子配置
    chroma: ChromaConfig = field(default_factory=ChromaConfig)
    dashscope: DashScopeConfig = field(default_factory=DashScopeConfig)
    chunk: ChunkConfig = field(default_factory=ChunkConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)

    # 其他配置
    pdf_base_dir: str = "./data"
    log_level: str = "INFO"
    debug: bool = False

    # 转换为字典（方便与现有代码兼容）
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chroma_path": self.chroma.path,
            "collection_name": self.chroma.collection_name,
            "pdf_base_dir": self.pdf_base_dir,
            "llm_model": self.dashscope.llm_model,
            "embedding_model": self.dashscope.embedding_model,

            # 混合检索配置
            "use_hybrid_search": self.retrieval.use_hybrid,
            "use_rerank": self.retrieval.use_rerank,
            "rerank_top_n": self.retrieval.rerank_top_n,
            "vector_weight": self.retrieval.vector_weight,
            "keyword_weight": self.retrieval.keyword_weight,

            # 语义缓存配置
            "use_cache": self.cache.use_cache,
            "cache_path": self.cache.cache_path,
            "similarity_threshold": self.cache.similarity_threshold,
            "max_cache_size": self.cache.max_cache_size,
            "cache_ttl_days": self.cache.ttl_days,

            # 流式输出配置
            "use_streaming": self.streaming.use_streaming,
            "stream_chunk_size": self.streaming.stream_chunk_size,
            "stream_delay": self.streaming.stream_delay,

            # 分块配置
            "chunk_size": self.chunk.chunk_size,
            "chunk_overlap": self.chunk.chunk_overlap,

            # Ingest 配置
            "input_dir": self.ingest.input_dir,
            "metadata_file": self.ingest.metadata_file,

            # 其他
            "log_level": self.log_level,
            "debug": self.debug,
        }


# 全局配置实例
_global_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置（单例模式）"""
    global _global_config
    if _global_config is None:
        _global_config = load_config_from_env()
    return _global_config


def load_config_from_env() -> AppConfig:
    """从环境变量加载配置"""
    config = AppConfig()

    # ChromaDB 配置
    if os.getenv("CHROMA_PATH"):
        config.chroma.path = os.getenv("CHROMA_PATH")
    if os.getenv("COLLECTION_NAME"):
        config.chroma.collection_name = os.getenv("COLLECTION_NAME")

    # DashScope 配置
    if os.getenv("DASHSCOPE_API_KEY"):
        config.dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
    if os.getenv("DASHSCOPE_EMBEDDING_MODEL"):
        config.dashscope.embedding_model = os.getenv("DASHSCOPE_EMBEDDING_MODEL")
    if os.getenv("DASHSCOPE_LLM_MODEL"):
        config.dashscope.llm_model = os.getenv("DASHSCOPE_LLM_MODEL")

    # 分块配置
    if os.getenv("CHUNK_SIZE"):
        config.chunk.chunk_size = int(os.getenv("CHUNK_SIZE"))
    if os.getenv("CHUNK_OVERLAP"):
        config.chunk.chunk_overlap = int(os.getenv("CHUNK_OVERLAP"))
    if os.getenv("OVERLAP_RATIO"):
        config.chunk.overlap_ratio = float(os.getenv("OVERLAP_RATIO"))

    # 检索配置
    if os.getenv("USE_HYBRID_SEARCH"):
        config.retrieval.use_hybrid = os.getenv("USE_HYBRID_SEARCH").lower() == "true"
    if os.getenv("USE_RERANK"):
        config.retrieval.use_rerank = os.getenv("USE_RERANK").lower() == "true"
    if os.getenv("VECTOR_WEIGHT"):
        config.retrieval.vector_weight = float(os.getenv("VECTOR_WEIGHT"))
    if os.getenv("KEYWORD_WEIGHT"):
        config.retrieval.keyword_weight = float(os.getenv("KEYWORD_WEIGHT"))

    # Ingest 配置
    if os.getenv("INPUT_DIR"):
        config.ingest.input_dir = os.getenv("INPUT_DIR")

    # 其他配置
    if os.getenv("LOG_LEVEL"):
        config.log_level = os.getenv("LOG_LEVEL")
    if os.getenv("DEBUG"):
        config.debug = os.getenv("DEBUG").lower() == "true"

    return config


def reload_config() -> AppConfig:
    """重新加载配置"""
    global _global_config
    _global_config = load_config_from_env()
    return _global_config


# ==================== 兼容性配置字典 ====================
# 用于与现有代码兼容

def get_config_dict() -> Dict[str, Any]:
    """获取配置字典（与现有 CONFIG 格式兼容）"""
    return get_config().to_dict()


# 默认配置字典（向后兼容）
DEFAULT_CONFIG = get_config_dict()
