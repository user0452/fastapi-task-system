"""Deterministic, course-chat focused query resolution without an LLM."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

REFERENCE_RE = re.compile(r"(?:那?它|这个|那[个里]|上一个|刚才那个|上述(?:内容|概念)?)")
LOW_INFORMATION_RE = re.compile(r"^[\s，。！？、？!,.]*?(?:它|这个|那个|那[个里]|上一个|刚才那个|为什么|怎么|讲一下|说说|呢|啊|呀|请问)*[\s，。！？、？!,.]*$")
FILLERS_RE = re.compile(r"^(?:请问|麻烦|帮我|帮忙|一下|讲一下|说说|解释一下|这个|那个|它|那)$")
ASCII_TOPIC_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_.-]{1,40}\b")


@dataclass(frozen=True)
class QueryResolution:
    original_query: str
    resolved_query: str
    focus_topic: str | None
    confidence: float
    resolution_source: str
    unresolved_references: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_query(query: str) -> str:
    return re.sub(r"\s+", " ", str(query or "")).strip()


def _topic_from_query(query: str) -> str | None:
    """Return only an explicit, conservative technical-looking topic candidate."""
    text = _clean_query(query)
    ascii_topics = [match.group(0) for match in ASCII_TOPIC_RE.finditer(text)]
    if ascii_topics:
        return max(ascii_topics, key=len)
    # A quoted Chinese term is an explicit topic, unlike arbitrary spoken filler.
    quoted = re.search(r"[\"“”']([^\"“”']{2,30})[\"“”']", text)
    if quoted:
        candidate = quoted.group(1).strip()
        if not FILLERS_RE.match(candidate):
            return candidate
    return None


def _unique_topics(state: dict[str, Any] | None, recent_messages: list[dict] | None) -> list[tuple[str, str]]:
    state = state or {}
    scoped_candidates: list[tuple[str, str]] = []
    for value, source in (
        (state.get("last_focus_topic"), "last_focus_topic"),
        (state.get("last_resolved_query"), "last_successful_search_query"),
        (state.get("last_original_query"), "last_original_query"),
    ):
        if not value:
            continue
        topic = str(value).strip() if source == "last_focus_topic" else _topic_from_query(str(value))
        if topic and not FILLERS_RE.match(topic):
            scoped_candidates.append((topic, source))
    if scoped_candidates:
        return _deduplicate_topics(scoped_candidates)

    point_names = [
        str(name).strip()
        for name in state.get("last_knowledge_point_names", []) or []
        if str(name).strip() and not FILLERS_RE.match(str(name).strip())
    ]
    if point_names:
        return _deduplicate_topics([(name, "last_knowledge_point_name") for name in point_names])

    candidates: list[tuple[str, str]] = []
    for message in reversed(recent_messages or []):
        topic = _topic_from_query(str(message.get("content") or ""))
        if topic and not FILLERS_RE.match(topic):
            candidates.append((topic, "recent_message"))
    return _deduplicate_topics(candidates)


def _deduplicate_topics(candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for topic, source in candidates:
        key = topic.casefold()
        if key not in seen:
            unique.append((topic, source))
            seen.add(key)
    return unique


def resolve_course_query(
    query: str,
    *,
    retrieval_state: dict[str, Any] | None = None,
    recent_messages: list[dict] | None = None,
    rolling_summary: str | None = None,
) -> QueryResolution:
    """Resolve only low-information course-chat references from scoped history.

    ``retrieval_state`` must already be loaded for the same user/course/session.
    The function deliberately does not inspect any global or cross-course context.
    """
    original = _clean_query(query)
    references = REFERENCE_RE.findall(original)
    if not references:
        return QueryResolution(original, original, _topic_from_query(original), 0.98, "original_query", [], "query_is_self_contained")

    candidates = _unique_topics(retrieval_state, recent_messages)
    # A summary can offer an explicitly quoted technical topic, but never decides alone.
    summary_topic = _topic_from_query(rolling_summary or "")
    if not candidates and summary_topic:
        candidates.append((summary_topic, "rolling_summary"))
    if len(candidates) != 1:
        return QueryResolution(
            original, original, None, 0.2 if not candidates else 0.35, "unresolved",
            references, "no_unique_scoped_course_focus",
        )
    topic, source = candidates[0]
    replaced = REFERENCE_RE.sub(f"{topic} ", original, count=1)
    # Avoid repeated topic phrasing such as "TIME_WAIT TIME_WAIT".
    replaced = re.sub(rf"(?:{re.escape(topic)}\s*){{2,}}", f"{topic} ", replaced).strip()
    if LOW_INFORMATION_RE.match(replaced) or len(replaced.replace(topic, "").strip(" ，。！？、？!?")) < 2:
        return QueryResolution(original, original, None, 0.3, "unresolved", references, "resolved_query_is_low_information")
    return QueryResolution(original, replaced, topic, 0.9, source, [], "unique_scoped_course_focus")


__all__ = ["QueryResolution", "resolve_course_query"]
