"""
PDF Ingest 脚本 - 增强版

功能:
- 使用递归层级切片 (chunker.py)
- 自动添加业务标签 (metadata_tagger.py)
- 支持混合检索的数据准备
- 存入 ChromaDB 向量库

用法:
    python ingest_enhanced.py                    # 使用默认配置
    python ingest_enhanced.py -i ./data          # 指定输入目录
    python ingest_enhanced.py --clear-collection # 清空集合后重新索引
"""

import os
import sys
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# 设置 UTF-8 编码输出 (Windows)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import fitz  # PyMuPDF
from chromadb import PersistentClient
from chromadb.api.types import EmbeddingFunction

# 导入自定义模块
from chunker import RecursiveChunker, split_document
from metadata_tagger import MetadataTagger, extract_document_tags


# ==================== 自定义 Embedding 函数 ====================

class EmbeddingFactory:
    """Embedding 工厂类 - 根据网络情况自动选择模型"""

    @staticmethod
    def get_embedding(model_name: str = "bge-large-zh-v1.5", api_key: str = None):
        """
        获取 Embedding 函数

        Args:
            model_name: 模型名称
            api_key: DashScope API Key（可选）

        Returns:
            Embedding 函数实例
        """
        # 优先尝试本地 BGE 模型
        if model_name.startswith("bge-"):
            try:
                from FlagEmbedding import FlagModel
                # 设置国内镜像源
                import os
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

                return BGEEmbeddingFunction(model_name=model_name)
            except Exception as e:
                print(f"[WARN] BGE 模型加载失败：{e}")
                print("[INFO] 切换到 DashScope Embedding API")

        # 回退到 DashScope API
        if not api_key:
            api_key = os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            return DashScopeEmbeddingFunction(api_key=api_key)

        raise RuntimeError("无法加载任何 Embedding 模型：BGE 不可用且未设置 DASHSCOPE_API_KEY")


class BGEEmbeddingFunction:
    """BGE Embedding 函数用于 ChromaDB（本地模型）"""

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
        """懒加载 embedding 模型"""
        if self._model is None:
            from FlagEmbedding import FlagModel
            self._model = FlagModel(
                self.model_name,
                query_instruction_for_retrieval="为这个句子生成表示以用于检索：",
                use_fp16=False  # 提高精度
            )
        return self._model

    def __call__(self, input: list[str]) -> list[list[float]]:
        """生成 embedding"""
        model = self._get_model()
        if len(input) == 1:
            embedding = model.encode(input[0])
            return [embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)]
        else:
            embeddings = model.encode(input)
            return [emb.tolist() if hasattr(emb, 'tolist') else list(emb) for emb in embeddings]


class DashScopeEmbeddingFunction:
    """DashScope embedding 函数用于 ChromaDB（备用方案）"""

    def __init__(self, api_key: str, model: str = "text-embedding-v3"):
        self.api_key = api_key
        self.model = model
        self._ef = None

    def _get_ef(self):
        """懒加载 embedding 函数"""
        if self._ef is None:
            from llama_index.embeddings.dashscope import DashScopeEmbedding
            self._ef = DashScopeEmbedding(model=self.model, api_key=self.api_key)
        return self._ef

    def __call__(self, input: list[str]) -> list[list[float]]:
        """生成 embedding"""
        ef = self._get_ef()
        if len(input) == 1:
            embedding = ef.get_text_embedding(input[0])
            return [embedding]
        else:
            return ef.get_text_embedding_batch(input)


# ==================== 配置区域 ====================

CONFIG = {
    # ChromaDB 配置
    "chroma_path": "./chroma_db",
    "collection_name": "legal_docs",

    # 分块配置
    "chunk_size": 500,          # 每块字符数
    "chunk_overlap": 100,       # 重叠字符数
    "overlap_ratio": 0.1,       # 重叠比例 (10%)

    # 输入输出
    "input_dir": "./data",
    "metadata_file": "./data/ingest_metadata.json",

    # Embedding 模型
    "embedding_model": "bge-large-zh-v1.5",  # 中文优化 Embedding
}


# ==================== PDF 解析 ====================

def generate_doc_id(file_path: str) -> str:
    """生成文档的唯一 ID"""
    return hashlib.md5(file_path.encode()).hexdigest()[:12]


def extract_pdf_metadata(file_path: str, pdf_doc: fitz.Document) -> dict:
    """
    提取 PDF 文档元数据

    Args:
        file_path: PDF 文件路径
        pdf_doc: PyMuPDF 文档对象

    Returns:
        元数据字典
    """
    path = Path(file_path)
    stat = path.stat()

    # 获取 PDF 内置元数据
    pdf_metadata = pdf_doc.metadata or {}

    metadata = {
        # 文件信息
        "file_name": path.name,
        "file_size": stat.st_size,
        "file_extension": path.suffix.lower(),

        # 时间信息
        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "ingested_at": datetime.now().isoformat(),

        # 文档唯一标识
        "doc_id": generate_doc_id(str(path.absolute())),

        # 内容类型
        "content_type": "legal_policy",

        # 来源路径
        "source_path": str(path),

        # PDF 信息
        "num_pages": len(pdf_doc),
        "title": pdf_metadata.get("title", path.stem),
        "author": pdf_metadata.get("author", ""),
        "subject": pdf_metadata.get("subject", ""),
    }

    return metadata


def extract_text_from_pdf(pdf_path: str) -> tuple[str, List[dict]]:
    """
    从 PDF 提取文本，同时保留页面结构

    Args:
        pdf_path: PDF 文件路径

    Returns:
        (完整文本，页面信息列表)
    """
    doc = fitz.open(pdf_path)
    pages_info = []
    text_parts = []

    for page_num, page in enumerate(doc, 1):
        page_text = page.get_text("text")

        pages_info.append({
            "page_num": page_num,
            "text_length": len(page_text),
        })

        if page_text.strip():
            text_parts.append(f"# 第 {page_num} 页\n\n{page_text}")

    doc.close()
    return "\n\n".join(text_parts), pages_info


# ==================== 主处理流程 ====================

def process_single_pdf(
    file_path: str,
    collection,
    chunker: RecursiveChunker,
    tagger: MetadataTagger,
    config: dict
) -> dict:
    """
    处理单个 PDF 文件（增强版）

    Returns:
        处理统计信息
    """
    path = Path(file_path)
    print(f"\n[INFO] 正在解析：{path.name}")

    try:
        # 1. 打开 PDF
        pdf_doc = fitz.open(str(path))

        # 2. 提取文本（带页面信息）
        full_text, pages_info = extract_text_from_pdf(str(path))

        # 3. 提取基础元数据
        base_metadata = extract_pdf_metadata(str(path), pdf_doc)
        pdf_doc.close()

        # 4. 构建页码映射：[(page_num, start_pos, end_pos), ...]
        # 首先解析 full_text 中的页面边界
        page_map = []
        current_pos = 0
        for page_info in pages_info:
            page_num = page_info["page_num"]
            # 查找 "# 第 X 页" 标记的位置
            page_marker = f"# 第 {page_num} 页"
            start_pos = full_text.find(page_marker)
            if start_pos == -1:
                start_pos = current_pos

            end_pos = start_pos + page_info["text_length"] + len(page_marker) + 10
            page_map.append((page_num, start_pos, end_pos))

        # 5. 递归层级切片（传入页码映射）
        chunks = chunker.split_recursive(full_text, page_map=page_map)

        # 5. 为每个 chunk 添加业务标签
        tagged_chunks = []
        for chunk in chunks:
            # 从 chunk 文本提取业务标签
            chunk_tags = tagger.extract_tags(
                text=chunk.text,
                file_name=path.name,
                existing_metadata={
                    **base_metadata,
                    "chunk_id": len(tagged_chunks),
                    "total_chunks": len(chunks),
                    "section_title": chunk.section_title,
                    "heading_level": chunk.heading_level,
                    "hierarchy_path": chunk.hierarchy_path,
                    "page_num": chunk.page_num,        # 页码
                    "page_range": chunk.page_range,    # 页码范围
                }
            )
            chunk.metadata = chunk_tags
            tagged_chunks.append(chunk)

        # 6. 存入向量库
        documents = []
        ids = []
        metadatas = []

        for idx, chunk in enumerate(tagged_chunks):
            # 扁平化 metadata（ChromaDB 要求）
            flat_metadata = {
                **chunk.metadata,
                "keywords": ",".join(chunk.metadata.get("keywords", [])),  # 列表转字符串
                "applicable_roles": ",".join(chunk.metadata.get("applicable_roles", [])),
            }

            # 确保所有值都是字符串、数字或 None
            clean_metadata = {}
            for key, value in flat_metadata.items():
                if isinstance(value, (str, int, float, type(None))):
                    clean_metadata[key] = value
                elif isinstance(value, list):
                    clean_metadata[key] = ",".join(str(v) for v in value)
                elif isinstance(value, dict):
                    clean_metadata[key] = json.dumps(value, ensure_ascii=False)
                else:
                    clean_metadata[key] = str(value)

            documents.append(chunk.text)
            ids.append(f"{base_metadata['doc_id']}_chunk_{idx}")
            metadatas.append(clean_metadata)

        # 批量添加到 ChromaDB
        if documents:
            collection.add(
                documents=documents,
                ids=ids,
                metadatas=metadatas,
            )

        stats = {
            "file_name": path.name,
            "status": "success",
            "num_pages": base_metadata["num_pages"],
            "num_chunks": len(chunks),
            "doc_id": base_metadata["doc_id"],
            "department": chunks[0].metadata.get("department", "未知") if chunks else "未知",
            "category": chunks[0].metadata.get("category", "未知") if chunks else "未知",
            "error": None,
        }

        print(f"       [OK] 解析完成：{len(chunks)} 个文本块 / {base_metadata['num_pages']} 页")
        print(f"            部门：{stats['department']}, 类别：{stats['category']}")
        return stats

    except Exception as e:
        print(f"       [FAIL] 解析失败：{str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "file_name": path.name,
            "status": "failed",
            "error": str(e),
        }


def ingest_all_pdfs(config: dict = None):
    """
    批量处理目录中的所有 PDF 文件（增强版）

    Args:
        config: 配置字典（可选，使用默认配置）
    """
    config = config or CONFIG

    print("=" * 60)
    print("PDF Ingest 脚本 - 增强版（递归切片 + 业务标签）")
    print("=" * 60)

    # 1. 初始化向量数据库
    print(f"\n[STEP 1] 初始化 ChromaDB: {config['chroma_path']}")
    db_client = PersistentClient(path=config["chroma_path"])

    # 使用 BGE Embedding（本地模型，无需 API Key）
    bge_ef = BGEEmbeddingFunction(model_name=config.get("embedding_model", "BAAI/bge-large-zh-v1.5"))

    collection = db_client.get_or_create_collection(
        name=config["collection_name"],
        embedding_function=bge_ef,
        metadata={"description": "Legal documents and policies with enhanced metadata"}
    )

    # 显示当前集合状态
    existing_count = collection.count()
    print(f"       集合 '{config['collection_name']}' 当前文档数：{existing_count}")

    # 2. 初始化切片器和标签提取器
    print("\n[STEP 2] 初始化 RecursiveChunker 和 MetadataTagger")
    chunker = RecursiveChunker(
        chunk_size=config.get("chunk_size", 500),
        overlap_ratio=config.get("overlap_ratio", 0.1)
    )
    tagger = MetadataTagger()

    # 3. 扫描输入目录
    input_dir = Path(config["input_dir"])
    if not input_dir.exists():
        print(f"[ERROR] 输入目录不存在：{input_dir}")
        return

    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[WARN] 目录中没有找到 PDF 文件：{input_dir}")
        return

    print(f"\n[STEP 3] 发现 {len(pdf_files)} 个 PDF 文件")

    # 4. 处理每个文件
    stats_list = []
    for pdf_file in pdf_files:
        stats = process_single_pdf(
            str(pdf_file),
            collection,
            chunker,
            tagger,
            config
        )
        stats_list.append(stats)

    # 5. 保存处理日志
    summary = {
        "ingested_at": datetime.now().isoformat(),
        "input_dir": str(input_dir.absolute()),
        "total_files": len(pdf_files),
        "successful": sum(1 for s in stats_list if s["status"] == "success"),
        "failed": sum(1 for s in stats_list if s["status"] == "failed"),
        "total_chunks": collection.count() - existing_count,
        "files": stats_list,
    }

    # 保存元数据日志
    with open(config["metadata_file"], 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 6. 打印摘要
    print("\n" + "=" * 60)
    print("处理摘要")
    print("=" * 60)
    print(f"  输入目录：{input_dir}")
    print(f"  处理文件：{summary['successful']}/{len(pdf_files)}")
    print(f"  新增文本块：{summary['total_chunks']}")
    print(f"  元数据日志：{config['metadata_file']}")

    # 按部门统计
    departments = {}
    categories = {}
    for s in stats_list:
        if s["status"] == "success":
            dept = s.get("department", "未知")
            cat = s.get("category", "未知")
            departments[dept] = departments.get(dept, 0) + 1
            categories[cat] = categories.get(cat, 0) + 1

    if departments:
        print(f"\n  部门分布:")
        for dept, count in sorted(departments.items()):
            print(f"    - {dept}: {count} 个文件")

    if categories:
        print(f"\n  类别分布:")
        for cat, count in sorted(categories.items()):
            print(f"    - {cat}: {count} 个文件")

    if summary['failed'] > 0:
        print(f"\n  失败文件:")
        for s in stats_list:
            if s["status"] == "failed":
                print(f"    - {s['file_name']}: {s['error']}")

    print("\n[OK] Ingest 完成！")

    return summary


# ==================== 命令行入口 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="PDF Ingest 脚本 - 增强版（递归切片 + 业务标签）"
    )
    parser.add_argument(
        "--input-dir", "-i",
        default="./data",
        help="PDF 文件输入目录 (默认：./data)"
    )
    parser.add_argument(
        "--chroma-path", "-c",
        default="./chroma_db",
        help="ChromaDB 存储路径 (默认：./chroma_db)"
    )
    parser.add_argument(
        "--collection",
        default="legal_docs",
        help="ChromaDB 集合名称 (默认：legal_docs)"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="分块大小 (默认：500)"
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=100,
        help="分块重叠 (默认：100)"
    )
    parser.add_argument(
        "--overlap-ratio",
        type=float,
        default=0.1,
        help="重叠比例 (默认：0.1)"
    )
    parser.add_argument(
        "--clear-collection",
        action="store_true",
        help="清空现有集合后重新索引"
    )

    args = parser.parse_args()

    # 应用命令行参数
    custom_config = {
        **CONFIG,
        "input_dir": args.input_dir,
        "chroma_path": args.chroma_path,
        "collection_name": args.collection,
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "overlap_ratio": args.overlap_ratio,
    }

    # 如果需要清空集合
    if args.clear_collection:
        confirm = input("[WARN] 确认要清空集合 '{}' 吗？(yes/no): ".format(args.collection))
        if confirm.lower() == 'yes':
            db_client = PersistentClient(path=args.chroma_path)
            try:
                db_client.delete_collection(args.collection)
                print("[OK] 已清空集合：{}".format(args.collection))
            except Exception:
                pass

    # 运行 ingest
    ingest_all_pdfs(custom_config)
