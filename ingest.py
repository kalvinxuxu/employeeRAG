"""
PDF  ingest 脚本 - 基于 Docling 的结构化解析

功能：
- 使用 Docling 精准解析 PDF 文档
- 提取结构化文本（Markdown 格式）
- 自动记录完整的元数据（Metadata）
- 按标题层级智能分块（Chunking）
- 存入 ChromaDB 向量库

用法:
    python ingest.py                    # 使用默认配置
    python ingest.py -i ./data          # 指定输入目录
    python ingest.py --clear-collection # 清空集合后重新索引
"""

import os
import sys
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# 设置 UTF-8 编码输出 (Windows)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docling.document_converter import DocumentConverter
from chromadb import PersistentClient
from chromadb.api.types import EmbeddingFunction


# ==================== 自定义 Embedding 函数 ====================

class DashScopeEmbeddingFunction(EmbeddingFunction):
    """DashScope embedding 函数用于 ChromaDB"""

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

    # 输入输出
    "input_dir": "./data",      # 修改为 data 目录
    "metadata_file": "./data/ingest_metadata.json",

    # Embedding 模型（本地）
    "embedding_model": "default",  # 使用 ChromaDB 默认 embedding
}


# ==================== 元数据提取 ====================

def generate_doc_id(file_path: str) -> str:
    """生成文档的唯一 ID"""
    return hashlib.md5(file_path.encode()).hexdigest()[:12]


def extract_metadata(file_path: str, doc_metadata: Optional[dict] = None) -> dict:
    """
    提取/生成文档元数据

    Args:
        file_path: PDF 文件路径
        doc_metadata: Docling 解析出的元数据

    Returns:
        元数据字典
    """
    path = Path(file_path)
    stat = path.stat()

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

        # 来源路径（相对路径）
        "source_path": str(path),
    }

    # 合并 Docling 提供的元数据
    if doc_metadata:
        metadata.update({
            "num_pages": doc_metadata.get("num_pages", 0),
            "title": doc_metadata.get("title", path.stem),
            "author": doc_metadata.get("author", ""),
            "language": doc_metadata.get("language", "zh"),
        })

    return metadata


# ==================== 智能分块 ====================

def split_by_headers(markdown_text: str, chunk_size: int = 500) -> list[dict]:
    """
    按 Markdown 标题智能分块

    Args:
        markdown_text: Markdown 格式文本
        chunk_size: 最大块大小

    Returns:
        分块列表，每块包含 {text, section_title, heading_level}
    """
    chunks = []
    lines = markdown_text.split('\n')

    current_section = {
        "title": "文档概述",
        "level": 0,
        "content": []
    }

    for line in lines:
        # 检测标题行
        if line.startswith('#'):
            # 保存之前的章节
            if current_section["content"]:
                section_text = '\n'.join(current_section["content"])
                chunks.append({
                    "text": section_text,
                    "section_title": current_section["title"],
                    "heading_level": current_section["level"],
                })

            # 解析新标题
            level = len(line) - len(line.lstrip('#'))
            title = line.strip('# ').strip()

            current_section = {
                "title": title,
                "level": level,
                "content": [line]
            }
        else:
            current_section["content"].append(line)

    # 处理最后一个章节
    if current_section["content"]:
        section_text = '\n'.join(current_section["content"])
        chunks.append({
            "text": section_text,
            "section_title": current_section["title"],
            "heading_level": current_section["level"],
        })

    # 对过大的块进行二次分割
    final_chunks = []
    for chunk in chunks:
        text = chunk["text"]
        if len(text) > chunk_size * 1.5:
            # 按段落分割
            paragraphs = text.split('\n\n')
            current_chunk = []
            current_len = 0

            for para in paragraphs:
                if current_len + len(para) > chunk_size:
                    if current_chunk:
                        final_chunks.append({
                            "text": '\n\n'.join(current_chunk),
                            "section_title": chunk["section_title"],
                            "heading_level": chunk["heading_level"],
                        })
                    current_chunk = [para]
                    current_len = len(para)
                else:
                    current_chunk.append(para)
                    current_len += len(para)

            if current_chunk:
                final_chunks.append({
                    "text": '\n\n'.join(current_chunk),
                    "section_title": chunk["section_title"],
                    "heading_level": chunk["heading_level"],
                })
        else:
            final_chunks.append(chunk)

    return final_chunks


def split_by_fixed_size(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    按固定大小分块（简单但高效）

    Args:
        text: 文本内容
        chunk_size: 每块大小
        overlap: 重叠大小

    Returns:
        分块列表
    """
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # 尝试在句子边界处切分
        if end < len(text):
            # 查找最近的句号
            for sep in ['.', '.', '?', '!', '\n']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1:
                    end = start + last_sep + 1
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


# ==================== 主处理流程 ====================

def process_single_pdf(
    file_path: str,
    converter: DocumentConverter,
    collection,
    config: dict
) -> dict:
    """
    处理单个 PDF 文件

    Returns:
        处理统计信息
    """
    path = Path(file_path)
    print(f"\n[INFO] 正在解析：{path.name}")

    try:
        # 使用 Docling 转换
        result = converter.convert(str(path))

        # 导出为 Markdown（结构化文本）
        doc_text = result.document.export_to_markdown()

        # 获取元数据
        doc_info = {
            "num_pages": len(result.document.pages),
            "title": path.stem,
        }
        metadata = extract_metadata(str(path), doc_info)

        # 智能分块（优先按标题，其次按固定大小）
        chunks = split_by_headers(doc_text, config["chunk_size"])

        # 如果分块太少，改用固定大小分块
        if len(chunks) < 3:
            chunks_text = '\n'.join([c["text"] for c in chunks])
            chunks = split_by_fixed_size(
                doc_text,
                config["chunk_size"],
                config["chunk_overlap"]
            )
            # 为固定分块添加简单元数据
            chunks = [
                {
                    "text": chunk,
                    "section_title": metadata["file_name"],
                    "heading_level": 0
                }
                for chunk in chunks
            ]

        # 存入向量库
        documents = []
        ids = []
        metadatas = []

        for idx, chunk in enumerate(chunks):
            chunk_metadata = {
                **metadata,
                "chunk_id": idx,
                "total_chunks": len(chunks),
                "section_title": chunk.get("section_title", ""),
                "heading_level": chunk.get("heading_level", 0),
            }

            documents.append(chunk["text"])
            ids.append(f"{metadata['doc_id']}_chunk_{idx}")
            metadatas.append(chunk_metadata)

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
            "num_pages": metadata["num_pages"],
            "num_chunks": len(chunks),
            "doc_id": metadata["doc_id"],
            "error": None,
        }

        print(f"       [OK] 解析完成：{len(chunks)} 个文本块 / {metadata['num_pages']} 页")
        return stats

    except Exception as e:
        print(f"       [FAIL] 解析失败：{str(e)}")
        return {
            "file_name": path.name,
            "status": "failed",
            "error": str(e),
        }


def ingest_all_pdfs(config: dict = None):
    """
    批量处理目录中的所有 PDF 文件

    Args:
        config: 配置字典（可选，使用默认配置）
    """
    config = config or CONFIG

    print("=" * 60)
    print("PDF Ingest 脚本 - 基于 Docling")
    print("=" * 60)

    # 1. 初始化向量数据库
    print(f"\n[STEP 1] 初始化 ChromaDB: {config['chroma_path']}")
    db_client = PersistentClient(path=config["chroma_path"])

    # 检查 API Key
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("[ERROR] 未设置 DASHSCOPE_API_KEY 环境变量")
        return

    # 使用 DashScope Embedding
    dashscope_ef = DashScopeEmbeddingFunction(api_key=api_key)

    collection = db_client.get_or_create_collection(
        name=config["collection_name"],
        embedding_function=dashscope_ef,
        metadata={"description": "Legal documents and policies"}
    )

    # 显示当前集合状态
    existing_count = collection.count()
    print(f"       集合 '{config['collection_name']}' 当前文档数：{existing_count}")

    # 2. 初始化 Docling 解析器
    print("\n[STEP 2] 初始化 Docling DocumentConverter")
    converter = DocumentConverter()

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
            converter,
            collection,
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
        description="PDF Ingest 脚本 - 基于 Docling 的结构化解析"
    )
    parser.add_argument(
        "--input-dir", "-i",
        default="./docs",
        help="PDF 文件输入目录 (默认：./docs)"
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
    }

    # 如果需要清空集合
    if args.clear_collection:
        from chromadb import HttpClient
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
