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
from typing import Optional, List

import streamlit as st
import chromadb
import fitz  # PyMuPDF


# ==================== 配置 ====================

CONFIG = {
    "chroma_path": "./chroma_db",
    "collection_name": "legal_docs",
    "pdf_base_dir": "./data",
    "llm_model": "qwen-plus",
    "embedding_model": "text-embedding-v3",
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
def get_chroma_collection():
    """获取 ChromaDB 集合"""
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
    查询 ChromaDB 并返回结果

    Args:
        query: 查询问题
        top_k: 返回的最相似结果数量

    Returns:
        (上下文文本，引用列表)
    """
    collection = get_chroma_collection()

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

            # 从 chunk 文本中提取页码
            page_num = extract_page_number_from_chunk(doc)

            # 引用信息
            citation = {
                "id": idx + 1,
                "file_name": metadata.get("file_name", "未知"),
                "section_title": metadata.get("section_title", ""),
                "similarity": round(similarity * 100, 1),
                "chunk_id": metadata.get("chunk_id", 0),
                "doc_id": metadata.get("doc_id", ""),
                "source_path": metadata.get("source_path", ""),
                "page_num": page_num,
                "chunk_text": doc,  # 保存原始 chunk 文本用于高亮
            }
            citations.append(citation)

            # 上下文内容
            context_parts.append(f"[{idx + 1}] {doc}")

    context = "\n\n".join(context_parts)
    return context, citations


# ==================== LLM 调用 ====================

def call_llm(query: str, context: str) -> str:
    """
    调用 LLM 生成回答

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

            # 尝试多种搜索方式
            rects = page.search_for(clean_text[:200])
            if not rects:
                rects = page.search_for(text[:200])

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

                # 方法 3: 逐句搜索
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
                    }
                else:
                    # 累加 chunk 数量
                    if file_name in pdf_info:
                        pdf_info[file_name]["chunk_count"] += 1

        return list(pdf_info.values())

    except Exception as e:
        print(f"获取知识库 PDF 列表失败：{e}")
        return []


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


def render_chat_panel():
    """渲染左侧聊天面板"""
    with st.container():
        st.subheader("💬 AI 问答")

        # 显示历史消息
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

                # 如果是 AI 消息且有引用，显示引用来源
                if msg["role"] == "assistant" and "citations" in msg:
                    # 如果是最新一条消息且需要展开引用
                    should_expand = (
                        st.session_state.citation_to_expand
                        and idx == len(st.session_state.messages) - 1
                    )
                    # 展开后重置标志
                    if should_expand:
                        st.session_state.citation_to_expand = False

                    with st.expander(
                        "📚 查看引用来源",
                        expanded=should_expand,
                        key=f"msg_{idx}_citations"
                    ):
                        for citation in msg["citations"]:
                            # 使用按钮形式的引用
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                if st.button(
                                    f"📄 [{citation['id']}] {citation['file_name']}",
                                    key=f"hist_msg_{idx}_citation_{citation['id']}",
                                    help=f"相似度：{citation['similarity']}% - 点击在右侧预览"
                                ):
                                    # 点击引用时，在右侧显示 PDF 并跳转到对应页面
                                    st.session_state.selected_pdf = citation["file_name"]
                                    st.session_state.selected_page = citation.get("page_num", 1)
                                    st.session_state.highlight_text = citation.get("chunk_text", "")
                                    st.session_state.active_citation = citation["id"]
                                    st.session_state.scroll_to_pdf = True
                                    st.session_state.citation_to_expand = False  # 不重复展开
                                    st.rerun()

                            with col2:
                                st.caption(f"{citation['similarity']}%")

                            if citation.get("section_title"):
                                st.caption(f"章节：{citation['section_title']}")
                            # 显示页码信息
                            if citation.get("page_num"):
                                st.caption(f"页码：第 {citation['page_num']} 页")

        # 聊天输入
        if prompt := st.chat_input("请输入您的问题..."):
            # 显示用户消息
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            # AI 响应
            with st.chat_message("assistant"):
                with st.spinner("正在思考..."):
                    # 1. 检索
                    context, citations = query_chroma(prompt, top_k=5)

                    if not context:
                        st.markdown("抱歉，我没有找到相关的参考资料。")
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": "抱歉，我没有找到相关的参考资料。"
                        })
                    else:
                        # 2. 生成回答
                        response = call_llm(prompt, context)
                        st.markdown(response)

                        # 显示引用来源（可点击）
                        if citations:
                            # 使用唯一 key 让 expander 可以被外部控制
                            expander_key = "citations_expander"
                            with st.expander("📚 查看引用来源", expanded=False, key=expander_key):
                                for citation in citations:
                                    # 使用按钮形式的引用
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        if st.button(
                                            f"📄 [{citation['id']}] {citation['file_name']}",
                                            key=f"citation_{citation['id']}",
                                            help=f"相似度：{citation['similarity']}% - 点击在右侧预览"
                                        ):
                                            # 点击引用时，在右侧显示 PDF 并跳转到对应页面
                                            st.session_state.selected_pdf = citation["file_name"]
                                            st.session_state.selected_page = citation.get("page_num", 1)
                                            st.session_state.highlight_text = citation.get("chunk_text", "")
                                            st.session_state.active_citation = citation["id"]
                                            # 标记需要滚动到 PDF 预览并展开引用列表
                                            st.session_state.scroll_to_pdf = True
                                            st.session_state.citation_to_expand = True
                                            st.rerun()

                                    with col2:
                                        st.caption(f"{citation['similarity']}%")

                                    if citation.get("section_title"):
                                        st.caption(f"章节：{citation['section_title']}")
                                    # 显示页码信息
                                    if citation.get("page_num"):
                                        st.caption(f"页码：第 {citation['page_num']} 页")

                        # 保存消息
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response,
                            "citations": citations,
                        })


def render_pdf_preview_panel():
    """渲染右侧 PDF 预览面板"""
    with st.container():
        # 调试信息
        debug_info = st.empty()
        debug_info.caption(f"DEBUG: scroll_to_pdf={st.session_state.scroll_to_pdf}, selected_pdf={st.session_state.selected_pdf}, active_citation={st.session_state.active_citation}")

        # 如果是通过点击引用跳转的，添加视觉提示和锚点
        if st.session_state.scroll_to_pdf and st.session_state.selected_pdf:
            # 使用一个醒目的提示框吸引用户注意
            st.markdown(
                """
                <div id="pdf-preview-anchor"></div>
                <div style="background-color: #E3F2FD; border-left: 4px solid #1565C0; padding: 16px; margin: 16px 0; border-radius: 8px;">
                    <strong>📌 已定位到 PDF 位置</strong>
                    <p style="margin: 8px 0 0 0; color: #424242;">点击下方"📍 跳转到高亮位置"按钮可自动搜索并定位到高亮内容</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            # 重置滚动标志
            st.session_state.scroll_to_pdf = False

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

    # 侧边栏：知识库管理
    with st.sidebar:
        render_knowledge_base_panel()

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
