---
name: rag-builder
description: RAG 知识问答助手构建指南 - 技术栈、架构和实现模板
type: reference
---

# RAG 知识问答助手构建指南

## 技术栈总览

```
┌─────────────────────────────────────────────────────────────┐
│                      RAG 系统架构图                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐            │
│   │  文档输入  │ →  │  文本分块  │ →  │  Embedding │            │
│   │  (PDF)   │    │ (Chunking)│    │  (向量化) │            │
│   └──────────┘    └──────────┘    └──────────┘            │
│                                        ↓                    │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐            │
│   │  AI 回答   │ ←  │  LLM 生成  │ ←  │  向量检索  │            │
│   │ (Streamlit)│   │ (DashScope)│   │ (ChromaDB)│           │
│   └──────────┘    └──────────┘    └──────────┘            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. 文档解析层 (Document Parsing)

| 方案 | 依赖 | 适用场景 |
|------|------|----------|
| **PyMuPDF (轻量)** | `pymupdf>=1.23.0` | 快速提取文本，无网络依赖 |
| **Docling (结构化)** | `docling>=2.0.0` | 精准解析标题/表格结构 |
| **pdfplumber** | `pdfplumber>=0.10.0` | 表格密集型文档 |

**代码模板 - PyMuPDF 解析：**

```python
import fitz  # PyMuPDF

def extract_text_from_pdf(pdf_path: str) -> str:
    """从 PDF 提取文本"""
    doc = fitz.open(pdf_path)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n\n".join(text_parts)
```

---

### 2. 向量数据库 (Vector Store)

| 组件 | 版本 | 说明 |
|------|------|------|
| **ChromaDB** | `chromadb>=0.4.0` | 本地持久化，简单易用 |
| 存储路径 | `./chroma_db` | 可配置 |
| Collection | `legal_docs` | 文档集合名称 |

**初始化代码：**

```python
import chromadb
from chromadb.api.types import EmbeddingFunction

class DashScopeEmbeddingFunction(EmbeddingFunction):
    def __init__(self, api_key: str, model: str = "text-embedding-v3"):
        self.api_key = api_key
        self.model = model

    def __call__(self, input: list[str]) -> list[list[float]]:
        import dashscope
        dashscope.api_key = self.api_key
        response = dashscope.TextEmbedding.call(
            model=self.model, input=input, text_type="document"
        )
        output = sorted(response.output["embeddings"], key=lambda x: x["text_index"])
        return [item["embedding"] for item in output]

# 初始化
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(
    name="legal_docs",
    embedding_function=DashScopeEmbeddingFunction(api_key="YOUR_KEY")
)
```

---

### 3. Embedding 模型 (向量化)

| 服务商 | 模型 | 维度 | 价格 |
|--------|------|------|------|
| **DashScope (阿里云)** | `text-embedding-v3` | 1024 | ~¥0.0007/千tokens |

**环境变量配置：**

```bash
# .env 文件
DASHSCOPE_API_KEY=sk-xxxxx
```

---

### 4. LLM 层 (大语言模型)

| 组件 | 版本 | 说明 |
|------|------|------|
| **LlamaIndex** | `llama-index-core>=0.10.0` | RAG 框架 |
| **DashScope LLM** | `llama-index-llms-dashscope>=0.1.0` | 通义千问接入 |

**推荐模型：**
- `qwen-plus` - 平衡性能与成本
- `qwen-max` - 复杂推理任务
- `qwen-turbo` - 快速响应场景

**LLM 调用代码：**

```python
from llama_index.llms.dashscope import DashScope

llm = DashScope(model="qwen-plus", api_key="YOUR_KEY")

prompt = f"""基于以下参考资料回答问题：

参考资料:
{context}

用户问题：{query}

请用简洁清晰的中文回答，并在引用处标注来源。"""

response = llm.complete(prompt)
```

---

### 5. 文本分块策略 (Chunking)

| 策略 | 参数 | 适用场景 |
|------|------|----------|
| **按标题分块** | - | 结构清晰的文档 |
| **固定大小分块** | chunk_size=500, overlap=100 | 通用场景 |
| **语义分块** | 需额外模型 | 高质量要求 |

**分块代码模板：**

```python
def split_by_fixed_size(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """按固定大小分块"""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # 在句子边界切分
        if end < len(text):
            for sep in ['。', '.', '!', '?', '\n']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1:
                    end = start + last_sep + 1
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap
    return chunks
```

---

### 6. Web 界面 (可选)

| 框架 | 版本 | 说明 |
|------|------|------|
| **Streamlit** | `streamlit>=1.30.0` | 快速构建聊天界面 |

**启动命令：**

```bash
streamlit run app.py
```

---

## 完整项目结构

```
rag-qa-system/
├── .env                    # 环境变量 (API Key)
├── .env.example            # 环境变量模板
├── requirements.txt        # 运行依赖
├── pyproject.toml          # 项目配置
├── README.md               # 文档
├── data/                   # PDF 文档目录
│   └── *.pdf
├── chroma_db/              # ChromaDB 持久化数据 (自动生成)
├── ingest.py               # 文档索引脚本 (Docling 版)
├── ingest_lite.py          # 文档索引脚本 (PyMuPDF 轻量版)
├── app.py                  # Streamlit Web 界面
└── src/
    └── rag_qa/
        └── __init__.py     # 核心模块
```

---

## 快速开始命令

```bash
# 1. 安装依赖
pip install -e .

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env 填入 DASHSCOPE_API_KEY

# 3. 将 PDF 放入 data/ 目录

# 4. 索引文档
python ingest_lite.py -i ./data

# 5. 启动 Web 界面
streamlit run app.py
```

---

## 核心依赖清单 (requirements.txt)

```txt
# Web 框架
streamlit>=1.30.0

# 向量数据库
chromadb>=0.4.0

# PDF 处理
PyMuPDF>=1.23.0
docling>=2.0.0
pdfplumber>=0.10.0

# LlamaIndex (LLM 调用)
llama-index-core>=0.10.0
llama-index-llms-dashscope>=0.1.0
llama-index-embeddings-dashscope>=0.1.0
llama-index-vector-stores-chroma>=0.1.0

# 工具
python-dotenv>=1.0.0
```

---

## 不同场景的配置建议

### 场景 1: 企业内部制度问答
- **分块大小**: 500-800 chars
- **top_k**: 3-5
- **模型**: qwen-plus
- **特点**: 准确性优先，需要引用来源

### 场景 2: 技术文档助手
- **分块大小**: 800-1200 chars
- **top_k**: 5-8
- **模型**: qwen-max
- **特点**: 代码片段需保留格式

### 场景 3: 客服知识库
- **分块大小**: 300-500 chars
- **top_k**: 3-5
- **模型**: qwen-turbo
- **特点**: 响应速度优先

### 场景 4: 学术研究助手
- **分块大小**: 1000+ chars
- **top_k**: 8-10
- **模型**: qwen-max
- **特点**: 需要长上下文和深度推理

---

## 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| ChromaDB 连接失败 | 路径权限问题 | 检查 `./chroma_db` 目录权限 |
| Embedding API 错误 | API Key 无效 | 检查 `.env` 中的 `DASHSCOPE_API_KEY` |
| PDF 解析失败 | 加密/损坏 | 尝试用其他 PDF 工具打开验证 |
| 检索结果不相关 | 分块过大/过小 | 调整 `chunk_size` 和 `chunk_overlap` |
| 回答质量差 | top_k 太小 | 增加检索数量或更换 LLM 模型 |

---

## 性能优化建议

1. **批量索引**: 使用 `collection.add()` 批量添加，避免逐条插入
2. **增量更新**: 记录已索引文档的 `doc_id`，避免重复索引
3. **缓存查询**: Streamlit 中使用 `@st.cache_resource` 缓存 ChromaDB 连接
4. **异步处理**: 大量文档时使用 `asyncio` 并发处理

---

## 扩展方向

1. **多格式支持**: 添加 Word (.docx)、Excel (.xlsx) 解析
2. **多向量库**: 支持 FAISS、Milvus、Weaviate 等
3. **混合检索**: 向量检索 + 关键词检索 (BM25)
4. **Rerank 模型**: 对检索结果二次排序提升质量
5. **多模态**: 解析 PDF 中的图表和图片

---

## 参考资源

- ChromaDB 文档: https://docs.trychroma.com/
- LlamaIndex 文档: https://docs.llamaindex.ai/
- DashScope 文档: https://help.aliyun.com/zh/dashscope/
- Streamlit 文档: https://docs.streamlit.io/
