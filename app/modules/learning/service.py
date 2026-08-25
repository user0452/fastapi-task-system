"""Small compatibility helper for a pre-existing local allocation test.

The old Quiz/Study Plan service was retired from the product runtime.  This
function is intentionally isolated and is not imported by the Adaptive Tutor
API; new learning decisions belong to ``app.modules.adaptive.policy``.
"""

from __future__ import annotations

from typing import Any, TypedDict


class _StudyPointEntry(TypedDict):
    index: int
    point: dict[str, Any]
    priority: int
    mastery: float
    sort_order: int
    id: int


def _study_point_priority(point: dict[str, Any]) -> int:
    mastery = max(0.0, min(100.0, float(point.get("mastery") or 0)))
    streak = max(0, int(point.get("low_score_streak") or 0))
    return max(1, int(max(0.0, 100.0 - mastery) + min(streak, 5) * 10))


def allocate_study_points(points: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    """Preserve deterministic behavior for a user-local legacy unit test only."""
    if days < 0:
        raise ValueError("days must be non-negative")
    if days == 0 or not points:
        return []

    entries: list[_StudyPointEntry] = [
        {
            "index": index,
            "point": point,
            "priority": _study_point_priority(point),
            "mastery": float(point.get("mastery") or 0),
            "sort_order": int(point.get("sort_order") or 0),
            "id": int(point.get("id") or 0),
        }
        for index, point in enumerate(points)
    ]

    def stable_order(entry: _StudyPointEntry) -> tuple[int, float, int, int, int]:
        return (
            -entry["priority"],
            entry["mastery"],
            entry["sort_order"],
            entry["id"],
            entry["index"],
        )

    if days < len(entries):
        return [dict(entry["point"]) for entry in sorted(entries, key=stable_order)[:days]]

    counts = [1] * len(entries)
    remaining_days = days - len(entries)
    total_priority = sum(entry["priority"] for entry in entries)
    remainders: list[tuple[int, int]] = []
    for index, entry in enumerate(entries):
        quotient, remainder = divmod(remaining_days * entry["priority"], total_priority)
        counts[index] += quotient
        remainders.append((remainder, index))

    extra_days = remaining_days - sum(count - 1 for count in counts)
    for _, index in sorted(
        remainders,
        key=lambda item: (-item[0], stable_order(entries[item[1]])),
    )[:extra_days]:
        counts[index] += 1

    scheduled: list[dict[str, Any]] = []
    previous_index: int | None = None
    for _ in range(days):
        available = [index for index, count in enumerate(counts) if count > 0]
        without_previous = [index for index in available if index != previous_index]
        candidates = without_previous or available
        selected_index = min(
            candidates,
            key=lambda index: (-counts[index], stable_order(entries[index])),
        )
        counts[selected_index] -= 1
        scheduled.append(dict(entries[selected_index]["point"]))
        previous_index = selected_index
    return scheduled


__all__ = ["allocate_study_points"]
