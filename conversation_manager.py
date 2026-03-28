"""
多轮对话管理 (Conversation Manager) - 支持上下文理解的追问

功能:
- 记住最近 N 轮对话历史
- 理解指代消解（如"那上海呢？"指代上海的出差补助）
- 自动补全省略的上下文信息
"""

import os
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    """对话消息"""
    role: str                        # "user" | "assistant"
    content: str                     # 消息内容
    timestamp: datetime              # 时间戳
    query: Optional[str] = None      # 原始查询（用于用户消息）
    context: Optional[str] = None    # 检索到的上下文（用于 assistant）
    citations: List[Dict] = field(default_factory=list)  # 引用来源


@dataclass
class ConversationHistory:
    """对话历史"""
    messages: List[Message]          # 消息列表
    max_turns: int = 5               # 最大轮数
    session_id: str = ""             # 会话 ID

    def add_message(self, role: str, content: str, **kwargs):
        """添加消息"""
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(),
            query=kwargs.get("query"),
            context=kwargs.get("context"),
            citations=kwargs.get("citations", [])
        )
        self.messages.append(message)

        # 保持最大轮数限制（1 轮 = 1 问 +1 答）
        while len(self.messages) > self.max_turns * 2:
            self.messages.pop(0)

    def get_recent_messages(self, n: int = 5) -> List[Message]:
        """获取最近 N 条消息"""
        return self.messages[-n:]

    def get_conversation_summary(self) -> str:
        """获取对话摘要（用于上下文）"""
        if not self.messages:
            return ""

        summary_parts = []
        for msg in self.messages[-self.max_turns * 2:]:
            role_label = "用户" if msg.role == "user" else "助手"
            summary_parts.append(f"{role_label}: {msg.content}")

        return "\n".join(summary_parts)

    def get_last_user_query(self) -> Optional[str]:
        """获取最后一个用户问题"""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.query or msg.content
        return None

    def get_entities_mentioned(self) -> Dict[str, List[str]]:
        """提取已提及的实体（用于指代消解）"""
        entities = {
            "locations": [],      # 地点
            "topics": [],         # 话题
            "departments": [],    # 部门
            "time_references": [] # 时间
        }

        # 简单关键词提取（可扩展为 NER）
        location_keywords = ["北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "西安", "重庆"]
        topic_keywords = ["出差", "报销", "请假", "考勤", "加班", "招聘", "面试", "入职", "补助", "标准", "流程"]
        dept_keywords = ["人力", "财务", "行政", "技术", "产品", "运营", "销售", "市场"]
        time_keywords = ["今天", "明天", "本周", "下周", "本月", "上月", "今年", "去年"]

        for msg in self.messages:
            text = msg.content
            for kw in location_keywords:
                if kw in text and kw not in entities["locations"]:
                    entities["locations"].append(kw)
            for kw in topic_keywords:
                if kw in text and kw not in entities["topics"]:
                    entities["topics"].append(kw)
            for kw in dept_keywords:
                if kw in text and kw not in entities["departments"]:
                    entities["departments"].append(kw)
            for kw in time_keywords:
                if kw in text and kw not in entities["time_references"]:
                    entities["time_references"].append(kw)

        return entities

    def clear(self):
        """清空对话历史"""
        self.messages = []


class ConversationManager:
    """对话管理器"""

    def __init__(self, max_turns: int = 5,
                 enable_coreference: bool = True,
                 llm_model: str = "qwen-plus",
                 api_key: Optional[str] = None,
                 persist_to_file: bool = False,
                 persist_dir: str = "./conversation_sessions"):
        """
        初始化对话管理器

        Args:
            max_turns: 最大对话轮数
            enable_coreference: 是否启用指代消解
            llm_model: LLM 模型名称
            api_key: DashScope API Key
            persist_to_file: 是否持久化会话到文件（Streamlit 环境下建议设为 True）
            persist_dir: 持久化目录
        """
        self.max_turns = max_turns
        self.enable_coreference = enable_coreference
        self.llm_model = llm_model
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.persist_to_file = persist_to_file
        self.persist_dir = persist_dir

        # 会话存储
        self._sessions: Dict[str, ConversationHistory] = {}
        self._llm = None

        # 加载已保存的会话
        if self.persist_to_file:
            self._load_all_sessions()

    def _get_llm(self):
        """懒加载 LLM"""
        if self._llm is None:
            try:
                from llama_index.llms.dashscope import DashScope
                self._llm = DashScope(model=self.llm_model, api_key=self.api_key)
            except ImportError:
                raise ImportError("请安装 llama-index-llms-dashscope")
        return self._llm

    def _get_session_file_path(self, session_id: str) -> str:
        """获取会话文件路径"""
        return os.path.join(self.persist_dir, f"{session_id}.json")

    def _save_session(self, session_id: str):
        """保存会话到文件"""
        if not self.persist_to_file:
            return

        session = self._sessions.get(session_id)
        if not session:
            return

        # 确保目录存在
        os.makedirs(self.persist_dir, exist_ok=True)

        # 序列化会话数据
        session_data = {
            "session_id": session.session_id,
            "max_turns": session.max_turns,
            "messages": []
        }

        for msg in session.messages:
            session_data["messages"].append({
                "role": msg.role,
                "content": msg.content,
                "query": msg.query,
                "context": msg.context,
                "citations": msg.citations,
                "timestamp": msg.timestamp.isoformat()
            })

        # 保存到文件
        file_path = self._get_session_file_path(session_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

    def _load_session(self, session_id: str) -> Optional[ConversationHistory]:
        """从文件加载会话"""
        if not self.persist_to_file:
            return None

        file_path = self._get_session_file_path(session_id)
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            session = ConversationHistory(
                messages=[],
                max_turns=session_data.get("max_turns", self.max_turns),
                session_id=session_data.get("session_id", session_id)
            )

            for msg_data in session_data.get("messages", []):
                msg = Message(
                    role=msg_data["role"],
                    content=msg_data["content"],
                    timestamp=datetime.fromisoformat(msg_data["timestamp"]),
                    query=msg_data.get("query"),
                    context=msg_data.get("context"),
                    citations=msg_data.get("citations", [])
                )
                session.messages.append(msg)

            return session
        except Exception as e:
            print(f"加载会话失败：{e}")
            return None

    def _load_all_sessions(self):
        """加载所有已保存的会话"""
        if not os.path.exists(self.persist_dir):
            return

        for filename in os.listdir(self.persist_dir):
            if filename.endswith(".json"):
                session_id = filename[:-5]  # 移除 .json 后缀
                session = self._load_session(session_id)
                if session:
                    self._sessions[session_id] = session

    def get_session(self, session_id: str = "default") -> ConversationHistory:
        """获取会话历史"""
        # 先检查内存
        if session_id in self._sessions:
            return self._sessions[session_id]

        # 尝试从文件加载
        if self.persist_to_file:
            session = self._load_session(session_id)
            if session:
                self._sessions[session_id] = session
                return session

        # 创建新会话
        self._sessions[session_id] = ConversationHistory(
            messages=[],
            max_turns=self.max_turns,
            session_id=session_id
        )
        return self._sessions[session_id]

    def add_user_message(self, query: str, session_id: str = "default",
                         content: Optional[str] = None):
        """添加用户消息"""
        session = self.get_session(session_id)
        session.add_message(
            role="user",
            content=content or query,
            query=query
        )
        # 保存会话到文件
        if self.persist_to_file:
            self._save_session(session_id)

    def add_assistant_message(self, content: str, session_id: str = "default",
                              context: Optional[str] = None,
                              citations: Optional[List[Dict]] = None):
        """添加助手消息"""
        session = self.get_session(session_id)
        session.add_message(
            role="assistant",
            content=content,
            context=context,
            citations=citations or []
        )
        # 保存会话到文件
        if self.persist_to_file:
            self._save_session(session_id)

    def resolve_coreference(self, query: str, session_id: str = "default") -> str:
        """
        解析指代消解，补全省略信息

        Args:
            query: 当前查询
            session_id: 会话 ID

        Returns:
            补全后的查询
        """
        if not self.enable_coreference:
            return query

        session = self.get_session(session_id)

        # 检查是否需要补全（包含指代词或省略）
        coreference_keywords = ["那", "呢", "这个", "那个", "上述", "前者", "后者", "如何", "怎样"]
        ellipsis_patterns = [
            "那.*呢",      # "那上海呢？"
            ".*怎么样",    # "上海怎么样？"
            ".*什么标准",  # "上海什么标准？"
        ]

        needs_resolution = (
            any(kw in query for kw in coreference_keywords) or
            any(__import__('re').search(p, query) for p in ellipsis_patterns)
        )

        if not needs_resolution:
            return query

        # 获取对话历史和已提及实体
        entities = session.get_entities_mentioned()
        last_query = session.get_last_user_query()
        summary = session.get_conversation_summary()

        if not entities["topics"]:
            # 没有已提及的话题，无法补全
            return query

        # 使用 LLM 进行指代消解
        llm = self._get_llm()

        coref_prompt = f"""你是一个指代消解助手。根据对话历史，补全当前查询中省略的信息。

## 对话历史
{summary}

## 已提及的实体
- 地点：{', '.join(entities['locations']) if entities['locations'] else '无'}
- 话题：{', '.join(entities['topics']) if entities['topics'] else '无'}
- 部门：{', '.join(entities['departments']) if entities['departments'] else '无'}

## 当前查询
{query}

## 任务
如果当前查询包含指代词（如"那"、"呢"、"这个"等）或有省略，请根据对话历史补全信息。
如果查询已经完整，请保持原样。

## 输出格式
请只输出补全后的查询，不要输出其他内容。

示例：
- 输入："出差补助多少？" → 已提及话题：出差补助
- 后续输入："那上海呢？" → 输出："上海的出差补助标准是多少？"

补全后的查询："""

        try:
            response = llm.complete(coref_prompt)
            resolved_query = str(response).strip()

            # 如果 LLM 没有补全，尝试简单规则补全
            if resolved_query == query:
                # 检查是否包含地点但缺少话题
                location_keywords = ["北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "西安", "重庆"]
                found_locations = [loc for loc in location_keywords if loc in query]

                if found_locations and entities["topics"]:
                    # 有地点但话题省略，尝试补全
                    main_topic = entities["topics"][0] if entities["topics"] else ""
                    resolved_query = f"{found_locations[0]}的{main_topic}标准是什么？"

            return resolved_query

        except Exception as e:
            # LLM 失败时，返回原始查询
            print(f"指代消解失败：{e}")
            return query

    def should_use_conversation_context(self, query: str, session_id: str = "default") -> bool:
        """
        判断是否需要使用对话上下文来增强检索

        Args:
            query: 当前查询
            session_id: 会话 ID

        Returns:
            是否使用上下文
        """
        session = self.get_session(session_id)

        # 检查是否有对话历史
        if not session.messages:
            return False

        # 检查问题是否简短（可能是追问）
        if len(query) < 15:
            return True

        # 检查是否包含指代词
        pronouns = ["这", "那", "其", "上述", "前者", "后者", "他", "她", "它"]
        if any(p in query for p in pronouns):
            return True

        return False

    def enrich_query_with_context(self, query: str, session_id: str = "default") -> str:
        """
        使用对话上下文增强查询

        Args:
            query: 当前查询
            session_id: 会话 ID

        Returns:
            增强后的查询
        """
        session = self.get_session(session_id)

        if not session.messages:
            return query

        # 获取最近的话题
        entities = session.get_entities_mentioned()
        summary = session.get_conversation_summary()

        # 构建增强查询
        if entities["topics"] and len(query) < 20:
            # 短查询，可能需要补充话题
            main_topic = entities["topics"][-1]  # 最近的话题
            return f"关于{main_topic}：{query}"

        return query

    def get_context_for_retrieval(self, query: str, session_id: str = "default") -> Optional[str]:
        """
        获取用于检索增强的上下文信息

        Args:
            query: 当前查询
            session_id: 会话 ID

        Returns:
            上下文信息（如果需要使用）
        """
        if not self.should_use_conversation_context(query, session_id):
            return None

        session = self.get_session(session_id)
        entities = session.get_entities_mentioned()

        # 构建上下文
        context_parts = []

        if entities["topics"]:
            context_parts.append(f"当前讨论话题：{', '.join(entities['topics'])}")
        if entities["locations"]:
            context_parts.append(f"已提及地点：{', '.join(entities['locations'])}")
        if entities["departments"]:
            context_parts.append(f"已提及部门：{', '.join(entities['departments'])}")

        return "; ".join(context_parts) if context_parts else None

    def clear_session(self, session_id: str = "default"):
        """清空会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def get_session_info(self, session_id: str = "default") -> Dict:
        """获取会话信息"""
        session = self.get_session(session_id)
        return {
            "session_id": session_id,
            "message_count": len(session.messages),
            "max_turns": session.max_turns,
            "entities_mentioned": session.get_entities_mentioned()
        }


# ==================== 全局实例 ====================

# 注意：在 Streamlit 环境中，不要使用全局变量存储会话数据
# Streamlit 每次交互都会重新运行脚本，导致全局变量重置
# 应该使用 st.cache_resource 或将会话 ID 存储在 st.session_state 中
# 然后在 app.py 中每次调用时从 st.session_state 获取 session_id


def get_conversation_manager(max_turns: int = 5, persist_to_file: bool = False) -> ConversationManager:
    """
    获取 ConversationManager 实例

    Args:
        max_turns: 最大对话轮数
        persist_to_file: 是否持久化到文件（Streamlit 环境下建议设为 True）

    注意：在 Streamlit 环境中，应该使用 st.cache_resource 缓存此实例
    并在 app.py 中管理会话 ID
    """
    return ConversationManager(max_turns=max_turns, persist_to_file=persist_to_file)


def process_followup_query(query: str, session_id: str = "default") -> Tuple[str, Optional[str]]:
    """
    处理追问：指代消解 + 上下文增强

    Args:
        query: 当前查询
        session_id: 会话 ID

    Returns:
        (处理后的查询，上下文信息)
    """
    manager = get_conversation_manager()

    # 指代消解
    resolved_query = manager.resolve_coreference(query, session_id)

    # 获取上下文
    context = manager.get_context_for_retrieval(resolved_query, session_id)

    return resolved_query, context
