from datetime import date, datetime, timedelta

from app.modules.learning.today_planner import plan_today_rows


def _row(
    course_id: int,
    *,
    session_status: str | None = "planned",
    minutes: int = 30,
    exam_days: int | None = None,
    weak_points: int = 0,
    average_mastery: float = 80,
    current: bool = False,
) -> dict:
    today = date(2026, 7, 20)
    return {
        "course": {
            "id": course_id,
            "name": f"课程 {course_id}",
            "daily_minutes": minutes,
            "is_current": current,
            "status": "active",
            "exam_at": (
                datetime.combine(today + timedelta(days=exam_days), datetime.min.time())
                if exam_days is not None
                else None
            ),
            "learning_priority": {
                "total_points": max(weak_points, 1),
                "weak_points": weak_points,
                "average_mastery": average_mastery,
            },
            "roadmap_summary": {"overall_progress": 35},
        },
        "session": (
            {"id": course_id * 10, "status": session_status, "estimated_minutes": minutes, "items": []}
            if session_status is not None
            else None
        ),
    }


def test_plan_today_prioritises_urgent_weak_course_and_respects_budget():
    today = date(2026, 7, 20)
    urgent = _row(1, exam_days=2, weak_points=3, average_mastery=42)
    steady = _row(2, exam_days=45, weak_points=0, average_mastery=88, current=True)
    completed = _row(3, session_status="completed", exam_days=1, weak_points=4)

    result = plan_today_rows(
        [steady, completed, urgent],
        today=today,
        available_minutes=40,
    )

    assert [item["course"]["id"] for item in result["items"]] == [1, 2, 3]
    assert [item["recommendation"]["recommended_minutes"] for item in result["items"]] == [30, 10, 0]
    assert result["budget"] == {
        "available_minutes": 40,
        "requested_minutes": 60,
        "recommended_minutes": 40,
        "unallocated_minutes": 0,
        "limited": True,
    }
    assert any("距离考试" in reason for reason in result["items"][0]["recommendation"]["reasons"])
    assert any("薄弱知识点" in reason for reason in result["items"][0]["recommendation"]["reasons"])


def test_plan_today_keeps_unactionable_course_visible_without_spending_budget():
    result = plan_today_rows(
        [_row(1, session_status=None), _row(2, minutes=25)],
        today=date(2026, 7, 20),
        available_minutes=60,
    )

    assert [item["course"]["id"] for item in result["items"]] == [2, 1]
    assert result["items"][0]["recommendation"]["recommended_minutes"] == 25
    assert result["items"][1]["recommendation"]["recommended_minutes"] == 0
    assert result["budget"]["unallocated_minutes"] == 35


def test_plan_today_clamps_extreme_budget_values():
    low = plan_today_rows([_row(1)], today=date(2026, 7, 20), available_minutes=1)
    high = plan_today_rows([_row(1)], today=date(2026, 7, 20), available_minutes=10_000)

    assert low["budget"]["available_minutes"] == 10
    assert high["budget"]["available_minutes"] == 480


def test_plan_today_interprets_persisted_exam_time_in_the_user_timezone():
    row = _row(1)
    # 2026-07-21 06:30 UTC is still 2026-07-20 in Los Angeles. Treating the
    # persisted UTC-naive value as a local date would incorrectly report one day remaining.
    row["course"]["exam_at"] = datetime(2026, 7, 21, 6, 30)

    result = plan_today_rows(
        [row],
        today=date(2026, 7, 20),
        available_minutes=30,
        timezone_name="America/Los_Angeles",
    )

    recommendation = result["items"][0]["recommendation"]
    assert recommendation["priority_score"] == 80
    assert "考试日期已到，需要立即复习" in recommendation["reasons"]
