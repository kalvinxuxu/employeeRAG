# 智能问答助手使用指南

> 基于 RAG (检索增强生成) 技术的 PDF 文档智能问答系统

---

## 目录

1. [系统简介](#系统简介)
2. [环境准备](#环境准备)
3. [安装步骤](#安装步骤)
4. [配置 API Key](#配置-api-key)
5. [快速开始](#快速开始)
6. [Web 界面使用](#web-界面使用)
7. [Python API 调用](#python-api-调用)
8. [使用场景推荐](#使用场景推荐)
9. [常见问题](#常见问题)

---

## 系统简介

### 核心功能

| 功能 | 说明 |
|------|------|
| 📄 **PDF 解析** | 支持快速提取 PDF 文本内容 |
| 🔍 **向量检索** | 使用 ChromaDB 存储和检索向量 |
| 🧠 **智能索引** | 自动分块、Embedding 向量化 |
| 💬 **语义问答** | 理解自然语言问题，生成精准回答 |
| 🔗 **引用溯源** | 回答标注来源文件和页码 |

### 系统架构

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   PDF 文档    │ →  │  文本分块     │ →  │  Embedding   │
│   (输入)     │    │  (Chunking)  │    │  (向量化)    │
└──────────────┘    └──────────────┘    └──────────────┘
                                               ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   AI 回答     │ ←  │  LLM 生成     │ ←  │  向量检索    │
│ (Streamlit)  │    │ (DashScope)  │    │ (ChromaDB)   │
└──────────────┘    └──────────────┘    └──────────────┘
```

### 技术栈

- **前端界面**: Streamlit
- **向量数据库**: ChromaDB
- **PDF 处理**: PyMuPDF / Docling
- **LLM 框架**: LlamaIndex
- **Embedding**: DashScope (text-embedding-v3)
- **大模型**: 通义千问 (qwen-plus / qwen-max / qwen-turbo)

---

## 环境准备

### 系统要求

- Python 3.9 或更高版本
- 操作系统：Windows / macOS / Linux
- 内存：建议 8GB 以上

### 检查 Python 版本

```bash
python --version
```

---

## 安装步骤

### 1. 克隆或下载项目

确保你在项目根目录：

```bash
cd C:\Users\kalvi\Documents\claude_internalQAsystem
```

### 2. 安装依赖

**基础安装（推荐）：**

```bash
pip install -e .
```

**开发模式安装（包含代码格式化工具）：**

```bash
pip install -e ".[dev]"
```

### 3. 验证安装

```bash
python -c "import chromadb; import fitz; print('安装成功！')"
```

---

## 配置 API Key

### 获取 API Key

1. 访问阿里云 DashScope 控制台：https://dashscope.console.aliyun.com/apiKey
2. 登录/注册阿里云账号
3. 创建或复制你的 API Key

### 创建 .env 文件

在项目根目录执行：

```bash
# Windows PowerShell
cp .env.example .env

# 或者直接创建
echo DASHSCOPE_API_KEY=sk-your-key-here > .env
```

### 编辑 .env 文件

用文本编辑器打开 `.env`，填入你的 API Key：

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ **安全提示**: 不要将 `.env` 文件提交到 Git 仓库

---

## 快速开始

### 步骤 1: 准备 PDF 文档

将你的 PDF 文件放入 `data/` 目录：

```
data/
├── document1.pdf
├── document2.pdf
└── ...
```

### 步骤 2: 索引文档

**轻量版（推荐，使用 PyMuPDF）：**

```bash
python ingest_lite.py -i ./data
```

**完整版（使用 Docling，支持结构化解析）：**

```bash
python ingest.py -i ./data
```

### 步骤 3: 启动 Web 界面

```bash
streamlit run app.py
```

浏览器会自动打开到 **http://localhost:8501**

---

## Web 界面使用

### 界面布局

```
┌─────────────────────────────────────────────────────────┐
│  🤖 智能问答助手                                         │
├─────────────────┬───────────────────────────────────────┤
│                 │                                       │
│   💬 聊天区域    │         📖 PDF 预览区域                │
│                 │                                       │
│   - 输入问题     │         - 显示当前 PDF                 │
│   - 查看回答     │         - 支持翻页                     │
│   - 引用溯源     │         - 点击引用跳转                 │
│                 │                                       │
└─────────────────┴───────────────────────────────────────┘
```

### 功能说明

| 区域 | 功能 |
|------|------|
| **聊天框** | 输入自然语言问题，获取 AI 回答 |
| **引用链接** | 点击可跳转至对应 PDF 页面 |
| **文件选择器** | 选择要索引的 PDF 文件 |
| **重置按钮** | 清除对话历史 |

### 操作技巧

1. **提问**：直接在聊天框输入问题，按 Enter 发送
2. **查看引用**：点击回答中的引用标记，右侧 PDF 预览会跳转到对应页面
3. **多轮对话**：支持上下文连续的追问
4. **清除历史**：点击"清除对话"开始新的话题

---

## Python API 调用

### 基本用法

```python
from docs.pdf_parser import index_pdf, query_index

# 索引 PDF 文件
index = index_pdf("data/your_doc.pdf")

# 查询问题
answer = query_index("文档的核心观点是什么？", index)
print(answer)
```

### 自定义配置

```python
from docs.pdf_parser import index_pdf

# 自定义索引参数
index = index_pdf(
    pdf_path="data/doc.pdf",
    persist_dir="./my_chroma_db",      # 自定义数据库路径
    collection_name="my_collection",   # 自定义集合名称
    chunk_size=1024,                    # 分块大小
    chunk_overlap=100                   # 重叠大小
)
```

### 批量索引

```python
from pathlib import Path
from docs.pdf_parser import index_pdf

# 索引 data/ 目录下所有 PDF
for pdf_file in Path("data").glob("*.pdf"):
    print(f"索引中：{pdf_file}")
    index_pdf(str(pdf_file))
```

---

## 使用场景推荐

### 1. 企业内部制度问答

| 参数 | 推荐值 |
|------|--------|
| 模型 | qwen-plus |
| 分块大小 | 500-800 chars |
| top_k | 3-5 |
| 特点 | 准确性优先，需要引用来源 |

### 2. 技术文档助手

| 参数 | 推荐值 |
|------|--------|
| 模型 | qwen-max |
| 分块大小 | 800-1200 chars |
| top_k | 5-8 |
| 特点 | 保留代码片段格式 |

### 3. 客服知识库

| 参数 | 推荐值 |
|------|--------|
| 模型 | qwen-turbo |
| 分块大小 | 300-500 chars |
| top_k | 3-5 |
| 特点 | 响应速度优先 |

### 4. 学术研究助手

| 参数 | 推荐值 |
|------|--------|
| 模型 | qwen-max |
| 分块大小 | 1000+ chars |
| top_k | 8-10 |
| 特点 | 长上下文和深度推理 |

---

## 常见问题

### ❓ ChromaDB 连接失败

**可能原因**：目录权限问题

**解决方案**：
```bash
# 检查 chroma_db 目录是否存在
ls -la chroma_db/

# 如果没有，手动创建
mkdir chroma_db
```

### ❓ Embedding API 错误

**可能原因**：API Key 无效或未配置

**解决方案**：
1. 检查 `.env` 文件中的 `DASHSCOPE_API_KEY` 是否正确
2. 确认 API Key 在 DashScope 控制台已激活

### ❓ PDF 解析失败

**可能原因**：PDF 加密或文件损坏

**解决方案**：
1. 用其他 PDF 阅读器验证文件是否可打开
2. 移除 PDF 密码保护
3. 尝试使用 `ingest.py` (Docling 版) 进行解析

### ❓ 检索结果不相关

**可能原因**：分块大小不合适

**解决方案**：
1. 减小 `chunk_size`（如从 1000 改为 500）
2. 增加 `top_k` 检索数量
3. 检查 PDF 文本提取质量

### ❓ 回答质量差

**解决方案**：
1. 增加 `top_k` 值（如从 3 改为 5）
2. 更换更强的 LLM 模型（qwen-plus → qwen-max）
3. 优化 PDF 文档质量

---

## 附录

### 命令速查表

| 命令 | 说明 |
|------|------|
| `pip install -e .` | 安装项目依赖 |
| `python ingest_lite.py -i ./data` | 索引 PDF 文档 |
| `streamlit run app.py` | 启动 Web 界面 |
| `pytest` | 运行测试 |

### 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DASHSCOPE_API_KEY` | DashScope API 密钥 | `sk-xxxxx` |

### 参考资源

- [ChromaDB 文档](https://docs.trychroma.com/)
- [LlamaIndex 文档](https://docs.llamaindex.ai/)
- [DashScope 文档](https://help.aliyun.com/zh/dashscope/)
- [Streamlit 文档](https://docs.streamlit.io/)

---

*最后更新：2026-03-27*
