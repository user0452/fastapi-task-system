"""Small, auditable Fast RAG eligibility check; it never replaces tool choice."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.modules.agent.query_resolver import QueryResolution


@dataclass(frozen=True)
class RagRoute:
    route: str
    resolved_query: str
    confidence: float
    reason: str
    signals: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_AGENTIC_PATTERNS = (
    r"联网|网上|搜索.*网|查.*网|最新", r"出.{0,4}题|练习|测验|考试", r"学习计划|进度|错题|任务",
    r"记住|记忆|修改.*记忆|删除|更新|创建|添加", r"python|代码|计算|算一下",
    r"全文|整章|章节.*总结|总结.*章节|总结|概括", r"分别|逐个|步骤|然后|再.*", r"和.*(?:区别|比较)|(?:区别|比较).*和",
)


def choose_rag_route(
    *,
    message: str,
    course: dict | None,
    resolution: QueryResolution,
    confidence_threshold: float,
    enabled: bool,
    web_search_mode: str = "auto",
) -> RagRoute:
    compact = re.sub(r"\s+", "", message or "").casefold()
    signals = {
        "has_course": bool(course), "enabled": bool(enabled), "resolution_confidence": resolution.confidence,
        "web_search_mode": web_search_mode, "has_unresolved_reference": bool(resolution.unresolved_references),
    }
    if not enabled:
        return RagRoute("agentic_rag", resolution.resolved_query, resolution.confidence, "fast_rag_disabled", signals)
    if course is None:
        return RagRoute("agentic_rag", resolution.resolved_query, resolution.confidence, "no_active_course", signals)
    if web_search_mode == "on":
        return RagRoute("agentic_rag", resolution.resolved_query, resolution.confidence, "external_search_requested", signals)
    if not resolution.resolved_query or resolution.unresolved_references or resolution.confidence < confidence_threshold:
        return RagRoute("agentic_rag", resolution.resolved_query, resolution.confidence, "query_resolution_not_confident", signals)
    for pattern in _AGENTIC_PATTERNS:
        if re.search(pattern, compact, re.IGNORECASE):
            signals["agentic_pattern"] = pattern
            return RagRoute("agentic_rag", resolution.resolved_query, resolution.confidence, "requires_agent_tool_or_multi_step_reasoning", signals)
    return RagRoute("fast_rag", resolution.resolved_query, resolution.confidence, "single_topic_read_only_course_question", signals)


__all__ = ["RagRoute", "choose_rag_route"]
