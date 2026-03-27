"""
PDF 解析示例脚本

使用 LlamaIndex 和 PyMuPDF 解析 PDF 文档，并将内容存入 ChromaDB 向量库。
"""

import os
from pathlib import Path
from typing import Optional

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb
import fitz  # PyMuPDF


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    从 PDF 文件中提取文本内容。

    Args:
        pdf_path: PDF 文件路径

    Returns:
        提取的文本内容
    """
    text_content = []

    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, 1):
            text = page.get_text()
            if text.strip():
                text_content.append(f"--- 第 {page_num} 页 ---\n{text}")

    return "\n\n".join(text_content)


def parse_pdf_to_documents(
    pdf_path: str,
    metadata: Optional[dict] = None
) -> list[Document]:
    """
    将 PDF 解析为 LlamaIndex Document 对象列表。

    Args:
        pdf_path: PDF 文件路径
        metadata: 可选的元数据字典

    Returns:
        Document 对象列表
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")

    text = extract_text_from_pdf(str(pdf_path))

    doc_metadata = {
        "source": str(pdf_path),
        "file_name": pdf_path.name,
        **(metadata or {})
    }

    return [Document(text=text, metadata=doc_metadata)]


def setup_chroma_vector_store(
    persist_dir: str = "./chroma_db",
    collection_name: str = "documents"
) -> VectorStoreIndex:
    """
    设置 ChromaDB 向量存储并返回索引对象。

    Args:
        persist_dir: ChromaDB 持久化目录
        collection_name: 集合名称

    Returns:
        VectorStoreIndex 对象
    """
    # 初始化 ChromaDB 客户端
    client = chromadb.PersistentClient(path=persist_dir)

    # 获取或创建集合
    collection = client.get_or_create_collection(name=collection_name)

    # 创建向量存储
    vector_store = ChromaVectorStore(chroma_collection=collection)

    # 创建存储上下文
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    return storage_context


def index_pdf(
    pdf_path: str,
    persist_dir: str = "./chroma_db",
    collection_name: str = "documents",
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> VectorStoreIndex:
    """
    将 PDF 文档索引到 ChromaDB 向量库中。

    Args:
        pdf_path: PDF 文件路径
        persist_dir: ChromaDB 持久化目录
        collection_name: 集合名称
        chunk_size: 文本分块大小
        chunk_overlap: 分块重叠大小

    Returns:
        构建好的 VectorStoreIndex 对象
    """
    # 解析 PDF
    documents = parse_pdf_to_documents(pdf_path)

    # 文本分块
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    nodes = splitter.get_nodes_from_documents(documents)

    # 设置向量存储
    storage_context = setup_chroma_vector_store(persist_dir, collection_name)

    # 创建索引（需要配置 LLM 和 Embedding）
    # 注意：需要设置 OPENAI_API_KEY 环境变量
    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
    )

    print(f"✓ 已成功索引 {len(nodes)} 个文本块")
    return index


def query_index(
    query: str,
    index: VectorStoreIndex,
    top_k: int = 3
) -> str:
    """
    对索引进行查询并返回答案。

    Args:
        query: 查询问题
        index: VectorStoreIndex 对象
        top_k: 返回的最相似结果数量

    Returns:
        生成的回答
    """
    from llama_index.core import Settings
    from llama_index.llms.dashscope import DashScope
    from llama_index.embeddings.dashscope import DashScopeEmbedding

    # 配置 LLM 和 Embedding（通义千问）
    Settings.llm = DashScope(model="qwen-plus")
    Settings.embed_model = DashScopeEmbedding(model="text-embedding-v3")

    # 创建查询引擎
    query_engine = index.as_query_engine(similarity_top_k=top_k)
    response = query_engine.query(query)

    return str(response)


def main():
    """主函数 - 演示完整的 PDF 解析和索引流程。"""
    from llama_index.core import Settings
    from llama_index.llms.dashscope import DashScope
    from llama_index.embeddings.dashscope import DashScopeEmbedding

    # 环境变量检查
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("[WARN] 未设置 DASHSCOPE_API_KEY 环境变量")
        print("   请在 .env 文件中配置或导出环境变量")
        return

    # 配置 LLM 和 Embedding
    Settings.llm = DashScope(model="qwen-plus", api_key=api_key)
    Settings.embed_model = DashScopeEmbedding(model="text-embedding-v3", api_key=api_key)

    # 检查 data 目录
    data_dir = Path("data")
    if not data_dir.exists():
        data_dir.mkdir()
        print("[WARN] data/ 目录不存在，已创建空目录")
        print("   请将 PDF 文件放入 data/ 目录后重试")
        return

    # 查找所有 PDF 文件
    pdf_files = list(data_dir.glob("*.pdf"))

    if not pdf_files:
        print("[WARN] data/ 目录中没有找到 PDF 文件")
        print("   请将 PDF 文件放入 data/ 目录后重试")
        return

    print(f"[INFO] 找到 {len(pdf_files)} 个 PDF 文件:")
    for f in pdf_files:
        print(f"       - {f.name}")

    # 索引所有 PDF
    all_nodes = []

    for pdf_path in pdf_files:
        print(f"\n[INFO] 正在解析：{pdf_path.name}")
        try:
            documents = parse_pdf_to_documents(str(pdf_path))

            # 文本分块
            splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
            nodes = splitter.get_nodes_from_documents(documents)
            all_nodes.extend(nodes)
            print(f"       提取了 {len(nodes)} 个文本块")
        except Exception as e:
            print(f"       [ERROR] 解析失败：{e}")

    if not all_nodes:
        print("\n[ERROR] 没有成功索引任何文档")
        return

    # 设置向量存储
    print(f"\n[INFO] 正在存入 ChromaDB...")
    storage_context = setup_chroma_vector_store("./chroma_db", "documents")

    # 创建索引
    index = VectorStoreIndex(nodes=all_nodes, storage_context=storage_context)

    print(f"\n[OK] 索引完成！共 {len(all_nodes)} 个文本块")

    # 示例查询
    print("\n" + "=" * 50)
    print("示例查询")
    print("=" * 50)

    queries = [
        "这份文档主要讲了什么？",
        "有哪些关键规定？",
    ]

    for q in queries:
        print(f"\n问：{q}")
        query_engine = index.as_query_engine(similarity_top_k=3)
        response = query_engine.query(q)
        print(f"答：{response}")


if __name__ == "__main__":
    main()
