"""Deterministic cross-course prioritisation for the global Today view.

The planner never mutates course plans.  It explains how a user's finite daily
budget should be distributed across already scheduled learning units, so the
UI can offer a useful order without hiding the underlying course data.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.core.time_utils import DEFAULT_USER_TIMEZONE, utc_naive_to_local

DEFAULT_AVAILABLE_MINUTES = 90
MIN_FOCUS_BLOCK_MINUTES = 10
MAX_AVAILABLE_MINUTES = 480


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _exam_date(value: Any, timezone_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return utc_naive_to_local(value, timezone_name).date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    if "T" not in raw and " " not in raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return utc_naive_to_local(parsed, timezone_name).date()


def _priority(row: dict, today: date, timezone_name: str) -> tuple[float, list[str]]:
    course = row["course"]
    session = row.get("session")
    learning = course.get("learning_priority") or {}
    score = 0.0
    reasons: list[str] = []

    status = str((session or {}).get("status") or "")
    if status == "in_progress":
        score += 42
        reasons.append("今日单元已经开始，优先完成以保持连续性")
    elif status == "planned":
        score += 30
        reasons.append("今天已有可执行学习单元")
    elif status in {"completed", "evaluated"}:
        score -= 100
        reasons.append("今日单元已经完成")
    else:
        course_status = str(course.get("status") or "")
        if course_status in {"draft", "preparing", "diagnostic_pending"}:
            score += 12
            reasons.append("先完成课程准备或诊断，才能生成后续计划")
        else:
            reasons.append("暂未生成今日学习单元")

    exam = _exam_date(course.get("exam_at"), timezone_name)
    if exam is not None:
        remaining_days = (exam - today).days
        if remaining_days <= 0:
            score += 50
            reasons.append("考试日期已到，需要立即复习")
        elif remaining_days <= 3:
            score += 42
            reasons.append(f"距离考试仅剩 {remaining_days} 天")
        elif remaining_days <= 7:
            score += 32
            reasons.append(f"距离考试还有 {remaining_days} 天")
        elif remaining_days <= 30:
            score += 16
            reasons.append(f"考试进入 {remaining_days} 天准备窗口")

    total_points = int(_number(learning.get("total_points")))
    weak_points = int(_number(learning.get("weak_points")))
    average_mastery = _number(learning.get("average_mastery"), 0.0)
    if total_points:
        weakness_score = min(24.0, weak_points * 4.0)
        if average_mastery < 60:
            weakness_score += min(16.0, (60.0 - average_mastery) / 2.5)
        score += weakness_score
        if weak_points:
            reasons.append(f"有 {weak_points} 个薄弱知识点需要巩固")
        elif average_mastery >= 80:
            reasons.append("当前掌握度较稳，可按计划推进")

    roadmap = course.get("roadmap_summary") or {}
    progress = max(0.0, min(100.0, _number(roadmap.get("overall_progress"))))
    if progress < 25:
        score += 8
        reasons.append("长期路线仍处于起步阶段")
    elif progress >= 90:
        score -= 4

    if bool(course.get("is_current")):
        score += 4

    return round(score, 2), reasons[:3]


def _requested_minutes(row: dict) -> int:
    session = row.get("session") or {}
    course = row["course"]
    value = session.get("estimated_minutes") or course.get("daily_minutes") or 30
    return max(MIN_FOCUS_BLOCK_MINUTES, min(int(_number(value, 30)), MAX_AVAILABLE_MINUTES))


def plan_today_rows(
    rows: list[dict],
    *,
    today: date,
    available_minutes: int = DEFAULT_AVAILABLE_MINUTES,
    timezone_name: str = DEFAULT_USER_TIMEZONE,
) -> dict:
    """Rank rows and distribute a bounded budget across actionable sessions."""

    budget = max(MIN_FOCUS_BLOCK_MINUTES, min(int(available_minutes), MAX_AVAILABLE_MINUTES))
    ranked: list[dict] = []
    for original_index, row in enumerate(rows):
        score, reasons = _priority(row, today, timezone_name)
        requested = _requested_minutes(row)
        status = str((row.get("session") or {}).get("status") or "")
        actionable = bool(row.get("session")) and status not in {"completed", "evaluated"}
        ranked.append(
            {
                **row,
                "_original_index": original_index,
                "_actionable": actionable,
                "_score": score,
                "_reasons": reasons,
                "_requested": requested,
            }
        )

    ranked.sort(
        key=lambda item: (
            not item["_actionable"],
            -item["_score"],
            item["_original_index"],
            int(item["course"]["id"]),
        )
    )

    remaining = budget
    recommended_total = 0
    requested_total = sum(item["_requested"] for item in ranked if item["_actionable"])
    result: list[dict] = []
    for rank, item in enumerate(ranked, start=1):
        recommended = 0
        if item["_actionable"] and remaining >= MIN_FOCUS_BLOCK_MINUTES:
            recommended = min(item["_requested"], remaining)
            if recommended < MIN_FOCUS_BLOCK_MINUTES:
                recommended = 0
            remaining -= recommended
            recommended_total += recommended
        reasons = list(item["_reasons"])
        if item["_actionable"] and recommended == 0:
            reasons.append("今日时间预算已分配完，可顺延到下一学习时段")
        elif item["_actionable"] and recommended < item["_requested"]:
            reasons.append("根据今日可用时间缩短本次学习块")
        result.append(
            {
                key: value
                for key, value in item.items()
                if not key.startswith("_")
            }
            | {
                "recommendation": {
                    "rank": rank,
                    "priority_score": item["_score"],
                    "requested_minutes": item["_requested"],
                    "recommended_minutes": recommended,
                    "budget_limited": recommended < item["_requested"] if item["_actionable"] else False,
                    "reasons": reasons[:4],
                }
            }
        )

    return {
        "items": result,
        "budget": {
            "available_minutes": budget,
            "requested_minutes": requested_total,
            "recommended_minutes": recommended_total,
            "unallocated_minutes": remaining,
            "limited": requested_total > budget,
        },
    }


__all__ = [
    "DEFAULT_AVAILABLE_MINUTES",
    "MAX_AVAILABLE_MINUTES",
    "MIN_FOCUS_BLOCK_MINUTES",
    "plan_today_rows",
]
