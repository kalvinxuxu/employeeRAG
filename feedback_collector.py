"""
反馈收集系统 (Feedback Loop) - 收集用户对 AI 回答的点赞/踩反馈

功能:
- 收集员工对答案的点赞/踩反馈
- 被"踩"的问题自动汇总成报告
- 提醒 HR 补充或更新相关文档
"""

import os
import json
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class FeedbackEntry:
    """反馈条目"""
    question: str                    # 用户问题
    answer: str                      # AI 回答
    feedback_type: str               # "upvote" | "downvote"
    created_at: datetime             # 反馈时间
    context_hash: str = ""           # 上下文哈希
    citations: List[Dict] = field(default_factory=list)  # 引用来源
    user_comment: str = ""           # 用户评论（可选）
    session_id: str = ""             # 会话 ID
    metadata: Dict = field(default_factory=dict)  # 其他元数据


class FeedbackCollector:
    """反馈收集器"""

    def __init__(self, storage_path: str = "./feedback_logs",
                 auto_report: bool = True,
                 report_format: str = "markdown"):
        """
        初始化反馈收集器

        Args:
            storage_path: 存储路径
            auto_report: 是否自动生成报告
            report_format: 报告格式 ("markdown" | "json" | "csv")
        """
        self.storage_path = Path(storage_path)
        self.auto_report = auto_report
        self.report_format = report_format

        # 确保目录存在
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # 反馈文件路径
        self.feedback_file = self.storage_path / "feedback_logs.json"
        self.report_file = self.storage_path / "downvote_report.md"

        # 内存缓存
        self._feedbacks: List[FeedbackEntry] = []
        self._load_feedbacks()

    def _load_feedbacks(self):
        """从文件加载反馈"""
        if self.feedback_file.exists():
            try:
                with open(self.feedback_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        self._feedbacks.append(FeedbackEntry(
                            question=item.get("question", ""),
                            answer=item.get("answer", ""),
                            feedback_type=item.get("feedback_type", ""),
                            created_at=datetime.fromisoformat(item.get("created_at", datetime.now().isoformat())),
                            context_hash=item.get("context_hash", ""),
                            citations=item.get("citations", []),
                            user_comment=item.get("user_comment", ""),
                            session_id=item.get("session_id", ""),
                            metadata=item.get("metadata", {})
                        ))
            except Exception as e:
                print(f"加载反馈文件失败：{e}")

    def _save_feedbacks(self):
        """保存反馈到文件"""
        try:
            data = []
            for entry in self._feedbacks:
                data.append({
                    "question": entry.question,
                    "answer": entry.answer,
                    "feedback_type": entry.feedback_type,
                    "created_at": entry.created_at.isoformat(),
                    "context_hash": entry.context_hash,
                    "citations": entry.citations,
                    "user_comment": entry.user_comment,
                    "session_id": entry.session_id,
                    "metadata": entry.metadata
                })

            with open(self.feedback_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存反馈文件失败：{e}")

    def add_feedback(self, question: str, answer: str, feedback_type: str,
                     citations: Optional[List[Dict]] = None,
                     user_comment: str = "",
                     session_id: str = "",
                     context_hash: str = "") -> FeedbackEntry:
        """
        添加反馈

        Args:
            question: 用户问题
            answer: AI 回答
            feedback_type: "upvote" | "downvote"
            citations: 引用来源
            user_comment: 用户评论
            session_id: 会话 ID
            context_hash: 上下文哈希

        Returns:
            反馈条目
        """
        entry = FeedbackEntry(
            question=question,
            answer=answer,
            feedback_type=feedback_type,
            created_at=datetime.now(),
            context_hash=context_hash,
            citations=citations or [],
            user_comment=user_comment,
            session_id=session_id
        )

        self._feedbacks.append(entry)
        self._save_feedbacks()

        # 如果是负面反馈且启用自动报告，生成报告
        if feedback_type == "downvote" and self.auto_report:
            self.generate_downvote_report()

        return entry

    def get_downvotes(self, days: int = 7) -> List[FeedbackEntry]:
        """
        获取指定天数内的负面反馈

        Args:
            days: 天数

        Returns:
            负面反馈列表
        """
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        return [
            f for f in self._feedbacks
            if f.feedback_type == "downvote" and f.created_at >= cutoff
        ]

    def get_upvotes(self, days: int = 7) -> List[FeedbackEntry]:
        """获取指定天数内的正面反馈"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        return [
            f for f in self._feedbacks
            if f.feedback_type == "upvote" and f.created_at >= cutoff
        ]

    def generate_downvote_report(self, days: int = 7,
                                  output_path: Optional[str] = None) -> str:
        """
        生成负面反馈汇总报告

        Args:
            days: 汇总天数
            output_path: 输出路径（默认使用配置的 report_file）

        Returns:
            报告内容
        """
        downvotes = self.get_downvotes(days)

        if not downvotes:
            return "## 暂无负面反馈\n\n在过去 {} 天内没有收到负面反馈。".format(days)

        # 按问题分组统计
        question_groups: Dict[str, List[FeedbackEntry]] = {}
        for entry in downvotes:
            # 简化问题作为 key（前 50 字）
            question_key = entry.question[:50] + "..." if len(entry.question) > 50 else entry.question
            if question_key not in question_groups:
                question_groups[question_key] = []
            question_groups[question_key].append(entry)

        # 生成 Markdown 报告
        report_lines = [
            "# 📋 负面反馈汇总报告",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**统计周期**: 过去 {days} 天",
            f"**负面反馈总数**: {len(downvotes)} 条",
            f"**涉及问题数**: {len(question_groups)} 个",
            "",
            "---",
            "",
            "## 📊 问题汇总",
            ""
        ]

        # 按被踩次数排序
        sorted_questions = sorted(
            question_groups.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )

        for idx, (question, entries) in enumerate(sorted_questions, 1):
            report_lines.extend([
                f"### {idx}. {question}",
                "",
                f"**被踩次数**: {len(entries)} 次",
                "",
                "**AI 回答示例**:",
                "",
                f"> {entries[0].answer[:200]}..." if len(entries[0].answer) > 200 else f"> {entries[0].answer}",
                ""
            ])

            # 显示引用来源
            if entries[0].citations:
                report_lines.append("**参考来源**:")
                for citation in entries[0].citations[:3]:
                    file_name = citation.get("file_name", "未知")
                    page_num = citation.get("page_num", "")
                    report_lines.append(f"- {file_name} 第{page_num}页")
                report_lines.append("")

            # 用户评论
            comments = [e.user_comment for e in entries if e.user_comment]
            if comments:
                report_lines.extend([
                    "**用户反馈**:",
                    "",
                ])
                for comment in comments:
                    report_lines.append(f"- {comment}")
                report_lines.append("")

            # 时间线
            report_lines.append("**反馈时间**:")
            for entry in entries:
                report_lines.append(f"- {entry.created_at.strftime('%Y-%m-%d %H:%M')}")
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")

        # 添加建议
        report_lines.extend([
            "## 💡 处理建议",
            "",
            "1. **高频问题优先处理**: 被踩次数多的问题优先审查",
            "2. **检查文档完整性**: 确认相关文档是否覆盖了用户关心的内容",
            "3. **更新文档**: 根据用户反馈补充或修订文档",
            "4. **优化检索**: 检查检索策略是否需要调整",
            "",
            "---",
            "",
            "*本报告由系统自动生成*"
        ])

        report_content = "\n".join(report_lines)

        # 保存报告
        output_file = output_path or self.report_file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        return report_content

    def get_stats(self) -> Dict:
        """获取反馈统计"""
        total = len(self._feedbacks)
        upvotes = len(self.get_upvotes(30))  # 30 天内
        downvotes = len(self.get_downvotes(30))

        return {
            "total_feedbacks": total,
            "upvotes_30d": upvotes,
            "downvotes_30d": downvotes,
            "satisfaction_rate": upvotes / max(upvotes + downvotes, 1),
            "downvote_categories": self._analyze_downvote_categories()
        }

    def _analyze_downvote_categories(self) -> Dict[str, int]:
        """分析负面反馈分类"""
        categories: Dict[str, int] = {}
        for entry in self._feedbacks:
            if entry.feedback_type != "downvote":
                continue

            # 根据问题内容简单分类
            question = entry.question.lower()
            if any(kw in question for kw in ["报销", "发票", "财务"]):
                categories["财务报销"] = categories.get("财务报销", 0) + 1
            elif any(kw in question for kw in ["考勤", "请假", "加班"]):
                categories["考勤管理"] = categories.get("考勤管理", 0) + 1
            elif any(kw in question for kw in ["出差", "差旅"]):
                categories["出差管理"] = categories.get("出差管理", 0) + 1
            elif any(kw in question for kw in ["招聘", "面试", "入职"]):
                categories["招聘管理"] = categories.get("招聘管理", 0) + 1
            else:
                categories["其他"] = categories.get("其他", 0) + 1

        return categories

    def export_to_csv(self, output_path: Optional[str] = None) -> str:
        """导出反馈数据为 CSV"""
        import csv

        output_file = output_path or (self.storage_path / "feedback_export.csv")

        with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["时间", "类型", "问题", "回答", "用户评论", "引用来源"])

            for entry in self._feedbacks:
                citations_str = "; ".join([
                    f"{c.get('file_name', '未知')}第{c.get('page_num', '')}页"
                    for c in entry.citations[:3]
                ])
                writer.writerow([
                    entry.created_at.strftime("%Y-%m-%d %H:%M"),
                    "👍" if entry.feedback_type == "upvote" else "👎",
                    entry.question,
                    entry.answer[:500] if len(entry.answer) > 500 else entry.answer,
                    entry.user_comment,
                    citations_str
                ])

        return str(output_file)


# ==================== 全局实例 ====================

_default_collector: Optional[FeedbackCollector] = None


def get_feedback_collector(storage_path: str = "./feedback_logs") -> FeedbackCollector:
    """获取全局 FeedbackCollector 实例"""
    global _default_collector
    if _default_collector is None:
        _default_collector = FeedbackCollector(storage_path=storage_path)
    return _default_collector


def submit_feedback(question: str, answer: str, is_upvote: bool,
                    citations: Optional[List[Dict]] = None,
                    comment: str = "") -> FeedbackEntry:
    """
    便捷函数：提交反馈

    Args:
        question: 问题
        answer: 回答
        is_upvote: 是否点赞
        citations: 引用
        comment: 评论

    Returns:
        反馈条目
    """
    collector = get_feedback_collector()
    return collector.add_feedback(
        question=question,
        answer=answer,
        feedback_type="upvote" if is_upvote else "downvote",
        citations=citations,
        user_comment=comment
    )
