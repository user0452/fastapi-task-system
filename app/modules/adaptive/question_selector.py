"""Deterministic question-bank ranking shared by runtime and benchmarks."""

from __future__ import annotations

from typing import Any

DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}


def select_best_question(
    candidates: list[dict[str, Any]],
    *,
    desired_difficulty: str,
    coverage_types: list[str] | None = None,
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

    desired_rank = DIFFICULTY_RANK.get(desired_difficulty, 1)

    def rank(item: dict[str, Any]) -> tuple[float, float, float, float, int]:
        distance = abs(DIFFICULTY_RANK.get(str(item.get("difficulty")), 1) - desired_rank)
        attempts = int(item.get("attempt_count") or 0)
        correct = int(item.get("correct_count") or 0)
        repeated_penalty = min(0.45, attempts * 0.08)
        source_bonus = {
            "user_upload": 0.16,
            "textbook": 0.14,
            "public_source": 0.08,
            "search": 0.06,
            "generated": 0.0,
        }.get(str(item.get("source_type")), 0.0)
        unseen_bonus = 0.20 if attempts == 0 else 0.0
        return (
            float(item.get("relevance") or 0) * 0.45
            + float(item.get("confidence") or 0) * 0.18
            + float(item.get("quality_score") or 0) * 0.17
            + source_bonus
            + unseen_bonus
            - distance * 0.10
            - repeated_penalty,
            -float(correct),
            -float(item.get("quality_score") or 0),
            -float(item.get("relevance") or 0),
            -int(item["id"]),
        )

    return max(candidates, key=rank)


__all__ = ["select_best_question"]
