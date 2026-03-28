"""
流式 LLM 调用 - 支持打字机效果输出

功能:
- 使用 Streamlit 的流式显示功能
- 让文字像打字机一样逐个跳出
- 降低用户的感官等待时间

用法:
    # 在 Streamlit 中
    with st.chat_message("assistant"):
        response = stream_llm_response(query, context)
        st.write_stream(response)  # 流式显示
"""

import os
from typing import Optional, Generator, Tuple, Any
import streamlit as st


def get_streaming_llm(model: str = "qwen-plus", api_key: Optional[str] = None):
    """
    获取支持流式输出的 LLM 实例

    Args:
        model: 模型名称
        api_key: API Key

    Returns:
        支持 stream 方法的 LLM 实例
    """
    try:
        from llama_index.llms.dashscope import DashScope
    except ImportError:
        return None

    api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None

    # DashScope LLM 支持流式输出
    llm = DashScope(model=model, api_key=api_key)
    return llm


def create_streaming_prompt(query: str, context: str) -> str:
    """
    创建流式提示词

    Args:
        query: 用户问题
        context: 检索到的上下文

    Returns:
        格式化的提示词
    """
    return f"""基于以下参考资料回答问题。如果资料中没有相关信息，请直接告知用户。

参考资料:
{context}

用户问题：{query}

请用简洁清晰的中文回答，并在引用处标注来源编号（如 [1]、[2]）。"""


def stream_llm_response(
    query: str,
    context: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Generator[str, None, None]:
    """
    流式生成 LLM 回答

    Args:
        query: 用户问题
        context: 检索到的上下文
        model: 模型名称
        api_key: API Key

    Yields:
        逐个生成的文本片段
    """
    llm = get_streaming_llm(model=model, api_key=api_key)
    if not llm:
        yield "[错误] LLM 初始化失败"
        return

    prompt = create_streaming_prompt(query, context)

    try:
        # 使用 stream 方法进行流式输出
        response = llm.stream_complete(prompt)

        # 逐个输出文本片段
        for chunk in response:
            if hasattr(chunk, 'delta'):
                delta = chunk.delta
                if hasattr(delta, 'content') and delta.content:
                    yield delta.content
            elif hasattr(chunk, 'text'):
                yield chunk.text

    except Exception as e:
        yield f"\n\n[流式输出错误：{str(e)}]"


def generate_full_response(
    query: str,
    context: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    生成完整回答（非流式，用于缓存）

    Args:
        query: 用户问题
        context: 检索到的上下文
        model: 模型名称
        api_key: API Key

    Returns:
        完整的回答文本
    """
    llm = get_streaming_llm(model=model, api_key=api_key)
    if not llm:
        return "[错误] LLM 初始化失败"

    prompt = create_streaming_prompt(query, context)

    try:
        response = llm.complete(prompt)
        return str(response)
    except Exception as e:
        return f"[错误] LLM 调用失败：{str(e)}"


def stream_text_with_typing(
    text: str,
    delay: float = 0.01,
    chunk_size: int = 1,
) -> Generator[str, None, None]:
    """
    模拟打字机效果输出文本

    Args:
        text: 要输出的文本
        delay: 每个字符的延迟（秒）
        chunk_size: 每次输出的字符数

    Yields:
        逐个字/词输出
    """
    import time

    # 按中文字符输出（每个汉字作为一个 chunk）
    i = 0
    while i < len(text):
        # 检查是否是引用标记 [1], [2] 等
        if text[i:i+2] == '[' and i + 4 < len(text) and text[i+3] == ']':
            # 一次性输出完整引用标记
            yield text[i:i+4]
            i += 4
        else:
            # 输出单个字符或词组
            chunk = text[i:i+chunk_size]
            yield chunk
            i += chunk_size

        # 添加微小延迟（可选，Streamlit 的 write_stream 有自己的节奏）
        if delay > 0:
            time.sleep(delay)


# ==================== Streamlit 集成 ====================

def render_streaming_response(
    query: str,
    context: str,
    use_cache: bool = True,
) -> Tuple[str, bool]:
    """
    在 Streamlit 中渲染流式响应

    Args:
        query: 用户问题
        context: 检索到的上下文
        use_cache: 是否使用缓存

    Returns:
        (完整回答，是否来自缓存)
    """
    from semantic_cache import get_cache

    cache = get_cache() if use_cache else None

    # 尝试从缓存获取
    if cache:
        cached_entry = cache.get(query)
        if cached_entry:
            # 缓存命中，直接显示完整答案
            st.markdown(cached_entry.answer)
            return cached_entry.answer, True

    # 流式生成回答
    full_response = ""
    with st.spinner("正在思考..."):
        # 使用 write_stream 进行流式显示
        response_gen = stream_llm_response(query, context)
        response_gen = st.write_stream(response_gen)

        # 收集完整回答用于缓存
        # 注意：write_stream 返回完整文本
        full_response = response_gen

    # 保存到缓存
    if cache and full_response:
        cache.set(query, full_response, context)

    return full_response, False
