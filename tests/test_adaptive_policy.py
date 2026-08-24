from datetime import datetime, timezone

from app.modules.adaptive.policy import (
    choose_next_action,
    select_action,
    select_objective,
    update_student_state,
)


def _objective(objective_id: int, title: str, importance: float = 0.5) -> dict:
    return {
        "id": objective_id,
        "title": title,
        "description": f"能够完成 {title} 的可验证任务。",
        "required_ability": f"在场景中判断 {title}。",
        "importance": importance,
        "status": "active",
    }


def test_policy_repairs_unmet_prerequisite_before_dependent_objective():
    objectives = [_objective(1, "解释基础协议", 0.7), _objective(2, "判断高级场景", 0.95)]
    states = {
        1: {"mastery": 0.25, "confidence": 0.45, "attempt_count": 2},
        2: {"mastery": 0.0, "confidence": 0.0, "attempt_count": 0},
    }
    relations = [
        {
            "source_objective_id": 1,
            "target_objective_id": 2,
            "relation_type": "prerequisite",
        }
    ]

    decision = choose_next_action(objectives, states, relations)

    assert decision is not None
    assert decision["objective_id"] == 1
    assert decision["action_type"] == "explain"


def test_policy_penalizes_unnecessary_practice_for_validated_mastery():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    objectives = [_objective(1, "已验证目标", 0.5), _objective(2, "仍需练习目标", 0.5)]
    states = {
        1: {
            "mastery": 0.92,
            "confidence": 0.88,
            "attempt_count": 8,
            "last_practiced_at": now.isoformat(),
        },
        2: {"mastery": 0.3, "confidence": 0.3, "attempt_count": 2},
    }

    decision = choose_next_action(objectives, states, [])

    assert decision is not None
    assert decision["objective_id"] == 2


def test_policy_stops_when_every_objective_is_recently_validated():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    objectives = [_objective(1, "已验证目标 A"), _objective(2, "已验证目标 B")]
    states = {
        objective_id: {
            "mastery": 0.9,
            "confidence": 0.86,
            "attempt_count": 5,
            "last_practiced_at": now.isoformat(),
        }
        for objective_id in (1, 2)
    }

    assert select_objective(objectives, states, [], now=now) is None


def test_policy_reintroduces_mastered_objective_only_when_review_is_due():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    decision = choose_next_action(
        [_objective(1, "需要间隔复习")],
        {
            1: {
                "mastery": 0.9,
                "confidence": 0.86,
                "attempt_count": 5,
                "last_practiced_at": "2026-08-10T00:00:00+00:00",
            }
        },
        [],
        now=now,
    )

    assert decision is not None
    assert decision["action_type"] == "review"


def test_high_mastery_low_confidence_requires_verification():
    decision = select_action(
        _objective(1, "高掌握低置信目标"),
        {"mastery": 0.86, "confidence": 0.22, "attempt_count": 1},
    )

    assert decision["action_type"] == "verify_mastery"
    assert "证据" in decision["reason"]


def test_active_misconception_wins_action_selection():
    decision = select_action(
        _objective(1, "区分两个相似概念"),
        {"mastery": 0.62, "confidence": 0.62},
        [{"code": "confuse_a_b", "description": "混淆 A 与 B"}],
    )

    assert decision["action_type"] == "misconception_repair"
    assert decision["misconception"]["code"] == "confuse_a_b"


def test_state_update_is_bounded_and_confidence_is_separate():
    first = update_student_state(
        {"mastery": 0.1, "confidence": 0.0, "attempt_count": 0},
        score=1.0,
        difficulty="hard",
    )
    second = update_student_state(first, score=1.0, difficulty="hard")

    assert first["mastery"] <= 0.32
    assert second["mastery"] > first["mastery"]
    assert second["confidence"] > first["confidence"]
    assert first["mastery"] != first["confidence"]
    assert "BKT-inspired" in first["update_reason"]
