# Python RAG QA System

基于 LlamaIndex 和 ChromaDB 的检索增强生成（RAG）问答系统。

## 功能特性

- 📄 **PDF 解析** - 使用 PyMuPDF 高效提取 PDF 文本
- 🔍 **向量检索** - ChromaDB 作为向量数据库
- 🧠 **智能索引** - LlamaIndex 文本分块和索引
- 💬 **语义查询** - 支持自然语言问答

## 快速开始

### 1. 安装依赖

```bash
pip install -e .
```

开发模式安装（包含开发工具）：

```bash
pip install -e ".[dev]"
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# 复制模板
cp .env.example .env

# 编辑 .env 文件，填入你的 DashScope API Key
DASHSCOPE_API_KEY=your_api_key_here
```

> 获取 API Key: https://dashscope.console.aliyun.com/apiKey

### 3. 运行示例

```bash
# 将 PDF 文件放入 data/ 目录
python docs/pdf_parser.py
```

## 项目结构

```
.
├── src/
│   └── rag_qa/          # 主要源代码
├── docs/                # 文档和示例脚本
├── data/                # PDF 数据文件
├── chroma_db/           # ChromaDB 持久化数据（自动生成）
├── pyproject.toml       # 项目配置
└── README.md
```

## 使用示例

### 基本用法

```python
from docs.pdf_parser import index_pdf, query_index

# 索引 PDF
index = index_pdf("data/your_doc.pdf")

# 查询
answer = query_index("文档的核心观点是什么？", index)
print(answer)
```

### 自定义配置

```python
# 自定义分块参数
index = index_pdf(
    pdf_path="data/doc.pdf",
    persist_dir="./my_chroma_db",
    collection_name="my_collection",
    chunk_size=1024,      # 更大的分块
    chunk_overlap=100     # 更多重叠
)
```

## Streamlit Web 界面

项目提供了基于 Streamlit 的 Web 聊天界面，支持：

- 💬 左侧聊天框与 AI 对话
- 📖 右侧 PDF 预览插件
- 🔗 点击 AI 引用时显示来源文件名和对应 PDF 页面

### 启动 Web 界面

```bash
# 确保 PDF 文件已索引到 ChromaDB
python ingest.py

# 启动 Streamlit 应用
streamlit run app.py
```

界面会自动在浏览器中打开，默认地址：http://localhost:8501

## 开发工具

```bash
# 代码格式化
black src/ docs/

# 代码检查
ruff check src/ docs/

# 运行测试
pytest
```

## 许可证

MIT License
