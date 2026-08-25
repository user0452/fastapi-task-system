"""Deterministic question-bank ranking shared by runtime and benchmarks."""

from __future__ import annotations

from typing import Any

DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}


def _shingles(value: str) -> set[str]:
    compact = "".join(str(value or "").casefold().split())
    if len(compact) <= 2:
        return {compact} if compact else set()
    return {compact[index : index + 2] for index in range(len(compact) - 1)}


def _similarity(left: str, right: str) -> float:
    a = _shingles(left)
    b = _shingles(right)
    return len(a & b) / max(len(a | b), 1)


def select_best_question(
    candidates: list[dict[str, Any]],
    *,
    desired_difficulty: str,
    coverage_types: list[str] | None = None,
    action_type: str | None = None,
    recent_question_ids: set[int] | None = None,
    recent_question_contents: list[str] | None = None,
) -> dict[str, Any] | None:
    """Pick a real question using objective alignment before generation.

    The function is deliberately side-effect free so the same ranking can be
    evaluated with deterministic fixtures without a database or an LLM.
    """
    if coverage_types:
        preferred = set(coverage_types)
        preferred_candidates = [
            item for item in candidates if item.get("coverage_type") in preferred
        ]
        if preferred_candidates:
            candidates = preferred_candidates
    if not candidates:
        return None

    recent_question_ids = recent_question_ids or set()
    recent_question_contents = recent_question_contents or []
    unseen_candidates = [
        item for item in candidates if int(item.get("id") or 0) not in recent_question_ids
    ]
    if unseen_candidates:
        candidates = unseen_candidates

    desired_rank = DIFFICULTY_RANK.get(desired_difficulty, 1)

    def rank(item: dict[str, Any]) -> tuple[float, float, float, float, float, int]:
        distance = abs(DIFFICULTY_RANK.get(str(item.get("difficulty")), 1) - desired_rank)
        attempts = int(item.get("attempt_count") or 0)
        correct = int(item.get("correct_count") or 0)
        repeated_penalty = min(0.45, attempts * 0.08)
        similarity_penalty = max(
            (_similarity(str(item.get("content") or ""), previous) for previous in recent_question_contents),
            default=0.0,
        ) * 0.40
        source_bonus = {
            "user_upload": 0.16,
            "textbook": 0.14,
            "public_source": 0.08,
            "search": 0.06,
            "generated": 0.0,
        }.get(str(item.get("source_type")), 0.0)
        unseen_bonus = 0.20 if attempts == 0 else 0.0
        action_bonus = 0.0
        if action_type == "misconception_repair" and str(item.get("coverage_type")) in {"scenario", "transfer"}:
            action_bonus = 0.28
        elif action_type == "verify_mastery" and str(item.get("coverage_type")) in {"scenario", "transfer"}:
            action_bonus = 0.16
        elif action_type == "review" and attempts > 0:
            action_bonus = 0.24
        return (
            float(item.get("relevance") or 0) * 0.45
            + float(item.get("confidence") or 0) * 0.18
            + float(item.get("quality_score") or 0) * 0.17
            + source_bonus
            + unseen_bonus
            + action_bonus
            - distance * 0.18
            - repeated_penalty
            - similarity_penalty,
            -similarity_penalty,
            -float(correct),
            -float(item.get("quality_score") or 0),
            -float(item.get("relevance") or 0),
            -int(item["id"]),
        )

    return max(candidates, key=rank)


__all__ = ["select_best_question"]
