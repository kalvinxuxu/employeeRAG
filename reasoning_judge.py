"""
反思链路 (Reasoning Judge) - 让大模型在回答前先判断文档是否有答案

功能:
- 让 LLM 先判断提供的文档中是否包含问题答案
- 如果没有，直接回答"不知道"，避免幻觉
- 显性展示判断过程，让用户看到分析步骤
"""

import os
from typing import Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class JudgmentResult(Enum):
    """判断结果"""
    ANSWER_FOUND = "answer_found"      # 找到答案
    PARTIAL_FOUND = "partial_found"    # 部分相关信息
    NO_ANSWER = "no_answer"            # 无答案
    UNCERTAIN = "uncertain"            # 不确定


@dataclass
class JudgmentOutput:
    """判断输出"""
    result: JudgmentResult             # 判断结果
    confidence: float                  # 置信度 (0-1)
    reasoning: str                     # 推理过程
    relevant_chunks: int               # 相关片段数量
    can_answer: bool                   # 是否可以回答


class ReasoningJudge:
    """反思判断器"""

    def __init__(self, llm_model: str = "qwen-plus", api_key: Optional[str] = None):
        """
        初始化反思判断器

        Args:
            llm_model: LLM 模型名称
            api_key: DashScope API Key
        """
        self.llm_model = llm_model
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self._llm = None

    def _get_llm(self):
        """懒加载 LLM"""
        if self._llm is None:
            try:
                from llama_index.llms.dashscope import DashScope
                self._llm = DashScope(model=self.llm_model, api_key=self.api_key)
            except ImportError:
                raise ImportError("请安装 llama-index-llms-dashscope")
        return self._llm

    def judge(self, query: str, context: str) -> JudgmentOutput:
        """
        判断文档中是否包含问题答案

        Args:
            query: 用户问题
            context: 检索到的上下文

        Returns:
            判断输出
        """
        if not context or not context.strip():
            return JudgmentOutput(
                result=JudgmentResult.NO_ANSWER,
                confidence=1.0,
                reasoning="未提供任何参考文档",
                relevant_chunks=0,
                can_answer=False
            )

        llm = self._get_llm()

        # 构建判断 Prompt
        judge_prompt = f"""你是一个严谨的文档分析助手。请分析以下参考资料是否包含用户问题的答案。

## 用户问题
{query}

## 参考资料
{context}

## 分析任务
1. 仔细阅读参考资料
2. 判断资料中是否包含问题答案
3. 如果有答案，说明在哪些片段中
4. 如果没有答案，说明原因

## 输出格式
请严格按照以下 JSON 格式输出：
{{
    "result": "answer_found|partial_found|no_answer|uncertain",
    "confidence": 0.0-1.0,
    "reasoning": "简要说明分析过程和依据",
    "relevant_chunks": 相关片段数量 (整数),
    "can_answer": true/false
}}

判断标准：
- answer_found: 参考资料明确包含问题答案
- partial_found: 参考资料包含部分相关信息，但不足以完整回答
- no_answer: 参考资料与问题无关，或不包含答案
- uncertain: 无法确定（模糊、矛盾等情况）

请只输出 JSON，不要输出其他内容。"""

        try:
            response = llm.complete(judge_prompt)
            output_text = str(response).strip()

            # 解析 JSON 输出
            import json
            import re

            # 提取 JSON 部分（可能包含在代码块中）
            json_match = re.search(r'\{[\s\S]*\}', output_text)
            if json_match:
                output_text = json_match.group()

            data = json.loads(output_text)

            # 解析结果
            result_map = {
                "answer_found": JudgmentResult.ANSWER_FOUND,
                "partial_found": JudgmentResult.PARTIAL_FOUND,
                "no_answer": JudgmentResult.NO_ANSWER,
                "uncertain": JudgmentResult.UNCERTAIN
            }

            result = result_map.get(data.get("result", "uncertain"), JudgmentResult.UNCERTAIN)
            confidence = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning", "无法解析推理过程")
            relevant_chunks = int(data.get("relevant_chunks", 0))
            can_answer = bool(data.get("can_answer", False))

            return JudgmentOutput(
                result=result,
                confidence=confidence,
                reasoning=reasoning,
                relevant_chunks=relevant_chunks,
                can_answer=can_answer
            )

        except Exception as e:
            # 解析失败时，降级处理
            return JudgmentOutput(
                result=JudgmentResult.UNCERTAIN,
                confidence=0.5,
                reasoning=f"判断过程出错：{str(e)}",
                relevant_chunks=0,
                can_answer=True  # 降级为允许回答
            )

    def generate_response(self, query: str, judgment: JudgmentOutput,
                         context: str, original_answer: str) -> Tuple[str, str]:
        """
        根据判断结果生成最终响应

        Args:
            query: 用户问题
            judgment: 判断输出
            context: 上下文
            original_answer: 原始 AI 回答

        Returns:
            (最终响应，展示的思考过程)
        """
        # 构建思考过程展示
        thinking_process = self._format_thinking_process(judgment)

        # 根据判断结果决定响应
        if judgment.result == JudgmentResult.NO_ANSWER:
            # 没有答案，直接告知用户
            final_response = (
                f"抱歉，根据提供的文档资料，我没有找到关于「{query}」的相关信息。"
                f"\n\n{thinking_process}"
            )
            return final_response, thinking_process

        elif judgment.result == JudgmentResult.PARTIAL_FOUND:
            # 部分信息，说明局限性
            final_response = (
                f"根据文档资料，我找到了一些相关信息，但可能不够完整：\n\n"
                f"{original_answer}\n\n{thinking_process}"
            )
            return final_response, thinking_process

        elif judgment.result == JudgmentResult.ANSWER_FOUND:
            # 找到答案，正常回答
            final_response = (
                f"根据文档资料，我找到了相关信息：\n\n"
                f"{original_answer}\n\n{thinking_process}"
            )
            return final_response, thinking_process

        else:
            # 不确定情况
            final_response = (
                f"我尝试分析了文档资料，但判断结果不够明确。"
                f"以下是我的回答，仅供参考：\n\n"
                f"{original_answer}\n\n{thinking_process}"
            )
            return final_response, thinking_process

    def _format_thinking_process(self, judgment: JudgmentOutput) -> str:
        """格式化思考过程展示"""
        result_emoji = {
            JudgmentResult.ANSWER_FOUND: "✅",
            JudgmentResult.PARTIAL_FOUND: "⚠️",
            JudgmentResult.NO_ANSWER: "❌",
            JudgmentResult.UNCERTAIN: "❓"
        }

        result_text = {
            JudgmentResult.ANSWER_FOUND: "在文档中找到答案",
            JudgmentResult.PARTIAL_FOUND: "找到部分相关信息",
            JudgmentResult.NO_ANSWER: "文档中无相关信息",
            JudgmentResult.UNCERTAIN: "判断结果不明确"
        }

        return (
            f"---\n"
            f"{result_emoji[judgment.result]} **分析结果**: {result_text[judgment.result]}\n\n"
            f"**置信度**: {judgment.confidence:.0%}\n\n"
            f"**分析过程**: {judgment.reasoning}\n\n"
            f"**参考片段数**: {judgment.relevant_chunks} 个\n"
        )


# ==================== 便捷函数 ====================

_default_judge: Optional[ReasoningJudge] = None


def get_reasoning_judge(model: str = "qwen-plus") -> ReasoningJudge:
    """获取全局 ReasoningJudge 实例"""
    global _default_judge
    if _default_judge is None:
        _default_judge = ReasoningJudge(llm_model=model)
    return _default_judge


def judge_and_respond(query: str, context: str, original_answer: str) -> Tuple[str, str]:
    """
    便捷函数：判断并生成响应

    Args:
        query: 用户问题
        context: 上下文
        original_answer: 原始 AI 回答

    Returns:
        (最终响应，思考过程)
    """
    judge = get_reasoning_judge()
    judgment = judge.judge(query, context)
    return judge.generate_response(query, judgment, context, original_answer)
