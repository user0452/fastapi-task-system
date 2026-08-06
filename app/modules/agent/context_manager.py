"""Token-budgeted, round-aware course-agent context assembly."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

import numpy as np

from app.core.config import get_settings
from app.integrations.embedding.chunking import estimate_tokens
from app.integrations.embedding.service import deserialize_embedding, embed_texts

MAX_MEMORIES = 5
MAX_MASTERY_POINTS = 8
SEMANTIC_MEMORY_WEIGHT = 0.8
LEXICAL_MEMORY_WEIGHT = 0.2
# Compatibility export for callers/tests.  Context selection is now round-based.
RECENT_TURNS = 10


def _compact(value: Any, token_limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    tokens = estimate_tokens(text)
    if tokens <= token_limit:
        return text
    length = max(80, int(len(text) * token_limit / max(1, tokens)) - 12)
    return text[:length] + "…"


def _truncate_content(value: Any, token_limit: int) -> tuple[str, bool]:
    text = str(value or "").strip()
    if estimate_tokens(text) <= token_limit:
        return text, False
    length = max(80, int(len(text) * token_limit / max(1, estimate_tokens(text))) - 12)
    return text[:length] + "…", True


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
    min_score: float | None = None,
    embedding_provider: Callable = embed_texts,
) -> list[dict]:
    if not memories or not str(query or "").strip():
        return []
    threshold = get_settings().memory_relevance_threshold if min_score is None else max(0.0, min(1.0, float(min_score)))
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
        lexical = len(query_terms & _lexical_terms(text)) / max(1, len(query_terms))
        semantic, has_semantic_score = 0.0, False
        if query_vector is not None and memory.get("embedding_json"):
            try:
                vector = deserialize_embedding(memory["embedding_json"])
                if vector.shape == query_vector.shape:
                    semantic = max(0.0, min(1.0, float(np.dot(query_vector, vector))))
                    has_semantic_score = True
            except (TypeError, ValueError):
                pass
        score = semantic * SEMANTIC_MEMORY_WEIGHT + lexical * LEXICAL_MEMORY_WEIGHT if has_semantic_score else lexical
        if score >= threshold:
            ranked.append((score, memory.get("updated_at"), memory))
    ranked.sort(key=lambda item: (item[0], item[1] or ""), reverse=True)
    return [item[2] for item in ranked[: max(1, min(int(limit), MAX_MEMORIES))]]


def _complete_rounds(messages: list[dict]) -> tuple[list[list[dict]], list[dict]]:
    """Pair a user turn with its next assistant response; never emit half a round."""
    rounds: list[list[dict]] = []
    pending: list[dict] = []
    user_message: dict | None = None
    for message in sorted(messages, key=lambda item: int(item.get("id") or 0)):
        role = message.get("role")
        if role == "user":
            if user_message is not None:
                pending.append(user_message)
            user_message = message
        elif role == "assistant" and user_message is not None:
            rounds.append([user_message, message])
            user_message = None
        elif role == "assistant":
            pending.append(message)
    if user_message is not None:
        pending.append(user_message)
    return rounds, pending


def _round_messages(rounds: list[list[dict]], per_message_tokens: int) -> tuple[list[dict], bool]:
    items: list[dict] = []
    truncated = False
    for round_items in rounds:
        for item in round_items:
            content, item_truncated = _truncate_content(item.get("content"), per_message_tokens)
            truncated = truncated or item_truncated
            items.append({"id": item.get("id"), "role": item.get("role"), "content": content})
    return items, truncated


def _message_cost(items: list[dict]) -> int:
    return estimate_tokens(json.dumps(items, ensure_ascii=False, separators=(",", ":")))


def build_agent_context(
    *,
    course: dict | None,
    profile: dict | None,
    mastery: list[dict],
    memories: list[dict],
    messages: list[dict],
    conversation_summary: str | None = None,
    summary_blocks: list[dict] | None = None,
    covered_until_message_id: int | None = None,
    server_time: str | None = None,
) -> tuple[str, dict]:
    """Assemble summaries, pending originals, and 3--5 complete recent rounds.

    Older originals are never deleted.  When their async summary is not ready,
    they remain pending; only an explicit budget emergency uses deterministic
    snippets, which is reported as degraded.
    """
    settings = get_settings()
    budget = settings.agent_context_budget_tokens
    min_rounds = settings.agent_min_recent_rounds
    target_rounds = max(min_rounds, settings.agent_target_recent_rounds)
    weak_points = sorted(mastery, key=lambda item: float(item.get("mastery", item.get("mastery_score", 0)) or 0))[:MAX_MASTERY_POINTS]
    selected_memories = memories[:MAX_MEMORIES]
    block_items: list[dict] = []
    summary_tokens = 0
    for block in summary_blocks or []:
        if not block.get("summary_text"):
            continue
        summary, _ = _truncate_content(block.get("summary_text"), 900)
        item = {
            "id": block.get("id"), "start_message_id": block.get("start_message_id"),
            "end_message_id": block.get("end_message_id"), "level": block.get("level", 0),
            "summary": summary,
        }
        item_tokens = estimate_tokens(json.dumps(item, ensure_ascii=False))
        if block_items and summary_tokens + item_tokens > settings.conversation_summary_max_tokens:
            break
        block_items.append(item)
        summary_tokens += item_tokens
    compact_memories = []
    for memory in selected_memories:
        content, _ = _truncate_content(
            json.dumps(memory.get("content") or {}, ensure_ascii=False, default=str), 260
        )
        compact_memories.append({"type": memory.get("memory_type"), "content": content})
    fixed_layers = {
        "course": _compact(course or {}, 500),
        "profile": _compact(profile or {}, 500),
        "weak_points": [{"name": point.get("name"), "mastery": point.get("mastery", point.get("mastery_score"))} for point in weak_points],
        "memories": compact_memories,
        "summary_blocks": block_items,
        "legacy_summary": (conversation_summary or "")[:1200] if not block_items else "",
        "summary_instruction": "摘要可能与较新的原文重叠；发生冲突时，以 recent_rounds 和 pending_original_messages 为准。",
        "server_time": server_time,
    }
    # Keep fixed business state bounded so it cannot evict protected original rounds.
    complete_rounds, unmatched = _complete_rounds(messages)
    protected = complete_rounds[-min_rounds:] if min_rounds else []
    protected_count = len(protected)
    degraded_reasons: list[str] = []
    if protected_count < min_rounds and complete_rounds:
        degraded_reasons.append("fewer_than_minimum_complete_rounds_available")

    fixed_cost = estimate_tokens(json.dumps(fixed_layers, ensure_ascii=False, default=str, separators=(",", ":")))
    protected_messages = max(1, sum(len(round_items) for round_items in protected) + len(unmatched))
    protected_allowance = max(900, budget - fixed_cost - 400)
    per_message_tokens = max(120, protected_allowance // protected_messages)
    recent_items, message_truncated = _round_messages(protected, per_message_tokens)
    pending_current, pending_truncated = _round_messages([unmatched] if unmatched else [], per_message_tokens)
    if message_truncated or pending_truncated:
        degraded_reasons.append("long_message_truncated_to_preserve_complete_recent_rounds")

    selected_rounds = list(protected)
    # Add older complete rounds until target 5, without breaking pairs.
    for candidate in reversed(complete_rounds[:-len(protected) or None]):
        if len(selected_rounds) >= target_rounds:
            break
        trial = [candidate, *selected_rounds]
        trial_items, _ = _round_messages(trial, per_message_tokens)
        if fixed_cost + _message_cost(trial_items) + _message_cost(pending_current) <= budget:
            selected_rounds = trial
            recent_items = trial_items
        else:
            break

    covered_until = int(covered_until_message_id or 0)
    selected_ids = {int(item.get("id") or 0) for item in recent_items}
    pending_rounds = [
        round_items for round_items in complete_rounds
        if round_items[-1].get("id", 0) > covered_until and int(round_items[-1].get("id") or 0) not in selected_ids
    ]
    pending_items, pending_old_truncated = _round_messages(pending_rounds, per_message_tokens)
    remaining = budget - fixed_cost - _message_cost(recent_items) - _message_cost(pending_current)
    if pending_items and _message_cost(pending_items) <= remaining:
        pending_original = pending_items
    elif pending_items:
        # Deterministic emergency fallback: retain identifiers and representative text.
        pending_original = [
            {"id": item["id"], "role": item["role"], "content": str(item["content"])[:240] + ("…" if len(str(item["content"])) > 240 else "")}
            for item in pending_items
        ]
        degraded_reasons.append("pending_originals_deterministically_compacted_under_budget")
    else:
        pending_original = []
    if pending_old_truncated:
        degraded_reasons.append("pending_long_message_truncated")

    layers = {
        **fixed_layers,
        "pending_original_messages": pending_original + pending_current,
        "recent_rounds": recent_items,
    }
    prompt = json.dumps(layers, ensure_ascii=False, default=str, separators=(",", ":"))
    used_tokens = estimate_tokens(prompt)
    return prompt, {
        "budget_tokens": budget,
        "used_tokens": used_tokens,
        "recent_round_count": len(selected_rounds),
        "recent_message_count": len(recent_items),
        "recent_turns": len(recent_items),  # compatibility with existing trace consumers
        "summary_block_count": len(block_items),
        "summary_tokens": summary_tokens,
        "pending_message_count": len(pending_original) + len(pending_current),
        "covered_until_message_id": covered_until_message_id,
        "memory_count": len(selected_memories),
        "weak_point_count": len(weak_points),
        "truncated": bool(degraded_reasons) or used_tokens > budget,
        "degraded": bool(degraded_reasons) or used_tokens > budget,
        "degradation_reason": ";".join(degraded_reasons) if degraded_reasons else None,
    }


def build_rolling_summary(previous: str | None, messages: list[dict]) -> str:
    """Legacy deterministic fallback retained for old deployments only."""
    additions = "\n".join(f"#{item.get('id')} {item.get('role', 'user')}: {str(item.get('content') or '').strip()[:260]}" for item in messages if item.get("content"))
    combined = "\n".join(part for part in [(previous or "").strip(), additions] if part)
    return combined[-3500:]


__all__ = ["RECENT_TURNS", "build_agent_context", "build_rolling_summary", "select_relevant_memories"]
