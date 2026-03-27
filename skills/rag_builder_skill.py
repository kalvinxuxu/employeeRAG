"""
RAG Builder Skill - 知识问答助手构建工具

触发词：RAG、知识库、问答系统、知识助手、ChromaDB、向量数据库、文档问答
"""

import json
from pathlib import Path
from typing import Optional


def get_rag_stack(scenario: str = "general") -> dict:
    """
    根据场景返回推荐的技术栈配置

    Args:
        scenario: 应用场景 (general/legal/tech_support/customer_service)

    Returns:
        推荐配置字典
    """
    configs = {
        "general": {
            "chunk_size": 500,
            "chunk_overlap": 100,
            "top_k": 5,
            "llm_model": "qwen-plus",
            "embedding_model": "text-embedding-v3",
        },
        "legal": {
            "chunk_size": 800,
            "chunk_overlap": 150,
            "top_k": 3,
            "llm_model": "qwen-plus",
            "embedding_model": "text-embedding-v3",
        },
        "tech_support": {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "top_k": 8,
            "llm_model": "qwen-max",
            "embedding_model": "text-embedding-v3",
        },
        "customer_service": {
            "chunk_size": 400,
            "chunk_overlap": 80,
            "top_k": 3,
            "llm_model": "qwen-turbo",
            "embedding_model": "text-embedding-v3",
        },
    }
    return configs.get(scenario, configs["general"])


def generate_requirements(scenario: str = "general") -> str:
    """
    生成 requirements.txt 内容
    """
    base_deps = [
        "# Web 框架",
        "streamlit>=1.30.0",
        "",
        "# 向量数据库",
        "chromadb>=0.4.0",
        "",
        "# PDF 处理",
        "PyMuPDF>=1.23.0",
        "docling>=2.0.0",
        "pdfplumber>=0.10.0",
        "",
        "# LlamaIndex (LLM 调用)",
        "llama-index-core>=0.10.0",
        "llama-index-llms-dashscope>=0.1.0",
        "llama-index-embeddings-dashscope>=0.1.0",
        "llama-index-vector-stores-chroma>=0.1.0",
        "",
        "# 工具",
        "python-dotenv>=1.0.0",
    ]
    return "\n".join(base_deps)


def generate_env_template() -> str:
    """
    生成.env 模板
    """
    return """# DashScope API Key
# 获取地址：https://dashscope.console.aliyun.com/apiKey
DASHSCOPE_API_KEY=sk-your-api-key-here

# (可选) 自定义配置
# RAG_CHUNK_SIZE=500
# RAG_TOP_K=5
# RAG_LLM_MODEL=qwen-plus
"""


def generate_ingest_script(pdf_parser: str = "pymupdf") -> str:
    """
    生成 ingest 脚本模板

    Args:
        pdf_parser: 解析器类型 (pymupdf/docling)
    """
    if pdf_parser == "docling":
        return "# Docling 版本 ingest 脚本\n# 使用 DocumentConverter 进行结构化解析\nfrom docling.document_converter import DocumentConverter\n\ndef parse_pdf(path):\n    converter = DocumentConverter()\n    result = converter.convert(path)\n    return result.document.export_to_markdown()"
    else:
        return "# PyMuPDF 版本 ingest 脚本\n# 轻量快速，无网络依赖\nimport fitz\n\ndef parse_pdf(path):\n    doc = fitz.open(path)\n    text = '\\n'.join([page.get_text() for page in doc])\n    doc.close()\n    return text"


class RagBuilderSkill:
    """RAG Builder Skill 主类"""

    def __init__(self):
        self.skill_path = Path(__file__).parent
        self.reference_path = self.skill_path / "rag-builder.md"

    def load_reference(self) -> Optional[str]:
        """加载参考文档"""
        if self.reference_path.exists():
            return self.reference_path.read_text(encoding="utf-8")
        return None

    def analyze_requirement(self, user_input: str) -> dict:
        """
        分析用户需求

        Returns:
            需求分析结果
        """
        result = {
            "scenario": "general",
            "doc_format": "pdf",
            "deploy_env": "local",
            "scale": "small",
        }

        # 场景识别
        if any(kw in user_input for kw in ["制度", "法律", "合规", "政策"]):
            result["scenario"] = "legal"
        elif any(kw in user_input for kw in ["技术", "API", "开发", "代码"]):
            result["scenario"] = "tech_support"
        elif any(kw in user_input for kw in ["客服", "客户", "咨询", "问答"]):
            result["scenario"] = "customer_service"

        # 文档格式识别
        if any(kw in user_input for kw in ["Word", "docx", "DOCX"]):
            result["doc_format"] = "docx"
        elif any(kw in user_input for kw in ["Markdown", "md", "MD"]):
            result["doc_format"] = "markdown"

        return result

    def generate_project(self, project_name: str, config: dict) -> dict:
        """
        生成项目文件结构

        Args:
            project_name: 项目名称
            config: 配置字典

        Returns:
            文件路径列表
        """
        files = {
            f"{project_name}/requirements.txt": generate_requirements(config["scenario"]),
            f"{project_name}/.env.example": generate_env_template(),
            f"{project_name}/ingest.py": generate_ingest_script("pymupdf"),
            f"{project_name}/README.md": self._generate_readme(project_name, config),
        }
        return files

    def _generate_readme(self, project_name: str, config: dict) -> str:
        """生成 README"""
        return f"""# {project_name}

基于 RAG 技术的知识问答系统。

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
cp .env.example .env
# 编辑.env 填入 DASHSCOPE_API_KEY
```

### 3. 索引文档
```bash
python ingest.py -i ./data
```

### 4. 启动服务
```bash
streamlit run app.py
```

## 配置
- 分块大小：{config["chunk_size"]}
- 检索数量：{config["top_k"]}
- LLM 模型：{config["llm_model"]}
"""


# 主函数供 skill 调用
def main(user_input: str = "") -> str:
    """
    Skill 主入口

    Args:
        user_input: 用户输入

    Returns:
        响应文本
    """
    skill = RagBuilderSkill()
    requirement = skill.analyze_requirement(user_input)
    config = get_rag_stack(requirement["scenario"])

    response = []
    response.append("## RAG 知识问答助手配置建议\n")
    response.append(f"**识别场景**: {requirement['scenario']}")
    response.append(f"**文档格式**: {requirement['doc_format']}")
    response.append(f"**推荐配置**:\n")
    response.append(f"- 分块大小：{config['chunk_size']} 字符")
    response.append(f"- 重叠大小：{config['chunk_overlap']} 字符")
    response.append(f"- 检索数量：top_k = {config['top_k']}")
    response.append(f"- LLM 模型：{config['llm_model']}")
    response.append(f"- Embedding 模型：{config['embedding_model']}")

    return "\n".join(response)


if __name__ == "__main__":
    print(main("帮我搭建一个企业制度问答系统"))
