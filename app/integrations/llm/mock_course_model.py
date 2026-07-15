"""Deterministic offline chat model used by local and end-to-end tests.

The mock still emits native model tool calls, so the same ``create_agent``
graph, tools, middleware and checkpoints are exercised without network access.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Sequence
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool


def _latest_user_text(messages: list[BaseMessage]) -> str:
    return next(
        (
            str(message.content)
            for message in reversed(messages)
            if isinstance(message, HumanMessage)
        ),
        "",
    )


def _tool_result_reply(message: ToolMessage) -> str:
    name = str(message.name or "")
    try:
        payload = json.loads(str(message.content or "{}"))
    except (TypeError, ValueError):
        payload = {}
    if payload.get("deleted") is True:
        return "任务已删除。"
    if payload.get("deleted") is False:
        return "任务不存在或已经删除。"
    if name == "search_course_knowledge":
        total = int(payload.get("total") or 0)
        return f"我已根据课程资料整理出结论，并参考了 {total} 个相关片段。"
    if name == "search_external_learning_resources":
        total = len(payload.get("resources") or [])
        return f"已为你整理 {total} 个外部学习资源。"
    if name == "generate_practice_questions":
        return "练习题已生成，请直接在下方作答。"
    if name == "generate_diagnostic_questions":
        return "诊断题已生成，请直接在下方作答。"
    if name == "get_today_learning":
        return "今天的学习安排已显示在下方。"
    if name == "get_course_progress":
        return "当前课程进度和掌握情况已显示在下方。"
    if name == "get_study_plan":
        return "当前学习计划已显示在下方。"
    if name == "get_wrong_answer_summary":
        return "错题汇总已显示在下方。"
    return "工具执行完成。"


def _tool_call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": f"mock-{uuid4().hex}",
                "type": "tool_call",
            }
        ],
    )


class MockCourseChatModel(BaseChatModel):
    """Small intent router that behaves like a native tool-calling model."""

    @property
    def _llm_type(self) -> str:
        return "a3-offline-course-agent"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        if messages and isinstance(messages[-1], ToolMessage):
            response = AIMessage(content=_tool_result_reply(messages[-1]))
            return ChatResult(generations=[ChatGeneration(message=response)])

        text = _latest_user_text(messages)
        lowered = text.casefold()
        task_match = re.search(r"(?:删除|移除)\s*(?:任务)?\s*(\d+)", text)
        count_match = re.search(r"(\d+)\s*道", text)

        if task_match:
            response = _tool_call("delete_task", {"task_id": int(task_match.group(1))})
        elif any(word in lowered for word in ("视频", "网上", "外部资源", "推荐资源")):
            response = _tool_call("search_external_learning_resources", {"topic": text})
        elif any(word in lowered for word in ("出题", "道题", "练习", "做题", "练几道")):
            response = _tool_call(
                "generate_practice_questions",
                {
                    "knowledge_point_id": None,
                    "question_count": int(count_match.group(1)) if count_match else 3,
                    "difficulty": "medium",
                },
            )
        elif "诊断" in lowered:
            response = _tool_call("generate_diagnostic_questions", {})
        elif "今天" in lowered:
            response = _tool_call("get_today_learning", {})
        elif any(word in lowered for word in ("进度", "掌握", "薄弱")):
            response = _tool_call("get_course_progress", {})
        elif "计划" in lowered:
            response = _tool_call("get_study_plan", {})
        elif "错题" in lowered:
            response = _tool_call("get_wrong_answer_summary", {})
        elif any(
            word in lowered
            for word in ("资料", "讲解", "解释", "什么是", "根据", "总结", "课程内容")
        ):
            response = _tool_call(
                "search_course_knowledge",
                {"query": text, "result_count": 8},
            )
        else:
            response = AIMessage(content=f"已收到你的问题：{text}")
        return ChatResult(generations=[ChatGeneration(message=response)])


__all__ = ["MockCourseChatModel"]
