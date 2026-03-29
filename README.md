# PDF 智能问答系统 (RAG QA System)

基于 LlamaIndex、ChromaDB 和 Streamlit 的 PDF 智能问答系统。

## 功能特性

- 📄 **PDF 解析** - 使用 PyMuPDF 高效提取 PDF 文本
- 🔍 **向量检索** - ChromaDB 作为向量数据库
- 🧠 **智能索引** - LlamaIndex 文本分块和索引
- 💬 **语义查询** - 支持自然语言问答
- 🌐 **Web 界面** - Streamlit 聊天界面，支持 PDF 预览
- 🚀 **一键部署** - 支持 Vercel、Sealos Cloud 部署

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

## ☁️ 部署到 Sealos Cloud

### 快速部署步骤：

1. **构建并推送 Docker 镜像**
   ```bash
   # Windows 用户运行
   deploy-sealos.bat

   # 或 Linux/Mac 用户运行
   bash deploy-sealos.sh
   ```

2. **在 Sealos Cloud 创建应用**
   - 访问 https://cloud.sealos.io 并登录
   - 点击「应用管理」→「应用」→「创建应用」
   - 配置镜像、端口和环境变量

3. **获取公开域名**
   - 部署完成后获得 `https://pdf-qa-system-xxx.sealos.run` 域名
   - 可在浏览器中公开访问

详细部署指南请查看：[sealos-deploy.md](sealos-deploy.md)

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
