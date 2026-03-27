"""
PDF Ingest 脚本 - 基于 PyMuPDF 的快速解析

这是 Docling ingest.py 的轻量版本，不依赖网络模型下载。

功能：
- 使用 PyMuPDF (fitz) 快速解析 PDF 文档
- 提取文本并转换为类 Markdown 格式
- 自动记录完整的元数据（Metadata）
- 按标题/段落智能分块（Chunking）
- 存入 ChromaDB 向量库

用法:
    python ingest_lite.py                    # 使用默认配置
    python ingest_lite.py -i ./data          # 指定输入目录
    python ingest_lite.py --clear-collection # 清空集合后重新索引
"""

import os
import sys
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

# 设置 UTF-8 编码输出 (Windows)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import fitz  # PyMuPDF
from chromadb import PersistentClient
from chromadb.api.types import EmbeddingFunction


# ==================== 自定义 Embedding 函数 ====================

class DashScopeEmbeddingFunction(EmbeddingFunction):
    """DashScope embedding 函数用于 ChromaDB"""

    def __init__(self, api_key: str, model: str = "text-embedding-v3"):
        self.api_key = api_key
        self.model = model

    def name(self) -> str:
        """返回 embedding 函数名称"""
        return f"dashscope-{self.model}"

    def __call__(self, input: list[str]) -> list[list[float]]:
        """生成 embedding（支持批量处理，最大批量大小为 10）"""
        import dashscope
        dashscope.api_key = self.api_key

        # DashScope API 限制批量大小不能超过 10 个
        MAX_BATCH_SIZE = 10
        all_embeddings = []

        # 分批次处理
        for i in range(0, len(input), MAX_BATCH_SIZE):
            batch = input[i:i + MAX_BATCH_SIZE]
            response = dashscope.TextEmbedding.call(
                model=self.model,
                input=batch,
                text_type="document"
            )

            if response.status_code != 200:
                raise Exception(f"Embedding API 错误：{response.code} - {response.message}")

            # 按原始顺序返回 embeddings
            output = response.output.get("embeddings", [])
            # 按 input 顺序排序
            sorted_embeddings = sorted(output, key=lambda x: x.get("text_index", 0))
            all_embeddings.extend([item.get("embedding") for item in sorted_embeddings])

        return all_embeddings

    def embed_query(self, input: str) -> list[list[float]]:
        """为单个查询生成 embedding"""
        import dashscope
        dashscope.api_key = self.api_key

        response = dashscope.TextEmbedding.call(
            model=self.model,
            input=input,
            text_type="query"
        )

        if response.status_code == 200:
            embeddings = response.output.get("embeddings", [])
            # 返回 List[List[float]] 格式（ChromaDB 要求）
            return [embeddings[0].get("embedding")] if embeddings else [[]]
        else:
            raise Exception(f"Embedding API 错误：{response.code} - {response.message}")

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """为多个文档生成 embedding"""
        return self(documents)


# ==================== 配置区域 ====================

CONFIG = {
    # ChromaDB 配置
    "chroma_path": "./chroma_db",
    "collection_name": "legal_docs",

    # 分块配置
    "chunk_size": 500,          # 每块字符数
    "chunk_overlap": 100,       # 重叠字符数

    # 输入输出
    "input_dir": "./data",
    "metadata_file": "./data/ingest_metadata.json",

    # Embedding 模型 - 使用 DashScope
    "embedding_model": "dashscope-text-embedding-v3",
}


# ==================== 元数据提取 ====================

def generate_doc_id(file_path: str) -> str:
    """生成文档的唯一 ID"""
    return hashlib.md5(file_path.encode()).hexdigest()[:12]


def extract_metadata(file_path: str, pdf_doc: fitz.Document) -> dict:
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


# ==================== 文本提取 ====================

def extract_text_from_pdf(pdf_path: str) -> Tuple[str, List[dict]]:
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

        # 尝试提取标题（简单的启发式方法）
        # 查找大写、加粗或大字号的文本
        blocks = page.get_text("dict")["blocks"]
        potential_titles = []

        for block in blocks:
            if block.get("type") == 0:  # 文本块
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        # 大字号可能是标题
                        if span.get("size", 0) > 14:
                            potential_titles.append({
                                "text": span.get("text", "").strip(),
                                "size": span.get("size", 0),
                                "page": page_num,
                            })

        pages_info.append({
            "page_num": page_num,
            "text_length": len(page_text),
            "potential_titles": potential_titles[:5],  # 最多 5 个候选标题
        })

        if page_text.strip():
            text_parts.append(f"# 第 {page_num} 页\n\n{page_text}")

    doc.close()
    return "\n\n".join(text_parts), pages_info


# ==================== 智能分块 ====================

def detect_headings(text: str) -> List[Tuple[int, str, int]]:
    """
    检测 Markdown 风格的标题

    Returns:
        [(标题级别，标题文本，起始位置), ...]
    """
    headings = []
    # 匹配 # 到 ###### 标题
    pattern = r'^(#{1,6})\s+(.+)$'

    for match in re.finditer(pattern, text, re.MULTILINE):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.start()
        headings.append((level, title, start))

    return headings


def split_by_structure(text: str, chunk_size: int = 500, overlap: int = 100) -> List[dict]:
    """
    按文档结构智能分块

    策略：
    1. 优先在标题处切分
    2. 过大的块再按段落切分
    3. 保证每块大小适中
    """
    chunks = []
    headings = detect_headings(text)

    if not headings:
        # 没有标题，使用固定大小分块
        return split_by_fixed_size(text, chunk_size, overlap)

    # 按标题分块
    sections = []
    for i, (level, title, start) in enumerate(headings):
        if i < len(headings) - 1:
            end = headings[i + 1][2]
        else:
            end = len(text)

        section_text = text[start:end].strip()
        sections.append({
            "title": title,
            "level": level,
            "text": section_text,
            "start": start,
            "end": end,
        })

    # 处理每个 section
    for section in sections:
        section_text = section["text"]

        if len(section_text) <= chunk_size * 1.2:
            # 块大小合适，直接添加
            chunks.append({
                "text": section_text,
                "section_title": section["title"],
                "heading_level": section["level"],
            })
        else:
            # 块太大，按段落进一步分割
            paragraphs = section_text.split('\n\n')
            current_chunk = []
            current_len = 0

            for para in paragraphs:
                para_len = len(para)

                if current_len + para_len > chunk_size and current_chunk:
                    # 当前块已满，保存并开始新块
                    chunks.append({
                        "text": '\n\n'.join(current_chunk),
                        "section_title": section["title"],
                        "heading_level": section["level"],
                    })
                    # 保留部分重叠
                    if overlap > 0 and len(current_chunk) > 1:
                        current_chunk = current_chunk[-1:]
                        current_len = len(current_chunk[0])
                    else:
                        current_chunk = []
                        current_len = 0

                current_chunk.append(para)
                current_len += para_len

            # 添加最后一个块
            if current_chunk:
                chunks.append({
                    "text": '\n\n'.join(current_chunk),
                    "section_title": section["title"],
                    "heading_level": section["level"],
                })

    return chunks


def split_by_fixed_size(text: str, chunk_size: int = 500, overlap: int = 100) -> List[dict]:
    """
    按固定大小分块（简单但高效）
    """
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # 尝试在句子边界处切分
        if end < len(text):
            for sep in ['.', '!', '?', '\n']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1:
                    end = start + last_sep + 1
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append({
                "text": chunk,
                "section_title": "文档内容",
                "heading_level": 0,
            })

        start = end - overlap

    return chunks


# ==================== 主处理流程 ====================

def process_single_pdf(
    file_path: str,
    collection,
    config: dict
) -> dict:
    """
    处理单个 PDF 文件
    """
    path = Path(file_path)
    print(f"[INFO] 正在解析：{path.name}")

    try:
        # 打开 PDF
        pdf_doc = fitz.open(str(path))

        # 提取元数据
        metadata = extract_metadata(str(path), pdf_doc)

        # 提取文本
        full_text, pages_info = extract_text_from_pdf(str(path))

        pdf_doc.close()

        # 智能分块
        chunks = split_by_structure(
            full_text,
            config["chunk_size"],
            config["chunk_overlap"]
        )

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
    """
    config = config or CONFIG

    print("=" * 60)
    print("PDF Ingest 脚本 (轻量版) - 基于 PyMuPDF")
    print("=" * 60)

    # 1. 初始化向量数据库
    print(f"\n[STEP 1] 初始化 ChromaDB: {config['chroma_path']}")
    db_client = PersistentClient(path=config["chroma_path"])

    # 使用 DashScope Embedding
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("[ERROR] 未设置 DASHSCOPE_API_KEY 环境变量")
        return

    dashscope_ef = DashScopeEmbeddingFunction(api_key=api_key)
    print("       使用 DashScope Embedding (text-embedding-v3)")

    collection = db_client.get_or_create_collection(
        name=config["collection_name"],
        embedding_function=dashscope_ef,
        metadata={"description": "Legal documents and policies"}
    )

    # 显示当前集合状态
    existing_count = collection.count()
    print(f"       集合 '{config['collection_name']}' 当前文档数：{existing_count}")

    # 2. 扫描输入目录
    input_dir = Path(config["input_dir"])
    if not input_dir.exists():
        print(f"[ERROR] 输入目录不存在：{input_dir}")
        return

    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[WARN] 目录中没有找到 PDF 文件：{input_dir}")
        return

    print(f"\n[STEP 2] 发现 {len(pdf_files)} 个 PDF 文件")

    # 3. 处理每个文件
    stats_list = []
    for pdf_file in pdf_files:
        stats = process_single_pdf(
            str(pdf_file),
            collection,
            config
        )
        stats_list.append(stats)

    # 4. 保存处理日志
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

    # 5. 打印摘要
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
        description="PDF Ingest 脚本 (轻量版) - 基于 PyMuPDF"
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
        import builtins
        # 检查是否可以交互式输入
        try:
            confirm = input("[WARN] 确认要清空集合 '{}' 吗？(yes/no): ".format(args.collection))
            if confirm.lower() == 'yes':
                db_client = PersistentClient(path=args.chroma_path)
                try:
                    db_client.delete_collection(args.collection)
                    print("[OK] 已清空集合：{}".format(args.collection))
                except Exception:
                    pass
        except (EOFError, OSError):
            # 非交互式环境，直接清空
            db_client = PersistentClient(path=args.chroma_path)
            try:
                db_client.delete_collection(args.collection)
                print("[OK] 已清空集合：{}".format(args.collection))
            except Exception:
                pass

    # 运行 ingest
    ingest_all_pdfs(custom_config)
