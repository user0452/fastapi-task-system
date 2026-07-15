"""Deprecated compatibility facade over the shared create-agent runtime."""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.integrations.llm.agent_runtime import (
    invoke_agent_content,
    invoke_agent_messages,
    invoke_agent_structured,
    stream_agent_content,
)
from app.integrations.llm.model_provider import get_llm
from models import ExamInfo, ReviewTaskPreview


class ExamScheduleResult(BaseModel):
    exams: list[ExamInfo] = Field(default_factory=list)


class ReviewPlanResult(BaseModel):
    tasks_preview: list[ReviewTaskPreview] = Field(default_factory=list)


def ask_llm(user_text: str) -> str:
    return invoke_agent_content(
        [
            SystemMessage(content="你是一个严谨、简洁的学习助手。"),
            HumanMessage(content=user_text),
        ]
    )


def parse_exam_schedule(text: str) -> dict:
    result = invoke_agent_structured(
        [
            SystemMessage(
                content=(
                    "你是考试安排解析助手。提取课程名、YYYY-MM-DD 日期和可选的 HH:MM 时间；"
                    "不能确定的时间留空，不要猜测。"
                )
            ),
            HumanMessage(content=text),
        ],
        ExamScheduleResult,
    )
    validated = result if isinstance(result, ExamScheduleResult) else ExamScheduleResult.model_validate(result)
    return validated.model_dump()


def preview_review_plan(exams: list[dict]) -> dict:
    result = invoke_agent_structured(
        [
            SystemMessage(
                content=(
                    "你是复习任务规划助手。根据考试先后和剩余时间生成具体、可执行的任务；"
                    "任务状态使用 todo，优先级仅使用 low、medium、high。"
                )
            ),
            HumanMessage(content=json.dumps(exams, ensure_ascii=False)),
        ],
        ReviewPlanResult,
    )
    validated = result if isinstance(result, ReviewPlanResult) else ReviewPlanResult.model_validate(result)
    return validated.model_dump()


__all__ = [
    "ask_llm",
    "get_llm",
    "invoke_agent_content",
    "invoke_agent_messages",
    "invoke_agent_structured",
    "parse_exam_schedule",
    "preview_review_plan",
    "stream_agent_content",
]
