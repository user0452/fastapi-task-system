"""Token-budgeted rolling context and semantic course memory selection."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

import numpy as np

from app.integrations.embedding.chunking import estimate_tokens
from app.integrations.embedding.service import deserialize_embedding, embed_texts

MAX_CONTEXT_TOKENS = 7_000
RECENT_TURNS = 8
MAX_MEMORIES = 5
MAX_MASTERY_POINTS = 8


def _compact(value: Any, token_limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    tokens = estimate_tokens(text)
    if tokens <= token_limit:
        return text
    length = max(80, int(len(text) * token_limit / max(1, tokens)) - 12)
    return text[:length] + "…"


def _lexical_terms(value: str) -> set[str]:
    lowered = (value or "").casefold()
    terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{1,4}", lowered))
    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        terms.update(run[index : index + 2] for index in range(max(0, len(run) - 1)))
    return terms


def select_relevant_memories(
    query: str,
    memories: list[dict],
    *,
    limit: int = MAX_MEMORIES,
    embedding_provider: Callable = embed_texts,
) -> list[dict]:
    """Rank persistent memories semantically, with lexical fallback."""
    if not memories:
        return []
    query_vector = None
    if any(memory.get("embedding_json") for memory in memories):
        try:
            matrix = np.asarray(embedding_provider([query]), dtype="float32")
            if matrix.ndim == 2 and matrix.shape[0] == 1:
                query_vector = matrix[0]
        except Exception:
            query_vector = None
    query_terms = _lexical_terms(query)
    ranked = []
    for memory in memories:
        text = json.dumps(memory.get("content") or {}, ensure_ascii=False, default=str)
        memory_terms = _lexical_terms(text)
        lexical = len(query_terms & memory_terms) / max(1, len(query_terms))
        semantic = 0.0
        if query_vector is not None and memory.get("embedding_json"):
            try:
                vector = deserialize_embedding(memory["embedding_json"])
                if vector.shape == query_vector.shape:
                    semantic = max(0.0, min(1.0, (float(np.dot(query_vector, vector)) + 1.0) / 2.0))
            except (TypeError, ValueError):
                semantic = 0.0
        score = semantic * 0.8 + lexical * 0.2 if semantic else lexical
        ranked.append((score, memory.get("updated_at"), memory))
    ranked.sort(key=lambda item: (item[0], item[1] or ""), reverse=True)
    return [item[2] for item in ranked[: max(1, min(int(limit), MAX_MEMORIES))]]


def build_agent_context(
    *,
    course: dict | None,
    profile: dict | None,
    mastery: list[dict],
    memories: list[dict],
    messages: list[dict],
    conversation_summary: str | None,
    server_time: str | None = None,
) -> tuple[str, dict]:
    """Assemble layers under an explicit model-token budget."""
    weak_points = sorted(
        mastery,
        key=lambda item: float(item.get("mastery", item.get("mastery_score", 0)) or 0),
    )[:MAX_MASTERY_POINTS]
    selected_memories = memories[:MAX_MEMORIES]
    fixed_layers = {
        "course": _compact(course or {}, 650),
        "profile": _compact(profile or {}, 750),
        "weak_points": [
            {
                "name": point.get("name"),
                "mastery": point.get("mastery", point.get("mastery_score")),
            }
            for point in weak_points
        ],
        "memories": [
            {"type": memory.get("memory_type"), "content": memory.get("content")}
            for memory in selected_memories
        ],
        "conversation_summary": (conversation_summary or "")[:3500],
        "server_time": server_time,
    }
    fixed_text = _compact(fixed_layers, 4_200)
    remaining = max(800, MAX_CONTEXT_TOKENS - estimate_tokens(fixed_text))

    recent: list[dict] = []
    used_recent_tokens = 0
    for item in reversed(messages[-RECENT_TURNS:]):
        candidate = {
            "id": item.get("id"),
            "role": item.get("role"),
            "content": str(item.get("content") or "")[:2400],
        }
        cost = estimate_tokens(json.dumps(candidate, ensure_ascii=False))
        if recent and used_recent_tokens + cost > remaining:
            break
        if cost > remaining:
            candidate["content"] = _compact(candidate["content"], remaining)
            cost = estimate_tokens(json.dumps(candidate, ensure_ascii=False))
        recent.append(candidate)
        used_recent_tokens += cost
    recent.reverse()
    layers = {**fixed_layers, "recent_turns": recent}
    prompt = json.dumps(layers, ensure_ascii=False, default=str, separators=(",", ":"))
    used_tokens = estimate_tokens(prompt)
    report = {
        "budget_tokens": MAX_CONTEXT_TOKENS,
        "used_tokens": used_tokens,
        "recent_turns": len(recent),
        "memory_count": len(selected_memories),
        "weak_point_count": len(weak_points),
        "summary_tokens": estimate_tokens(
            json.dumps(fixed_layers["conversation_summary"], ensure_ascii=False, default=str)
        ),
        "truncated": len(recent) < min(len(messages), RECENT_TURNS) or used_tokens >= MAX_CONTEXT_TOKENS,
    }
    return prompt, report


def build_rolling_summary(previous: str | None, messages: list[dict]) -> str:
    """Append only newly summarized messages; callers advance a DB checkpoint."""
    additions = "；".join(
        f"#{item.get('id')} {item.get('role', 'user')}: {str(item.get('content') or '').strip()[:260]}"
        for item in messages
        if item.get("content")
    )
    combined = "；".join(part for part in [(previous or "").strip(), additions] if part)
    if len(combined) <= 3500:
        return combined
    return "较早对话已压缩；" + combined[-3460:]


__all__ = [
    "RECENT_TURNS",
    "build_agent_context",
    "build_rolling_summary",
    "select_relevant_memories",
]
