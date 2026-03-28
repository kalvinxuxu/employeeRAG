"""
Streamlit RAG 聊天界面 - 基于 ChromaDB 的 PDF 问答系统

功能:
- 左侧聊天框与 AI 对话
- 右侧 PDF 预览插件
- 点击 AI 引用时显示来源文件名和对应 PDF 页面
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import streamlit as st
import chromadb
import fitz  # PyMuPDF

# 导入混合检索器
try:
    from retriever import HybridRetriever
    HYBRID_RETRIEVER_AVAILABLE = True
except ImportError:
    HYBRID_RETRIEVER_AVAILABLE = False

# 导入对话管理器 - 直接使用 get_conversation_manager 函数
CONVERSATION_MANAGER_AVAILABLE = True  # conversation_manager.py 存在即可用


# ==================== 配置 ====================

CONFIG = {
    "chroma_path": "./chroma_db",
    "collection_name": "legal_docs",
    "pdf_base_dir": "./data",
    "llm_model": "qwen-plus",
    "embedding_model": "text-embedding-v3",

    # 混合检索配置
    "use_hybrid_search": True,      # 是否启用混合检索
    "use_rerank": False,            # 是否启用 Rerank（需要安装 FlagEmbedding + 连接 HuggingFace）
    "rerank_top_n": 20,             # Rerank 候选数量
    "vector_weight": 0.5,           # 向量检索权重
    "keyword_weight": 0.5,          # 关键词检索权重

    # 响应速度优化配置
    "use_cache": True,              # 是否启用语义缓存
    "cache_path": "./semantic_cache",  # 缓存路径
    "similarity_threshold": 0.95,   # 缓存相似度阈值
    "use_streaming": True,          # 是否启用流式输出
}


# ==================== 自定义 Embedding 函数 ====================

class DashScopeEmbeddingFunction:
    """DashScope embedding 函数，用于 ChromaDB 查询"""

    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-v3"):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.model = model
        self._client = None

    def name(self) -> str:
        """返回 embedding 函数名称"""
        return f"dashscope-{self.model}"

    def _get_client(self):
        """懒加载 DashScope 客户端"""
        if self._client is None:
            import dashscope
            self._client = dashscope.TextEmbedding
        return self._client

    def __call__(self, input: List[str]) -> List[List[float]]:
        """生成 embedding"""
        import dashscope
        dashscope.api_key = self.api_key

        # 调用 DashScope API
        response = dashscope.TextEmbedding.call(
            model=self.model,
            input=input,
            text_type="document"
        )

        if response.status_code == 200:
            # 按原始顺序返回 embeddings
            output = response.output.get("embeddings", [])
            # 按 input 顺序排序
            sorted_embeddings = sorted(output, key=lambda x: x.get("text_index", 0))
            return [item.get("embedding") for item in sorted_embeddings]
        else:
            raise Exception(f"Embedding API 错误：{response.code} - {response.message}")

    def embed_query(self, input: str) -> List[List[float]]:
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

    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """为多个文档生成 embedding"""
        return self(documents)


# ==================== ChromaDB 查询 ====================

@st.cache_resource
def get_hybrid_retriever():
    """获取混合检索器实例"""
    if not HYBRID_RETRIEVER_AVAILABLE:
        return None

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None

    retriever = HybridRetriever(
        chroma_path=CONFIG["chroma_path"],
        collection_name=CONFIG["collection_name"],
        api_key=api_key,
        use_rerank=CONFIG.get("use_rerank", False),
        vector_weight=CONFIG.get("vector_weight", 0.5),
        keyword_weight=CONFIG.get("keyword_weight", 0.5),
    )
    return retriever


@st.cache_resource
def get_conversation_manager():
    """获取对话管理器实例（使用 cache_resource 缓存，避免 Streamlit 重新运行时重置）"""
    if not CONVERSATION_MANAGER_AVAILABLE:
        return None

    from conversation_manager import get_conversation_manager as create_manager

    # 使用 persist_to_file=True 确保持久化
    return create_manager(max_turns=5, persist_to_file=True)


@st.cache_resource
def get_chroma_collection():
    """获取 ChromaDB 集合（向后兼容）"""
    client = chromadb.PersistentClient(path=CONFIG["chroma_path"])

    # 使用 DashScope Embedding（与 ingest.py 保持一致）
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        st.error("未设置 DASHSCOPE_API_KEY 环境变量")
        return None

    dashscope_ef = DashScopeEmbeddingFunction(api_key=api_key)

    collection = client.get_or_create_collection(
        name=CONFIG["collection_name"],
        embedding_function=dashscope_ef,
    )
    return collection


def extract_page_number_from_chunk(text: str) -> int:
    """
    从 chunk 文本中提取页码
    格式：# 第 X 页  或 # 第 X ҳ（编码问题）
    """
    import re
    # 尝试匹配 "第 X 页" 或 "第 X ҳ" 格式（允许空格）
    match = re.search(r'第\s*(\d+)\s*(页|ҳ)', text)
    if match:
        return int(match.group(1))
    return 1  # 默认第一页


def query_chroma(query: str, top_k: int = 5) -> tuple[str, list[dict]]:
    """
    查询 ChromaDB 并返回结果（支持混合检索和元数据过滤）

    Args:
        query: 查询问题
        top_k: 返回的最相似结果数量

    Returns:
        (上下文文本，引用列表)
    """
    # 构建元数据过滤条件
    filter_metadata = {}
    if st.session_state.filter_department:
        filter_metadata["department"] = st.session_state.filter_department
    if st.session_state.filter_category:
        filter_metadata["category"] = st.session_state.filter_category

    # 优先使用混合检索器
    retriever = get_hybrid_retriever()
    if retriever and CONFIG.get("use_hybrid_search", True):
        try:
            context, citations = retriever.retrieve_with_context(
                query=query,
                top_k=top_k,
                rerank_top_n=CONFIG.get("rerank_top_n", 20),
                filter_metadata=filter_metadata if filter_metadata else None
            )
            return context, citations
        except Exception as e:
            # 混合检索失败，降级到纯向量检索
            st.warning(f"混合检索失败，使用向量检索：{e}")

    # 降级到纯向量检索
    collection = get_chroma_collection()
    if not collection:
        return "", []

    # 查询向量库
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    # 构建上下文和引用
    context_parts = []
    citations = []

    if results["documents"] and results["documents"][0]:
        for idx, (doc, metadata, distance) in enumerate(
            zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )
        ):
            # 相似度分数
            similarity = 1 - distance

            # 从 metadata 获取页码（优先从 section_title 中提取）
            page_num = metadata.get("page_num")
            if page_num is None:
                # 从 section_title 中提取页码（格式："第 X 页" 或 "第 X ҳ"）
                section_title = metadata.get("section_title", "")
                match = re.search(r'第\s*(\d+)\s*(页|ҳ)', section_title)
                if match:
                    page_num = int(match.group(1))
                else:
                    # 从 chunk 文本中提取页码
                    page_num = extract_page_number_from_chunk(doc)

            page_range = metadata.get("page_range", str(page_num))

            # 引用信息
            citation = {
                "id": idx + 1,
                "file_name": metadata.get("file_name", "未知"),
                "section_title": metadata.get("section_title", ""),
                "hierarchy_path": metadata.get("hierarchy_path", ""),  # 层级路径
                "similarity": round(similarity * 100, 1),
                "chunk_id": metadata.get("chunk_id", 0),
                "doc_id": metadata.get("doc_id", ""),
                "source_path": metadata.get("source_path", ""),
                "page_num": page_num,
                "page_range": page_range,  # 页码范围
                "chunk_text": doc,  # 保存原始 chunk 文本用于高亮
                "search_source": "vector",  # 检索来源标记
            }
            citations.append(citation)

            # 上下文内容
            context_parts.append(f"[{idx + 1}] {doc}")

    context = "\n\n".join(context_parts)
    return context, citations


# ==================== LLM 调用 ====================

def call_llm(query: str, context: str) -> str:
    """
    调用 LLM 生成回答（非流式，用于缓存）

    Args:
        query: 用户问题
        context: 检索到的上下文

    Returns:
        AI 回答
    """
    from llama_index.llms.dashscope import DashScope

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return "[错误] 未设置 DASHSCOPE_API_KEY 环境变量"

    llm = DashScope(model=CONFIG["llm_model"], api_key=api_key)

    prompt = f"""基于以下参考资料回答问题。如果资料中没有相关信息，请直接告知用户。

参考资料:
{context}

用户问题：{query}

请用简洁清晰的中文回答，并在引用处标注来源编号（如 [1]、[2]）。"""

    response = llm.complete(prompt)
    return str(response)


def call_llm_streaming(query: str, context: str):
    """
    流式调用 LLM 生成回答

    Args:
        query: 用户问题
        context: 检索到的上下文

    Yields:
        逐个生成的文本片段
    """
    try:
        from llama_index.llms.dashscope import DashScope
    except ImportError:
        yield "[错误] 无法导入 DashScope LLM"
        return

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        yield "[错误] 未设置 DASHSCOPE_API_KEY 环境变量"
        return

    llm = DashScope(model=CONFIG["llm_model"], api_key=api_key)

    prompt = f"""基于以下参考资料回答问题。如果资料中没有相关信息，请直接告知用户。

参考资料:
{context}

用户问题：{query}

请用简洁清晰的中文回答，并在引用处标注来源编号（如 [1]、[2]）。"""

    try:
        # 使用 stream 方法进行流式输出
        response = llm.stream_complete(prompt)

        previous_text = ""
        for chunk in response:
            # llama_index 的 stream_complete 返回的 text 是累积的完整文本
            # 需要计算增量
            current_text = chunk.text if hasattr(chunk, 'text') and chunk.text else ""
            if current_text:
                delta_text = current_text[len(previous_text):]
                previous_text = current_text
                if delta_text:
                    yield delta_text

    except Exception as e:
        yield f"\n\n[流式输出错误：{str(e)}]"


# ==================== PDF 预览功能 ====================

def get_pdf_path(file_name: str) -> Optional[Path]:
    """根据文件名查找 PDF 路径"""
    # 在基础目录中查找
    base_dir = Path(CONFIG["pdf_base_dir"])
    if base_dir.exists():
        pdf_path = base_dir / file_name
        if pdf_path.exists():
            return pdf_path

    # 在 data 子目录中查找
    for subdir in base_dir.iterdir():
        if subdir.is_dir():
            pdf_path = subdir / file_name
            if pdf_path.exists():
                return pdf_path

    return None


def find_text_in_pdf(pdf_path: Path, text: str, max_pages: int = 50) -> Optional[int]:
    """
    在 PDF 中搜索文本，返回找到的页码

    Args:
        pdf_path: PDF 文件路径
        text: 要搜索的文本
        max_pages: 最多搜索的页数

    Returns:
        找到的页码（从 1 开始），如果未找到则返回 None
    """
    try:
        doc = fitz.open(pdf_path)
        clean_text = ' '.join(text.strip().split())

        # 限制搜索范围
        pages_to_search = min(len(doc), max_pages)

        for page_num in range(pages_to_search):
            page = doc[page_num]
            page_text = page.get_text()

            # 尝试多种搜索方式
            rects = page.search_for(clean_text[:200])
            if not rects:
                rects = page.search_for(text[:200])

            # 如果没找到，尝试清理后的文本（移除换行和多余空格）
            if not rects:
                # 将 PDF 文本也进行标准化处理
                normalized_page_text = ' '.join(page_text.split())
                normalized_search = ' '.join(text.split())
                if normalized_search[:200] in normalized_page_text:
                    doc.close()
                    return page_num + 1

            # 尝试关键词子串匹配
            if not rects:
                # 提取关键句子（按标点分割）
                for sep in ['。', '！', '？', '.', '!', '?', '\n']:
                    parts = text.split(sep)
                    for part in parts:
                        part = part.strip()
                        if 10 < len(part) < 150:
                            found = page.search_for(part[:150])
                            if found:
                                rects = found
                                break
                    if rects:
                        break

            # 如果找到，返回页码（从 1 开始）
            if rects:
                doc.close()
                return page_num + 1

        doc.close()
        return None

    except Exception as e:
        print(f"搜索文本失败：{e}")
        return None


def extract_page_text(pdf_path: str, page_num: int) -> str:
    """提取 PDF 指定页面的文本"""
    try:
        doc = fitz.open(pdf_path)
        if page_num < 1 or page_num > len(doc):
            return ""
        page = doc[page_num - 1]
        text = page.get_text()
        doc.close()
        return text
    except Exception as e:
        return f"[读取失败]: {str(e)}"


def find_text_in_page(page: fitz.Page, text: str) -> List[fitz.Rect]:
    """
    在 PDF 页面中查找文本，返回匹配的矩形区域列表

    Args:
        page: PDF 页面对象
        text: 要查找的文本

    Returns:
        匹配的矩形区域列表，用于高亮显示
    """
    # 搜索文本，返回矩形区域
    rects = []

    # 清理文本：移除多余的空白和换行
    search_text = ' '.join(text.strip().split())

    # 尝试搜索原始文本
    text_instances = page.search_for(text)
    if text_instances:
        rects.extend(text_instances)

    # 如果没有找到，尝试用清理后的文本搜索
    if not rects:
        text_instances = page.search_for(search_text[:100])  # 限制长度避免过长
        if text_instances:
            rects.extend(text_instances)

    # 如果还是没有找到，尝试逐句搜索
    if not rects:
        sentences = re.split(r'[。！？.!?\n]', text[:500])
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10:  # 只搜索有意义的句子
                instances = page.search_for(sentence)
                if instances:
                    rects.extend(instances)
                    break  # 找到一个句子就够了

    return rects


def render_pdf_with_highlight(pdf_path: str, page_num: int,
                               highlight_text: Optional[str] = None,
                               zoom: float = 2.0) -> Optional[bytes]:
    """
    渲染 PDF 页面为图片，支持高亮文本

    Args:
        pdf_path: PDF 文件路径
        page_num: 页码（从 1 开始）
        highlight_text: 要高亮的文本
        zoom: 缩放比例

    Returns:
        PNG 图片字节数据
    """
    import traceback

    try:
        doc = fitz.open(pdf_path)

        if page_num < 1 or page_num > len(doc):
            st.warning(f"页码 {page_num} 超出范围 (1-{len(doc)})")
            doc.close()
            return None

        page = doc[page_num - 1]

        # 如果需要高亮，先查找并添加高亮注释
        if highlight_text:
            try:
                # 清理文本用于搜索
                clean_text = ' '.join(highlight_text.strip().split())

                # 搜索文本位置
                rects = []

                # 方法 1: 搜索原始文本
                found = page.search_for(highlight_text[:200])
                if found:
                    rects.extend(found)

                # 方法 2: 搜索清理后的文本
                if not rects and clean_text != highlight_text:
                    found = page.search_for(clean_text[:200])
                    if found:
                        rects.extend(found)

                # 方法 3: 逐句搜索（按标点分割）
                if not rects:
                    for sep in ['。', '！', '？', '.', '!', '?', '\n']:
                        parts = highlight_text.split(sep)
                        for part in parts:
                            part = part.strip()
                            if 20 < len(part) < 200:
                                found = page.search_for(part)
                                if found:
                                    rects.extend(found)
                                    break
                        if rects:
                            break

                # 方法 4: 尝试更短的关键片段（10-20 字）
                if not rects:
                    # 提取 20-50 字的子串进行搜索
                    for i in range(0, min(len(highlight_text) - 20, 100), 10):
                        sub = highlight_text[i:i+30].strip()
                        if len(sub) >= 15:
                            found = page.search_for(sub[:150])
                            if found:
                                rects.extend(found)
                                break

                # 方法 5: 在 PDF 页面文本中查找包含关系
                if not rects:
                    page_text = page.get_text()
                    normalized_page = ' '.join(page_text.split())
                    normalized_search = ' '.join(highlight_text.split())
                    # 检查标准化后的文本是否包含
                    if len(normalized_search) > 10 and normalized_search[:50] in normalized_page:
                        # 找到包含位置后，尝试用子串定位
                        for sep in ['。', '！', '？', '.', '!', '?']:
                            parts = highlight_text.split(sep)
                            for part in parts:
                                part = part.strip()
                                if 10 < len(part) < 100:
                                    found = page.search_for(part[:100])
                                    if found:
                                        rects.extend(found)
                                        break
                            if rects:
                                break

                # 添加高亮注释（黄色）
                for rect in rects:
                    try:
                        # 创建高亮注释
                        annot = page.add_highlight_annot(rect)
                        annot.set_colors(stroke=(1, 1, 0))  # 黄色
                        annot.update()
                    except Exception as e:
                        print(f"添加高亮失败：{e}")

                if rects:
                    print(f"找到 {len(rects)} 处高亮位置")
                else:
                    print("未找到匹配的文本位置")

            except Exception as e:
                print(f"高亮处理异常：{e}")
                print(traceback.format_exc())

        # 渲染为图片
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        doc.close()
        return pix.tobytes("png")

    except Exception as e:
        st.error(f"PDF 渲染失败：{str(e)}")
        print(traceback.format_exc())
        return None


# ==================== Streamlit 界面 ====================

def init_session_state():
    """初始化会话状态"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "selected_pdf" not in st.session_state:
        st.session_state.selected_pdf = None
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = 1
    if "citations" not in st.session_state:
        st.session_state.citations = []
    if "highlight_text" not in st.session_state:
        st.session_state.highlight_text = None  # 要高亮的文本
    if "active_citation" not in st.session_state:
        st.session_state.active_citation = None  # 当前选中的引用
    if "scroll_to_pdf" not in st.session_state:
        st.session_state.scroll_to_pdf = False  # 是否需要滚动到 PDF 预览
    if "citation_to_expand" not in st.session_state:
        st.session_state.citation_to_expand = False  # 是否需要展开引用列表
    if "kb_pdfs" not in st.session_state:
        st.session_state.kb_pdfs = []  # 知识库中的 PDF 列表
    if "kb_refresh" not in st.session_state:
        st.session_state.kb_refresh = 0  # 用于触发刷新

    # 元数据过滤相关
    if "filter_department" not in st.session_state:
        st.session_state.filter_department = None  # 选中部门
    if "filter_category" not in st.session_state:
        st.session_state.filter_category = None    # 选中类别
    if "metadata_options" not in st.session_state:
        st.session_state.metadata_options = {"departments": [], "categories": []}  # 可选的元数据值

    # ===== 新增功能相关 =====

    # 多轮对话管理
    if "session_id" not in st.session_state:
        import uuid
        st.session_state.session_id = str(uuid.uuid4())[:8]  # 短会话 ID
    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []  # 对话历史（最近 5 轮）

    # 反思链路功能
    if "enable_reasoning" not in st.session_state:
        st.session_state.enable_reasoning = False  # 是否启用反思链路（默认关闭）

    # 反馈收集
    if "feedback_submitted" not in st.session_state:
        st.session_state.feedback_submitted = {}  # 已提交反馈的消息 ID


def get_knowledge_base_pdfs() -> List[dict]:
    """从 ChromaDB 获取知识库中已有的 PDF 列表"""
    try:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return []

        # 创建 embedding 函数
        from chromadb import PersistentClient

        db_client = PersistentClient(path=CONFIG["chroma_path"])
        collection = db_client.get_collection(name=CONFIG["collection_name"])

        # 获取所有元数据中的文件名
        all_metadata = collection.get(include=["metadatas"])

        # 提取唯一的文件名
        pdf_set = set()
        pdf_info = {}

        for i, meta in enumerate(all_metadata.get("metadatas", [])):
            if meta and "file_name" in meta:
                file_name = meta["file_name"]
                if file_name not in pdf_set:
                    pdf_set.add(file_name)
                    pdf_info[file_name] = {
                        "file_name": file_name,
                        "doc_id": meta.get("doc_id", ""),
                        "num_pages": meta.get("num_pages", 0),
                        "chunk_count": 1,
                        "department": meta.get("department"),
                        "category": meta.get("category"),
                    }
                else:
                    # 累加 chunk 数量
                    if file_name in pdf_info:
                        pdf_info[file_name]["chunk_count"] += 1

        return list(pdf_info.values())

    except Exception as e:
        print(f"获取知识库 PDF 列表失败：{e}")
        return []


def get_metadata_options() -> Dict[str, List[str]]:
    """从 ChromaDB 获取元数据选项（部门、类别）"""
    try:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return {"departments": [], "categories": []}

        from chromadb import PersistentClient

        db_client = PersistentClient(path=CONFIG["chroma_path"])
        collection = db_client.get_collection(name=CONFIG["collection_name"])

        # 获取所有元数据
        all_metadata = collection.get(include=["metadatas"])

        # 提取唯一的部门和类别
        departments = set()
        categories = set()

        for meta in all_metadata.get("metadatas", []):
            if meta:
                if meta.get("department"):
                    departments.add(meta["department"])
                if meta.get("category"):
                    categories.add(meta["category"])

        return {
            "departments": sorted(list(departments)),
            "categories": sorted(list(categories)),
        }

    except Exception as e:
        print(f"获取元数据选项失败：{e}")
        return {"departments": [], "categories": []}


def render_knowledge_base_panel():
    """渲染知识库管理面板"""
    with st.container():
        st.subheader("📚 知识库管理")

        # 刷新按钮
        if st.button("🔄 刷新列表", key="refresh_kb"):
            st.session_state.kb_refresh += 1
            st.rerun()

        # 获取并显示 PDF 列表
        pdfs = get_knowledge_base_pdfs()
        st.session_state.kb_pdfs = pdfs

        if not pdfs:
            st.info("知识库中暂无 PDF 文档")
        else:
            st.caption(f"共 {len(pdfs)} 个文档")

            # 显示 PDF 列表
            for pdf in pdfs:
                file_name = pdf["file_name"]
                chunks = pdf.get("chunk_count", 0)
                pages = pdf.get("num_pages", 0)

                with st.container():
                    st.markdown(f"**📄 {file_name}**")
                    meta_text = []
                    if pages:
                        meta_text.append(f"{pages}页")
                    if chunks:
                        meta_text.append(f"{chunks}个片段")
                    if meta_text:
                        st.caption(" · ".join(meta_text))

                    # 查看按钮
                    if st.button("👁️ 查看", key=f"view_kb_{file_name}", type="tertiary"):
                        st.session_state.selected_pdf = file_name
                        st.session_state.selected_page = 1
                        st.session_state.scroll_to_pdf = True
                        st.rerun()

                    st.divider()

        # PDF 上传/导入区域
        st.divider()
        st.subheader("📥 导入新文档")

        # 文件上传器
        uploaded_files = st.file_uploader(
            "上传 PDF 文件",
            type=["pdf"],
            accept_multiple_files=True,
            key="upload_pdf"
        )

        if uploaded_files:
            # 确保 data 目录存在
            data_dir = Path(CONFIG["pdf_base_dir"])
            data_dir.mkdir(parents=True, exist_ok=True)

            for uploaded_file in uploaded_files:
                file_path = data_dir / uploaded_file.name

                # 如果文件已存在，跳过
                if file_path.exists():
                    st.warning(f"⚠️ {uploaded_file.name} 已存在，跳过")
                    continue

                # 保存文件
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.success(f"✅ {uploaded_file.name} 已保存到 {data_dir}")

            # 提示用户运行 ingest
            st.info(
                "📌 文件已保存到 `./data` 目录。\n\n"
                "请在终端运行以下命令将其加入知识库：\n\n"
                "```bash\npython ingest.py -i ./data\n```\n\n"
                "或者使用快速导入（需要配置 API Key）："
            )

            if st.button("⚡ 快速导入到知识库", key="quick_ingest"):
                quick_ingest_pdfs()


def quick_ingest_pdfs():
    """快速导入 PDF 到知识库（简化版 ingest）"""
    try:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            st.error("❌ 未设置 DASHSCOPE_API_KEY 环境变量")
            return

        # 导入 ingest 模块
        import importlib
        import ingest

        # 重新加载模块以获取最新代码
        importlib.reload(ingest)

        custom_config = {
            "chroma_path": CONFIG["chroma_path"],
            "collection_name": CONFIG["collection_name"],
            "input_dir": CONFIG["pdf_base_dir"],
            "chunk_size": 500,
            "chunk_overlap": 100,
        }

        with st.spinner("正在导入 PDF 到知识库..."):
            # 调用 ingest 函数
            result = ingest.ingest_all_pdfs(custom_config)

            if result:
                st.success(f"✅ 导入完成！新增 {result.get('total_chunks', 0)} 个文本块")
                st.session_state.kb_refresh += 1

    except Exception as e:
        st.error(f"导入失败：{str(e)}")
        st.info("💡 请确保已在终端配置好 DASHSCOPE_API_KEY 环境变量")


def render_filter_panel():
    """渲染元数据过滤面板"""
    with st.container():
        st.subheader("🔍 检索过滤")

        # 获取元数据选项
        if not st.session_state.metadata_options["departments"]:
            st.session_state.metadata_options = get_metadata_options()

        departments = st.session_state.metadata_options["departments"]
        categories = st.session_state.metadata_options["categories"]

        if not departments and not categories:
            st.info("暂无可过滤的元数据")
            return

        # 部门过滤
        if departments:
            selected_dept = st.selectbox(
                "部门",
                options=["全部"] + sorted(departments),
                index=0,
                key="filter_dept_select"
            )
            if selected_dept != "全部":
                st.session_state.filter_department = selected_dept
            else:
                st.session_state.filter_department = None

        # 类别过滤
        if categories:
            selected_cat = st.selectbox(
                "类别",
                options=["全部"] + sorted(categories),
                index=0,
                key="filter_cat_select"
            )
            if selected_cat != "全部":
                st.session_state.filter_category = selected_cat
            else:
                st.session_state.filter_category = None

        # 清除过滤按钮
        if st.session_state.filter_department or st.session_state.filter_category:
            if st.button("清除所有过滤", key="clear_filters"):
                st.session_state.filter_department = None
                st.session_state.filter_category = None
                st.rerun()

        # 显示当前过滤状态
        filters_applied = []
        if st.session_state.filter_department:
            filters_applied.append(f"部门：{st.session_state.filter_department}")
        if st.session_state.filter_category:
            filters_applied.append(f"类别：{st.session_state.filter_category}")

        if filters_applied:
            st.caption("当前过滤：" + " | ".join(filters_applied))


def render_chat_panel():
    """渲染左侧聊天面板（集成多轮对话、反思链路、反馈收集）"""
    with st.container():
        st.subheader("💬 AI 问答")

        # 显示历史消息
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

                # 如果是 AI 消息且有引用，显示引用来源和反馈按钮
                if msg["role"] == "assistant" and "citations" in msg:
                    msg_id = msg.get("id", f"msg_{idx}")

                    # 如果是最新一条消息且需要展开引用
                    should_expand = (
                        st.session_state.citation_to_expand
                        and idx == len(st.session_state.messages) - 1
                    )
                    if should_expand:
                        st.session_state.citation_to_expand = False

                    with st.expander(
                        "📚 查看引用来源",
                        expanded=should_expand,
                        key=f"msg_{idx}_citations"
                    ):
                        for citation in msg["citations"]:
                            source = citation.get("search_source", "vector")
                            source_emoji = {"vector": "🔵", "keyword": "🟢", "fusion": "🟠", "rerank": "🟣"}.get(source, "")
                            source_text = {"vector": "向量", "keyword": "关键词", "fusion": "融合", "rerank": "精排"}.get(source, "")

                            page_num = citation.get("page_num", 1)
                            page_range = citation.get("page_range", str(page_num))
                            display_page = page_range if page_range != str(page_num) else str(page_num)

                            col1, col2 = st.columns([3, 1])
                            with col1:
                                if st.button(
                                    f"{source_emoji} [{citation['id']}] {citation['file_name']}",
                                    key=f"hist_msg_{idx}_citation_{citation['id']}",
                                    help=f"相似度：{citation['similarity']}% | 检索：{source_text} - 点击在右侧预览"
                                ):
                                    st.session_state.selected_pdf = citation["file_name"]
                                    st.session_state.selected_page = page_num
                                    st.session_state.highlight_text = citation.get("chunk_text", "")
                                    st.session_state.active_citation = citation["id"]
                                    st.session_state.scroll_to_pdf = True
                                    st.session_state.citation_to_expand = False
                                    st.rerun()

                            with col2:
                                st.caption(f"{citation['similarity']}%")

                            if citation.get("section_title"):
                                st.caption(f"章节：{citation['section_title']}")
                            st.caption(f"📄 页码：第 {display_page} 页")
                            st.caption(f"检索：{source_text}")

                    # 反馈按钮（在 AI 消息下方）
                    if msg_id not in st.session_state.feedback_submitted:
                        fb_col1, fb_col2, fb_col3 = st.columns([1, 1, 3])
                        with fb_col1:
                            if st.button("👍 有用", key=f"upvote_{idx}", type="tertiary"):
                                submit_feedback_for_message(msg, is_upvote=True)
                                st.session_state.feedback_submitted[msg_id] = "upvote"
                                st.rerun()
                        with fb_col2:
                            if st.button("👎 无用", key=f"downvote_{idx}", type="tertiary"):
                                # 弹出输入框收集评论
                                st.session_state.pending_downvote_idx = idx
                                st.session_state.pending_downvote_msg = msg
                                st.rerun()

                        # 如果有待处理的差评，显示评论输入框
                        if st.session_state.get("pending_downvote_idx") == idx:
                            with st.form(key=f"downvote_form_{idx}"):
                                comment = st.text_area("请告诉我们哪里不好（可选）", key=f"downvote_comment_{idx}")
                                submitted = st.form_submit_button("提交反馈")
                                if submitted:
                                    submit_feedback_for_message(
                                        st.session_state.pending_downvote_msg,
                                        is_upvote=False,
                                        comment=comment
                                    )
                                    st.session_state.feedback_submitted[st.session_state.pending_downvote_msg["id"]] = "downvote"
                                    st.session_state.pending_downvote_idx = None
                                    st.success("感谢反馈！")
                                    st.rerun()
                    else:
                        # 已提交反馈，显示提示
                        feedback_type = st.session_state.feedback_submitted.get(msg_id, "")
                        if feedback_type == "upvote":
                            st.caption("✅ 感谢您的点赞！")
                        elif feedback_type == "downvote":
                            st.caption("📝 感谢您的反馈，我们会持续改进")

                    # 显示思考过程（如果启用了反思链路）
                    if msg.get("thinking_process"):
                        with st.expander("🤔 查看思考过程", expanded=False):
                            st.markdown(msg["thinking_process"])

        # 聊天输入控制（带配置开关）
        st.divider()
        with st.expander("⚙️ 功能设置", expanded=False):
            col_clear1, col_clear2 = st.columns([1, 3])
            with col_clear1:
                if st.button("🗑️ 清空对话历史"):
                    import uuid
                    # 清空会话文件
                    session_id_to_delete = st.session_state.session_id
                    session_file = os.path.join("./conversation_sessions", f"{session_id_to_delete}.json")
                    if os.path.exists(session_file):
                        os.remove(session_file)
                    # 重置会话 ID
                    st.session_state.session_id = str(uuid.uuid4())[:8]
                    st.session_state.messages = []
                    st.session_state.conversation_history = []
                    st.session_state.feedback_submitted = {}
                    # 清空缓存的 conversation manager
                    get_conversation_manager.clear()
                    st.rerun()
            st.caption(f"会话 ID: {st.session_state.session_id}")

        # 聊天输入
        if prompt := st.chat_input("请输入您的问题..."):
            import uuid
            msg_id = f"msg_{uuid.uuid4().hex[:8]}"

            # 1. 多轮对话处理：指代消解和上下文增强
            # 使用缓存的 conversation manager（关键修复：避免每次重新实例化）
            conv_manager = get_conversation_manager()

            if conv_manager is None:
                st.error("对话管理器不可用，请重启 Streamlit 服务")
                return

            # 指代消解（处理"那上海呢？"这类追问）
            resolved_prompt = conv_manager.resolve_coreference(prompt, st.session_state.session_id)

            # 显示原始问题和处理后问题（用于调试/透明）
            if resolved_prompt != prompt:
                st.caption(f"🔍 已理解追问意图：{resolved_prompt}")

            # 2. 检索
            context, citations = query_chroma(resolved_prompt, top_k=5)

            if not context:
                response_content = "抱歉，我没有找到相关的参考资料。"
                st.markdown(response_content)
                st.session_state.messages.append({
                    "role": "user",
                    "content": prompt,
                    "id": f"{msg_id}_user"
                })
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_content,
                    "id": msg_id,
                    "citations": [],
                    "thinking_process": None
                })

                # 更新对话历史
                conv_manager.add_user_message(prompt, st.session_state.session_id)
                conv_manager.add_assistant_message(response_content, st.session_state.session_id)
            else:
                # 3. 生成回答（支持流式输出和语义缓存）
                from semantic_cache import get_cache

                cache = get_cache(
                    similarity_threshold=CONFIG.get("similarity_threshold", 0.95),
                    cache_path=CONFIG.get("cache_path", "./semantic_cache")
                ) if CONFIG.get("use_cache", True) else None

                full_response = ""
                is_from_cache = False
                thinking_process = ""

                # 尝试从缓存获取
                if cache:
                    cached_entry = cache.get(resolved_prompt)
                    if cached_entry:
                        is_from_cache = True
                        full_response = cached_entry.answer
                        st.markdown(full_response)

                # 流式输出
                if not is_from_cache and CONFIG.get("use_streaming", True):
                    response_gen = call_llm_streaming(resolved_prompt, context)
                    full_response = st.write_stream(response_gen)
                elif not is_from_cache:
                    with st.spinner("正在思考..."):
                        full_response = call_llm(resolved_prompt, context)
                        st.markdown(full_response)

                # 4. 反思链路处理（如果启用）
                if st.session_state.enable_reasoning and not is_from_cache:
                    from reasoning_judge import get_reasoning_judge

                    judge = get_reasoning_judge(model=CONFIG["llm_model"])
                    judgment = judge.judge(resolved_prompt, context)
                    final_response, thinking_process = judge.generate_response(
                        resolved_prompt, judgment, context, full_response
                    )

                    # 显示带思考过程的回答
                    st.markdown(final_response)
                    full_response = final_response
                else:
                    thinking_process = ""

                # 保存到缓存
                if cache and full_response and not is_from_cache:
                    cache.set(resolved_prompt, full_response, context)

                # 显示缓存命中提示
                if is_from_cache:
                    st.caption("💡 语义缓存命中 - 加速响应")

                    # 显示引用来源（可点击）
                    if citations:
                        expander_key = "citations_expander"
                        with st.expander("📚 查看引用来源", expanded=False, key=expander_key):
                            for citation in citations:
                                source = citation.get("search_source", "vector")
                                source_emoji = {"vector": "🔵", "keyword": "🟢", "fusion": "🟠", "rerank": "🟣"}.get(source, "")
                                source_text = {"vector": "向量", "keyword": "关键词", "fusion": "融合", "rerank": "精排"}.get(source, "")

                                page_num = citation.get("page_num", 1)
                                page_range = citation.get("page_range", str(page_num))
                                display_page = page_range if page_range != str(page_num) else str(page_num)

                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    if st.button(
                                        f"{source_emoji} [{citation['id']}] {citation['file_name']}",
                                        key=f"cached_citation_{citation['id']}",
                                        help=f"相似度：{citation['similarity']}% | 检索：{source_text}"
                                    ):
                                        st.session_state.selected_pdf = citation["file_name"]
                                        st.session_state.selected_page = page_num
                                        st.session_state.highlight_text = citation.get("chunk_text", "")
                                        st.session_state.active_citation = citation["id"]
                                        st.session_state.scroll_to_pdf = True
                                        st.session_state.citation_to_expand = True
                                        st.rerun()

                                with col2:
                                    st.caption(f"{citation['similarity']}%")

                                if citation.get("section_title"):
                                    st.caption(f"章节：{citation['section_title']}")
                                st.caption(f"📄 页码：第 {display_page} 页")
                                st.caption(f"检索：{source_text}")

                    # 保存到消息历史
                    st.session_state.messages.append({
                        "role": "user",
                        "content": prompt,
                        "id": f"{msg_id}_user"
                    })
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": full_response,
                        "id": msg_id,
                        "citations": citations,
                        "from_cache": is_from_cache,
                        "thinking_process": thinking_process,
                        "resolved_prompt": resolved_prompt
                    })

                    # 更新对话历史
                    conv_manager.add_user_message(prompt, st.session_state.session_id)
                    conv_manager.add_assistant_message(full_response, st.session_state.session_id, context, citations)
                    return  # 缓存命中时提前返回

                # 非缓存消息的引用显示
                if citations:
                    expander_key = "citations_expander"
                    with st.expander("📚 查看引用来源", expanded=False, key=expander_key):
                        for citation in citations:
                            source = citation.get("search_source", "vector")
                            source_emoji = {"vector": "🔵", "keyword": "🟢", "fusion": "🟠", "rerank": "🟣"}.get(source, "")
                            source_text = {"vector": "向量", "keyword": "关键词", "fusion": "融合", "rerank": "精排"}.get(source, "")

                            page_num = citation.get("page_num", 1)
                            page_range = citation.get("page_range", str(page_num))
                            display_page = page_range if page_range != str(page_num) else str(page_num)

                            col1, col2 = st.columns([3, 1])
                            with col1:
                                if st.button(
                                    f"{source_emoji} [{citation['id']}] {citation['file_name']}",
                                    key=f"citation_{citation['id']}",
                                    help=f"相似度：{citation['similarity']}% | 检索：{source_text} - 点击在右侧预览"
                                ):
                                    st.session_state.selected_pdf = citation["file_name"]
                                    st.session_state.selected_page = page_num
                                    st.session_state.highlight_text = citation.get("chunk_text", "")
                                    st.session_state.active_citation = citation["id"]
                                    st.session_state.scroll_to_pdf = True
                                    st.session_state.citation_to_expand = True
                                    st.rerun()

                            with col2:
                                st.caption(f"{citation['similarity']}%")

                            if citation.get("section_title"):
                                st.caption(f"章节：{citation['section_title']}")
                            st.caption(f"📄 页码：第 {display_page} 页")
                            st.caption(f"检索：{source_text}")

                # 保存消息
                st.session_state.messages.append({
                    "role": "user",
                    "content": prompt,
                    "id": f"{msg_id}_user"
                })
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "id": msg_id,
                    "citations": citations,
                    "from_cache": is_from_cache,
                    "thinking_process": thinking_process,
                    "resolved_prompt": resolved_prompt
                })

                # 更新对话历史
                conv_manager.add_user_message(prompt, st.session_state.session_id)
                conv_manager.add_assistant_message(full_response, st.session_state.session_id, context, citations)


def submit_feedback_for_message(msg: dict, is_upvote: bool, comment: str = ""):
    """
    为消息提交反馈

    Args:
        msg: 消息字典
        is_upvote: 是否点赞
        comment: 用户评论
    """
    from feedback_collector import get_feedback_collector

    collector = get_feedback_collector()
    collector.add_feedback(
        question=msg.get("resolved_prompt", msg["content"]),
        answer=msg["content"],
        feedback_type="upvote" if is_upvote else "downvote",
        citations=msg.get("citations", []),
        user_comment=comment,
        session_id=st.session_state.session_id
    )

    if is_upvote:
        st.toast("👍 感谢您的点赞！", icon="✅")
    else:
        st.toast("📝 感谢您的反馈，我们会持续改进", icon="📝")


def render_pdf_preview_panel():
    """渲染右侧 PDF 预览面板"""
    with st.container():
        # 调试信息
        debug_info = st.empty()
        debug_info.caption(f"DEBUG: scroll_to_pdf={st.session_state.scroll_to_pdf}, selected_pdf={st.session_state.selected_pdf}, active_citation={st.session_state.active_citation}")

        st.subheader("📖 PDF 预览")

        # PDF 选择器（如果没有选中的 PDF）
        if not st.session_state.selected_pdf:
            # 列出所有可用的 PDF
            pdf_dir = Path(CONFIG["pdf_base_dir"])
            if pdf_dir.exists():
                pdf_files = list(pdf_dir.glob("*.pdf"))
                if pdf_files:
                    pdf_options = [f.name for f in pdf_files]
                    selected = st.selectbox(
                        "选择要预览的 PDF",
                        options=pdf_options,
                        index=0
                    )
                    if selected:
                        st.session_state.selected_pdf = selected
                        st.rerun()
                else:
                    st.info("没有找到 PDF 文件")
                    st.caption(f"请将 PDF 文件放入 {CONFIG['pdf_base_dir']} 目录")
            else:
                st.info(f"目录不存在：{CONFIG['pdf_base_dir']}")
            return

        # 显示当前选中的 PDF
        file_name = st.session_state.selected_pdf
        pdf_path = get_pdf_path(file_name)

        if not pdf_path:
            st.error(f"找不到文件：{file_name}")
            if st.button("清除选择"):
                st.session_state.selected_pdf = None
                st.rerun()
            return

        # 如果是通过点击引用跳转的，尝试自动定位到高亮文本的实际位置
        if st.session_state.scroll_to_pdf and st.session_state.highlight_text:
            # 先显示加载提示
            with st.spinner("🔍 正在搜索高亮文本位置..."):
                found_page = find_text_in_pdf(pdf_path, st.session_state.highlight_text)
                if found_page and found_page != st.session_state.selected_page:
                    st.info(f"✅ 已自动定位到高亮文本所在页码：{found_page}")
                    st.session_state.selected_page = found_page
                    st.session_state.scroll_to_pdf = False
                    st.rerun()
                elif not found_page:
                    st.warning("⚠️ 未能在文档中找到完全匹配的文本，显示引用标注的页码")

            # 重置滚动标志
            st.session_state.scroll_to_pdf = False

        # PDF 信息和控件
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**📄 {file_name}**")
            # 显示当前高亮状态
            if st.session_state.highlight_text:
                st.caption("🔍 已启用高亮显示")
        with col2:
            if st.button("✕ 关闭"):
                st.session_state.selected_pdf = None
                st.session_state.highlight_text = None
                st.session_state.active_citation = None
                st.rerun()

        # 获取 PDF 文档信息
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()
        except Exception:
            total_pages = 1

        # 页码选择器
        page_num = st.number_input(
            "页码",
            min_value=1,
            max_value=total_pages,
            value=min(st.session_state.selected_page, total_pages),
            step=1
        )

        # 更新会话状态
        if page_num != st.session_state.selected_page:
            st.session_state.selected_page = page_num

        # 渲染 PDF 页面（带高亮）
        png_data = render_pdf_with_highlight(
            str(pdf_path),
            page_num,
            st.session_state.highlight_text if st.session_state.active_citation else None,
            zoom=2.0  # 提高清晰度
        )

        # 显示 PDF 图片
        if png_data:
            st.image(png_data, use_container_width=True)
        else:
            st.error("无法渲染 PDF 页面")

        # 显示页面文本（可选）
        if st.checkbox("显示页面文本", key="show_text"):
            try:
                doc = fitz.open(pdf_path)
                page = doc[page_num - 1]
                page_text = page.get_text()
                doc.close()
                with st.expander("📝 查看页面文本"):
                    st.text(page_text)
            except Exception as e:
                st.error(f"读取文本失败：{str(e)}")

        # 高亮控制按钮
        if st.session_state.highlight_text and st.session_state.active_citation:
            col_find, col_auto, col_clear = st.columns([2, 2, 1])

            with col_find:
                # 尝试在当前页面查找高亮文本
                try:
                    doc = fitz.open(pdf_path)
                    page = doc[page_num - 1]

                    # 搜索文本
                    clean_text = ' '.join(st.session_state.highlight_text.strip().split())
                    rects = page.search_for(clean_text[:200])
                    if not rects:
                        rects = page.search_for(st.session_state.highlight_text[:200])

                    doc.close()

                    if rects:
                        st.success(f"✅ 在当前页面找到 {len(rects)} 处匹配")
                    else:
                        st.warning("⚠️ 当前页面未找到匹配文本")
                except Exception:
                    pass

            with col_auto:
                # 自动搜索整个 PDF 查找高亮文本所在位置
                if st.button("📍 跳转到高亮位置"):
                    found_page = find_text_in_pdf(pdf_path, st.session_state.highlight_text)
                    if found_page:
                        st.session_state.selected_page = found_page
                        st.rerun()
                    else:
                        st.warning("未在整个文档中找到匹配文本")

            with col_clear:
                if st.button("✕ 清除"):
                    st.session_state.highlight_text = None
                    st.session_state.active_citation = None
                    st.rerun()

        # 上一页/下一页按钮
        col_prev, col_next = st.columns(2)
        with col_prev:
            if page_num > 1:
                if st.button("← 上一页"):
                    st.session_state.selected_page = page_num - 1
                    st.rerun()
        with col_next:
            if page_num < total_pages:
                if st.button("下一页 →"):
                    st.session_state.selected_page = page_num + 1
                    st.rerun()


def main():
    """主函数"""
    st.set_page_config(
        page_title="PDF 智能问答",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 自定义样式
    st.markdown("""
    <style>
    .stChatMessage {
        border-radius: 12px;
        margin-bottom: 12px;
    }
    .stButton > button {
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

    # 初始化会话状态
    init_session_state()

    # 侧边栏：知识库管理 + 过滤面板
    with st.sidebar:
        render_knowledge_base_panel()
        st.divider()
        render_filter_panel()

    # 标题
    st.title("📚 PDF 智能问答系统")
    st.caption("基于 ChromaDB 的 RAG 问答 - 点击 AI 引用可在右侧查看 PDF 原文")

    # 创建左右两列布局
    left_col, right_col = st.columns([1, 1], gap="large")

    # 左侧：聊天面板
    with left_col:
        render_chat_panel()

    # 右侧：PDF 预览面板
    with right_col:
        render_pdf_preview_panel()


if __name__ == "__main__":
    main()
