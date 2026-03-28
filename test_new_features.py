"""
RAG 系统新功能测试脚本

测试功能:
1. 反思链路 (Reasoning Judge) - 判断文档是否有答案
2. 反馈收集 (Feedback Collector) - 点赞/踩反馈
3. 多轮对话管理 (Conversation Manager) - 追问理解
"""

import os
import sys

# 设置环境变量
os.environ["DASHSCOPE_API_KEY"] = os.getenv("DASHSCOPE_API_KEY", "sk-test-key")


def test_reasoning_judge():
    """测试反思链路功能"""
    print("\n" + "=" * 60)
    print("测试反思链路 (Reasoning Judge)")
    print("=" * 60)

    from reasoning_judge import ReasoningJudge, JudgmentResult

    judge = ReasoningJudge(api_key=os.getenv("DASHSCOPE_API_KEY"))

    # 测试用例 1: 有答案的情况
    print("\n[测试 1] 文档中有答案的情况")
    query1 = "出差补助标准是多少？"
    context1 = """
    [1] 公司员工差旅管理办法 第 3 页
    国内出差补助标准：一线城市每天 200 元，其他城市每天 150 元。
    住宿费上限标准：一线城市每天 400 元，其他城市每天 300 元。
    """

    result1 = judge.judge(query1, context1)
    print(f"判断结果：{result1.result.value}")
    print(f"置信度：{result1.confidence:.0%}")
    print(f"推理过程：{result1.reasoning}")
    print(f"相关片段数：{result1.relevant_chunks}")
    print(f"可否回答：{result1.can_answer}")

    # 测试用例 2: 无答案的情况
    print("\n[测试 2] 文档中无答案的情况")
    query2 = "公司年终奖发多少？"
    context2 = """
    [1] 公司员工差旅管理办法 第 5 页
    出差报销需要提供有效发票，经部门负责人审批后报销。
    交通费用按实际发生金额报销。
    """

    result2 = judge.judge(query2, context2)
    print(f"判断结果：{result2.result.value}")
    print(f"置信度：{result2.confidence:.0%}")
    print(f"推理过程：{result2.reasoning}")
    print(f"相关片段数：{result2.relevant_chunks}")
    print(f"可否回答：{result2.can_answer}")

    # 测试用例 3: 生成最终响应
    print("\n[测试 3] 生成最终响应")
    original_answer = "根据文档，国内出差补助标准为：一线城市每天 200 元，其他城市每天 150 元。"
    final_response, thinking = judge.generate_response(query1, result1, context1, original_answer)

    print("最终响应预览:")
    print(final_response[:200] + "...")

    print("\n思考过程:")
    print(thinking)

    print("\n✅ 反思链路测试完成")


def test_feedback_collector():
    """测试反馈收集功能"""
    print("\n" + "=" * 60)
    print("测试反馈收集 (Feedback Collector)")
    print("=" * 60)

    from feedback_collector import FeedbackCollector, get_feedback_collector

    collector = get_feedback_collector(storage_path="./test_feedback_logs")

    # 测试用例 1: 添加点赞反馈
    print("\n[测试 1] 添加点赞反馈")
    entry1 = collector.add_feedback(
        question="出差补助标准是多少？",
        answer="根据文档，一线城市每天 200 元，其他城市每天 150 元。",
        feedback_type="upvote",
        citations=[{"file_name": "差旅管理办法.pdf", "page_num": 3}],
        session_id="test_session_001"
    )
    print(f"反馈已记录：{entry1.question[:20]}... | 类型：{entry1.feedback_type}")

    # 测试用例 2: 添加点踩反馈
    print("\n[测试 2] 添加点踩反馈")
    entry2 = collector.add_feedback(
        question="公司年终奖发多少？",
        answer="公司年终奖根据个人绩效和公司业绩确定。",
        feedback_type="downvote",
        user_comment="回答太笼统，没有具体说明",
        session_id="test_session_001"
    )
    print(f"反馈已记录：{entry2.question[:20]}... | 类型：{entry2.feedback_type}")
    print(f"用户评论：{entry2.user_comment}")

    # 测试用例 3: 获取统计信息
    print("\n[测试 3] 获取统计信息")
    stats = collector.get_stats()
    print(f"总反馈数：{stats['total_feedbacks']}")
    print(f"30 天内点赞：{stats['upvotes_30d']}")
    print(f"30 天内点踩：{stats['downvotes_30d']}")
    print(f"满意度：{stats['satisfaction_rate']:.0%}")

    # 测试用例 4: 生成负面反馈报告
    print("\n[测试 4] 生成负面反馈报告")
    report = collector.generate_downvote_report(days=7)
    print("报告预览:")
    print(report[:500] + "...")

    # 测试用例 5: 导出 CSV
    print("\n[测试 5] 导出 CSV")
    csv_path = collector.export_to_csv()
    print(f"CSV 已导出到：{csv_path}")

    print("\n✅ 反馈收集测试完成")


def test_conversation_manager():
    """测试多轮对话管理功能"""
    print("\n" + "=" * 60)
    print("测试多轮对话管理 (Conversation Manager)")
    print("=" * 60)

    from conversation_manager import ConversationManager, get_conversation_manager

    manager = get_conversation_manager(max_turns=5)
    session_id = "test_conversation_001"

    # 清除旧会话（如果有）
    manager.clear_session(session_id)

    # 测试用例 1: 添加对话历史
    print("\n[测试 1] 添加对话历史")
    manager.add_user_message("出差补助多少？", session_id)
    manager.add_assistant_message(
        "根据文档，国内出差补助标准为：一线城市每天 200 元，其他城市每天 150 元。",
        session_id,
        context="差旅管理办法文档",
        citations=[{"file_name": "差旅管理办法.pdf", "page_num": 3}]
    )
    print("已添加第一轮对话")

    manager.add_user_message("北京属于一线城市吗？", session_id)
    manager.add_assistant_message(
        "是的，北京属于一线城市，出差补助标准为每天 200 元。",
        session_id
    )
    print("已添加第二轮对话")

    # 测试用例 2: 获取已提及的实体
    print("\n[测试 2] 获取已提及的实体")
    session = manager.get_session(session_id)
    entities = session.get_entities_mentioned()
    print(f"地点：{entities['locations']}")
    print(f"话题：{entities['topics']}")

    # 测试用例 3: 指代消解（处理追问）
    print("\n[测试 3] 指代消解 - 处理追问")
    followup_query = "那上海呢？"
    resolved = manager.resolve_coreference(followup_query, session_id)
    print(f"原始问题：{followup_query}")
    print(f"解析后：{resolved}")

    # 测试用例 4: 判断是否需要上下文
    print("\n[测试 4] 判断是否需要上下文")
    short_query = "广州呢？"
    needs_context = manager.should_use_conversation_context(short_query, session_id)
    print(f"查询：{short_query}")
    print(f"需要上下文：{needs_context}")

    # 测试用例 5: 上下文增强查询
    print("\n[测试 5] 上下文增强查询")
    enriched = manager.enrich_query_with_context(short_query, session_id)
    print(f"原始查询：{short_query}")
    print(f"增强后：{enriched}")

    # 测试用例 6: 获取会话信息
    print("\n[测试 6] 获取会话信息")
    info = manager.get_session_info(session_id)
    print(f"会话 ID: {info['session_id']}")
    print(f"消息数：{info['message_count']}")
    print(f"提及实体：{info['entities_mentioned']}")

    print("\n✅ 多轮对话管理测试完成")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("RAG 系统新功能测试")
    print("=" * 60)

    try:
        test_reasoning_judge()
    except Exception as e:
        print(f"\n❌ 反思链路测试失败：{e}")

    try:
        test_feedback_collector()
    except Exception as e:
        print(f"\n❌ 反馈收集测试失败：{e}")

    try:
        test_conversation_manager()
    except Exception as e:
        print(f"\n❌ 多轮对话管理测试失败：{e}")

    print("\n" + "=" * 60)
    print("测试全部完成")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
