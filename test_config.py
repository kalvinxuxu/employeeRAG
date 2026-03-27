"""
快速测试脚本 - 验证 RAG 系统配置是否正确
"""
import sys
import os
from pathlib import Path

# 设置 UTF-8 编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

def test_imports():
    """测试所有依赖是否可以正常导入"""
    print("[INFO] 测试导入...")

    try:
        from llama_index.core import Document, Settings
        print("  [OK] LlamaIndex")
    except ImportError as e:
        print(f"  [FAIL] LlamaIndex: {e}")
        return False

    try:
        from llama_index.llms.dashscope import DashScope
        print("  [OK] DashScope LLM")
    except ImportError as e:
        print(f"  [FAIL] DashScope LLM: {e}")
        return False

    try:
        from llama_index.embeddings.dashscope import DashScopeEmbedding
        print("  [OK] DashScope Embedding")
    except ImportError as e:
        print(f"  [FAIL] DashScope Embedding: {e}")
        return False

    try:
        import chromadb
        print("  [OK] ChromaDB")
    except ImportError as e:
        print(f"  [FAIL] ChromaDB: {e}")
        return False

    try:
        import fitz
        print("  [OK] PyMuPDF")
    except ImportError as e:
        print(f"  [FAIL] PyMuPDF: {e}")
        return False

    return True


def test_api_config():
    """测试 API 配置"""
    print("\n[INFO] 测试 API 配置...")

    api_key = os.getenv("DASHSCOPE_API_KEY")
    api_base = os.getenv("DASHSCOPE_API_BASE_URL")

    if api_key:
        print(f"  [OK] DASHSCOPE_API_KEY: {api_key[:15]}...")
    else:
        print(f"  [FAIL] DASHSCOPE_API_KEY 未设置")
        return False

    if api_base:
        print(f"  [OK] API Base: {api_base}")
    else:
        print(f"  [OK] API Base: 使用默认值")

    return True


def test_llm_connection():
    """测试 LLM 连接"""
    print("\n[INFO] 测试 LLM 连接...")

    try:
        from llama_index.llms.dashscope import DashScope

        # 显式传入 API Key 和 API Base
        api_key = os.getenv("DASHSCOPE_API_KEY")
        api_base = os.getenv("DASHSCOPE_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

        llm = DashScope(model="qwen-plus", api_key=api_key, api_base=api_base)

        # 简单测试
        print("  发送测试请求...")
        response = llm.complete("你好，请用一句话介绍你自己。")
        print(f"  [OK] LLM 响应：{response.text[:50]}...")
        return True

    except Exception as e:
        print(f"  [FAIL] LLM 测试失败：{e}")
        return False


def test_embedding_connection():
    """测试 Embedding 连接"""
    print("\n[INFO] 测试 Embedding 连接...")

    try:
        from llama_index.embeddings.dashscope import DashScopeEmbedding

        api_key = os.getenv("DASHSCOPE_API_KEY")

        embed_model = DashScopeEmbedding(model="text-embedding-v3", api_key=api_key)

        # 简单测试
        print("  生成测试 embedding...")
        embeddings = embed_model.get_text_embedding("这是一个测试句子。")
        print(f"  [OK] Embedding 维度：{len(embeddings)}")
        return True

    except Exception as e:
        print(f"  [FAIL] Embedding 测试失败：{e}")
        return False


def main():
    print("=" * 50)
    print("RAG QA System - 配置测试")
    print("=" * 50)

    # 测试导入
    if not test_imports():
        print("\n[FAIL] 导入测试失败，请检查依赖安装")
        return

    # 测试 API 配置
    if not test_api_config():
        print("\n[FAIL] API 配置测试失败")
        return

    # 测试 LLM
    if not test_llm_connection():
        print("\n[FAIL] LLM 连接测试失败")
        return

    # 测试 Embedding
    if not test_embedding_connection():
        print("\n[FAIL] Embedding 连接测试失败")
        return

    print("\n" + "=" * 50)
    print("[SUCCESS] 所有测试通过！RAG 系统已就绪")
    print("=" * 50)

    # 检查 PDF 文件
    data_dir = Path("data")
    if not data_dir.exists():
        data_dir.mkdir()
        print(f"\n[INFO] 已创建 data/ 目录")

    pdf_files = list(data_dir.glob("*.pdf"))
    if pdf_files:
        print(f"\n[INFO] 检测到 PDF 文件：{', '.join([f.name for f in pdf_files])}")
        print(f"\n运行以下命令开始索引:")
        print(f"   python docs/pdf_parser.py")
    else:
        print(f"\n[INFO] 请将 PDF 文件放入 data/ 目录")


if __name__ == "__main__":
    main()
