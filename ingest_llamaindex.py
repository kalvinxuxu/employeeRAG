"""
PDF Ingest 脚本 - 基于 LlamaIndex + DashScope

使用通义千问 API 进行 Embedding，无需本地模型下载。

用法:
    python ingest_llamaindex.py                    # 使用默认配置
    python ingest_llamaindex.py -i ./data          # 指定输入目录
    python ingest_llamaindex.py --clear-collection # 清空集合后重新索引
"""

import os
import sys
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# 设置 UTF-8 编码输出 (Windows)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

import fitz  # PyMuPDF
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import StorageContext, VectorStoreIndex, Settings
from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.dashscope import DashScopeEmbedding
import chromadb


# ==================== 配置区域 ====================

CONFIG = {
    # ChromaDB 配置
    "chroma_path": "./chroma_db",
    "collection_name": "legal_docs",

    # 分块配置
    "chunk_size": 512,
    "chunk_overlap": 50,

    # 输入输出
    "input_dir": "./data",
    "metadata_file": "./data/ingest_metadata.json",

    # 模型配置
    "llm_model": "qwen-plus",
    "embedding_model": "text-embedding-v3",
}


# ==================== 元数据提取 ====================

def generate_doc_id(file_path: str) -> str:
    """生成文档的唯一 ID"""
    return hashlib.md5(file_path.encode()).hexdigest()[:12]


def extract_metadata(file_path: str, pdf_doc: fitz.Document) -> dict:
    """提取 PDF 文档元数据"""
    path = Path(file_path)
    stat = path.stat()
    pdf_metadata = pdf_doc.metadata or {}

    return {
        "file_name": path.name,
        "file_size": stat.st_size,
        "num_pages": len(pdf_doc),
        "title": pdf_metadata.get("title", path.stem),
        "author": pdf_metadata.get("author", ""),
        "doc_id": generate_doc_id(str(path.absolute())),
        "source_path": str(path),
        "ingested_at": datetime.now().isoformat(),
    }


# ==================== 文本提取 ====================

def extract_text_from_pdf(pdf_path: str) -> str:
    """从 PDF 提取文本"""
    doc = fitz.open(pdf_path)
    text_parts = []

    for page_num, page in enumerate(doc, 1):
        page_text = page.get_text("text")
        if page_text.strip():
            text_parts.append(f"[第 {page_num} 页]\n{page_text}")

    doc.close()
    return "\n\n".join(text_parts)


# ==================== 主处理流程 ====================

def process_single_pdf(
    file_path: str,
    index: VectorStoreIndex,
    config: dict
) -> dict:
    """处理单个 PDF 文件"""
    path = Path(file_path)
    print(f"[INFO] 正在解析：{path.name}")

    try:
        # 打开 PDF
        pdf_doc = fitz.open(str(path))

        # 提取元数据
        metadata = extract_metadata(str(path), pdf_doc)

        # 提取文本
        full_text = extract_text_from_pdf(str(path))
        pdf_doc.close()

        # 创建 LlamaIndex Document
        doc = Document(
            text=full_text,
            metadata=metadata,
            metadata_template="[{key}]: {value}",
        )

        # 分块
        splitter = SentenceSplitter(
            chunk_size=config["chunk_size"],
            chunk_overlap=config["chunk_overlap"],
        )
        nodes = splitter.get_nodes_from_documents([doc])

        # 插入索引
        index.insert_nodes(nodes)

        stats = {
            "file_name": path.name,
            "status": "success",
            "num_pages": metadata["num_pages"],
            "num_chunks": len(nodes),
            "doc_id": metadata["doc_id"],
            "error": None,
        }

        print(f"       [OK] 解析完成：{len(nodes)} 个文本块 / {metadata['num_pages']} 页")
        return stats

    except Exception as e:
        print(f"       [FAIL] 解析失败：{str(e)}")
        return {
            "file_name": path.name,
            "status": "failed",
            "error": str(e),
        }


def ingest_all_pdfs(config: dict = None):
    """批量处理目录中的所有 PDF 文件"""
    config = config or CONFIG

    print("=" * 60)
    print("PDF Ingest 脚本 - LlamaIndex + DashScope")
    print("=" * 60)

    # 1. 检查 API Key
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("[ERROR] 未设置 DASHSCOPE_API_KEY 环境变量")
        print("        请在 .env 文件中配置 API Key")
        return

    print(f"\n[STEP 1] 初始化 DashScope Embedding")
    print(f"       API Key: {api_key[:15]}...")

    # 2. 配置 LlamaIndex
    Settings.llm = DashScope(model=config["llm_model"], api_key=api_key)
    Settings.embed_model = DashScopeEmbedding(model=config["embedding_model"], api_key=api_key)

    # 3. 初始化 ChromaDB
    print(f"\n[STEP 2] 初始化 ChromaDB: {config['chroma_path']}")
    db_client = chromadb.PersistentClient(path=config["chroma_path"])

    collection = db_client.get_or_create_collection(
        name=config["collection_name"],
        metadata={"description": "Legal documents and policies"},
    )

    existing_count = collection.count()
    print(f"       集合 '{config['collection_name']}' 当前文档数：{existing_count}")

    # 4. 创建向量存储和索引
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        storage_context=storage_context,
    )

    # 5. 扫描输入目录
    input_dir = Path(config["input_dir"])
    if not input_dir.exists():
        print(f"[ERROR] 输入目录不存在：{input_dir}")
        return

    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[WARN] 目录中没有找到 PDF 文件：{input_dir}")
        return

    print(f"\n[STEP 3] 发现 {len(pdf_files)} 个 PDF 文件")

    # 6. 处理每个文件
    stats_list = []
    for pdf_file in pdf_files:
        stats = process_single_pdf(
            str(pdf_file),
            index,
            config
        )
        stats_list.append(stats)

    # 7. 保存处理日志
    summary = {
        "ingested_at": datetime.now().isoformat(),
        "input_dir": str(input_dir.absolute()),
        "total_files": len(pdf_files),
        "successful": sum(1 for s in stats_list if s["status"] == "success"),
        "failed": sum(1 for s in stats_list if s["status"] == "failed"),
        "total_chunks": collection.count() - existing_count,
        "files": stats_list,
    }

    with open(config["metadata_file"], 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 8. 打印摘要
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

    parser = argparse.ArgumentParser(description="PDF Ingest 脚本 - LlamaIndex + DashScope")
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
        default=512,
        help="分块大小 (默认：512)"
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="分块重叠 (默认：50)"
    )
    parser.add_argument(
        "--clear-collection",
        action="store_true",
        help="清空现有集合后重新索引"
    )

    args = parser.parse_args()

    custom_config = {
        **CONFIG,
        "input_dir": args.input_dir,
        "chroma_path": args.chroma_path,
        "collection_name": args.collection,
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
    }

    # 清空集合
    if args.clear_collection:
        db_client = chromadb.PersistentClient(path=args.chroma_path)
        try:
            db_client.delete_collection(args.collection)
            print(f"[OK] 已清空集合：{args.collection}")
        except Exception:
            pass

    # 运行 ingest
    ingest_all_pdfs(custom_config)
