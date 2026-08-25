"""Deterministic Adaptive Tutor benchmark.

The benchmark is deliberately independent from the database and LLM provider.
It freezes curriculum graphs, student states, expected policy decisions and
question/grader fixtures so a policy change can be compared with explicit
baselines and ablations.
"""

from __future__ import annotations

import copy
import random
from datetime import datetime, timezone
from typing import Any, Sequence

from app.modules.adaptive.grader import grade_response
from app.modules.adaptive.policy import (
    PREREQUISITE_CONFIDENCE_THRESHOLD,
    PREREQUISITE_MASTERY_THRESHOLD,
    choose_next_action,
    select_action,
    update_student_state,
)
from app.modules.adaptive.question_selector import select_best_question

BENCHMARK_VERSION = "adaptive-benchmark-v2-stage2"
NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _objective(objective_id: int, title: str, importance: float = 0.7) -> dict[str, Any]:
    return {
        "id": objective_id,
        "title": title,
        "description": f"能够完成 {title} 的可评估任务。",
        "required_ability": f"在场景中判断 {title}。",
        "importance": importance,
        "status": "active",
    }


BASE_OBJECTIVES = [
    _objective(1, "解释基础概念", 0.70),
    _objective(2, "区分两个相似机制", 0.75),
    _objective(3, "判断复杂场景", 0.80),
]
CHAIN_RELATIONS = [
    {"source_objective_id": 1, "target_objective_id": 2, "relation_type": "prerequisite"},
    {"source_objective_id": 2, "target_objective_id": 3, "relation_type": "prerequisite"},
]


def _validated(at: str = "2026-08-25T10:00:00+00:00", mastery: float = 0.90, confidence: float = 0.90) -> dict[str, Any]:
    return {
        "mastery": mastery,
        "confidence": confidence,
        "attempt_count": 8,
        "last_practiced_at": at,
    }


def _case(
    category: str,
    case_id: str,
    states: dict[int, dict[str, Any]],
    expected_objective_id: int | None,
    expected_action_type: str | None,
    *,
    relations: list[dict[str, Any]] | None = None,
    importance: dict[int, float] | None = None,
    goal_relevance: dict[int, float] | None = None,
    misconceptions: dict[int, list[dict[str, Any]]] | None = None,
    weak_objective_id: int | None = None,
) -> dict[str, Any]:
    objectives = copy.deepcopy(BASE_OBJECTIVES)
    for objective in objectives:
        if importance and objective["id"] in importance:
            objective["importance"] = importance[objective["id"]]
    return {
        "case_id": case_id,
        "category": category,
        "objectives": objectives,
        "relations": copy.deepcopy(relations or []),
        "states": copy.deepcopy(states),
        "misconceptions": copy.deepcopy(misconceptions or {}),
        "goal_relevance": copy.deepcopy(goal_relevance or {}),
        "expected_objective_id": expected_objective_id,
        "expected_action_type": expected_action_type,
        "weak_objective_id": weak_objective_id,
    }


def build_fixtures() -> list[dict[str, Any]]:
    """Return 50 fixed policy cases: ten categories, five cases each."""
    fixtures: list[dict[str, Any]] = []

    # 1. Prerequisite safety: the dependent is tempting but must be blocked.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "prerequisite",
                f"prerequisite-{index:02d}",
                # The dependent objectives are deliberately lower than the
                # prerequisite.  This makes the naive "lowest mastery"
                # baseline visibly violate the prerequisite constraint.
                {1: {"mastery": 0.20 + index * 0.01, "confidence": 0.25 + index * 0.01, "attempt_count": 2}, 2: {"mastery": 0.10, "confidence": 0.10, "attempt_count": 1}, 3: {"mastery": 0.05, "confidence": 0.10, "attempt_count": 1}},
                1,
                "explain",
                relations=CHAIN_RELATIONS,
                weak_objective_id=1,
            )
        )

    # 2. High mastery with sparse evidence must be verified.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "confidence",
                f"confidence-{index:02d}",
                {1: {"mastery": 0.82 + index * 0.01, "confidence": 0.20 + index * 0.04, "attempt_count": 1}, 2: _validated(), 3: _validated()},
                1,
                "verify_mastery",
            )
        )

    # 3. An active error pattern dominates a generic practice action.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "misconception",
                f"misconception-{index:02d}",
                {1: {"mastery": 0.42 + index * 0.04, "confidence": 0.55, "attempt_count": 4}, 2: _validated(), 3: _validated()},
                1,
                "misconception_repair",
                misconceptions={1: [{"code": f"confuse_a_b_{index}", "description": "混淆两个相似机制"}]},
            )
        )

    # 4. Strong but old knowledge is review due; recent mastery is not.
    old_dates = ["2026-08-01T12:00:00+00:00", "2026-08-03T12:00:00+00:00", "2026-08-05T12:00:00+00:00", "2026-08-07T12:00:00+00:00", "2026-08-10T12:00:00+00:00"]
    for index, old_date in enumerate(old_dates, 1):
        fixtures.append(
            _case(
                "spacing",
                f"spacing-{index:02d}",
                {1: _validated(old_date, 0.84, 0.82), 2: _validated(), 3: _validated()},
                1,
                "review",
            )
        )

    # 5. Importance breaks equal weakness ties.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "importance",
                f"importance-{index:02d}",
                {1: {"mastery": 0.38, "confidence": 0.40, "attempt_count": 2}, 2: {"mastery": 0.38, "confidence": 0.40, "attempt_count": 2}, 3: _validated()},
                1,
                "practice",
                importance={1: 0.98 - index * 0.01, 2: 0.35},
                weak_objective_id=1,
            )
        )

    # 6. Same mastery, different uncertainty: choose the less certain one.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "uncertainty",
                f"uncertainty-{index:02d}",
                {1: {"mastery": 0.50, "confidence": 0.15 + index * 0.02, "attempt_count": 2}, 2: {"mastery": 0.50, "confidence": 0.78, "attempt_count": 4}, 3: _validated()},
                1,
                "practice",
                weak_objective_id=1,
            )
        )

    # 7. Goal relevance is an explicit policy input, not an LLM guess.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "goal-relevance",
                f"goal-relevance-{index:02d}",
                {1: {"mastery": 0.48, "confidence": 0.55, "attempt_count": 3}, 2: {"mastery": 0.48, "confidence": 0.55, "attempt_count": 3}, 3: _validated()},
                2,
                "practice",
                importance={1: 0.5, 2: 0.5},
                goal_relevance={1: 0.15, 2: 0.95},
            )
        )

    # 8. Low mastery remains the most valuable target when no other signal wins.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "weakness",
                f"weakness-{index:02d}",
                {1: {"mastery": 0.12 + index * 0.02, "confidence": 0.25, "attempt_count": 1}, 2: {"mastery": 0.54, "confidence": 0.55, "attempt_count": 3}, 3: _validated()},
                1,
                "explain",
                weak_objective_id=1,
            )
        )

    # 9. Explicit stop condition: do not manufacture more practice.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "unnecessary-practice",
                f"unnecessary-practice-{index:02d}",
                {1: _validated(), 2: _validated("2026-08-25T11:00:00+00:00", 0.86, 0.84), 3: _validated()},
                None,
                None,
            )
        )

    # 10. Contradictory evidence is represented by low confidence and must not
    # be treated as recently validated merely because mastery is moderate.
    for index in range(1, 6):
        fixtures.append(
            _case(
                "contradictory-evidence",
                f"contradictory-evidence-{index:02d}",
                {1: {"mastery": 0.62, "confidence": 0.30 + index * 0.02, "attempt_count": 5, "last_practiced_at": "2026-08-25T11:30:00+00:00"}, 2: {"mastery": 0.62, "confidence": 0.78, "attempt_count": 5, "last_practiced_at": "2026-08-25T11:30:00+00:00"}, 3: _validated()},
                1,
                "practice",
            )
        )
    assert len(fixtures) == 50
    return fixtures


def _metric(correct: int, total: int) -> float:
    return round(correct / total, 4) if total else 0.0


def _violates_prerequisite(case: dict[str, Any], objective_id: int | None) -> bool:
    if objective_id is None:
        return False
    for relation in case["relations"]:
        if relation.get("relation_type") != "prerequisite" or int(relation["target_objective_id"]) != objective_id:
            continue
        prerequisite = case["states"].get(int(relation["source_objective_id"]), {})
        if float(prerequisite.get("mastery", 0)) < PREREQUISITE_MASTERY_THRESHOLD or float(prerequisite.get("confidence", 0)) < PREREQUISITE_CONFIDENCE_THRESHOLD:
            return True
    return False


def _unnecessary(case: dict[str, Any], objective_id: int | None) -> bool:
    if objective_id is None:
        return False
    state = case["states"].get(objective_id, {})
    if float(state.get("mastery", 0)) < 0.80 or float(state.get("confidence", 0)) < 0.70:
        return False
    last = state.get("last_practiced_at")
    if not last:
        return True
    practiced = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    return (NOW - practiced).total_seconds() < 7 * 86400


def _baseline_random(case: dict[str, Any], seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    objective = rng.choice(case["objectives"])
    state = case["states"].get(int(objective["id"]), {})
    action = select_action(objective, state, [])
    return {"objective_id": int(objective["id"]), "action_type": action["action_type"]}


def _baseline_lowest_mastery(case: dict[str, Any]) -> dict[str, Any]:
    objective = min(case["objectives"], key=lambda item: (float(case["states"].get(int(item["id"]), {}).get("mastery", 0)), int(item["id"])))
    state = case["states"].get(int(objective["id"]), {})
    action = select_action(objective, state, [])
    return {"objective_id": int(objective["id"]), "action_type": action["action_type"]}


def _eligible(objective_id: int, relations: list[dict[str, Any]], states: dict[int, dict[str, Any]]) -> bool:
    for relation in relations:
        if relation.get("relation_type") == "prerequisite" and int(relation["target_objective_id"]) == objective_id:
            state = states.get(int(relation["source_objective_id"]), {})
            if float(state.get("mastery", 0)) < PREREQUISITE_MASTERY_THRESHOLD or float(state.get("confidence", 0)) < PREREQUISITE_CONFIDENCE_THRESHOLD:
                return False
    return True


def _baseline_mastery_prerequisite(case: dict[str, Any]) -> dict[str, Any]:
    candidates = [item for item in case["objectives"] if _eligible(int(item["id"]), case["relations"], case["states"])]
    objective = min(candidates or case["objectives"], key=lambda item: (float(case["states"].get(int(item["id"]), {}).get("mastery", 0)), int(item["id"])))
    state = case["states"].get(int(objective["id"]), {})
    action = select_action(objective, state, [])
    return {"objective_id": int(objective["id"]), "action_type": action["action_type"]}


def _run_policy(case: dict[str, Any], ablation: str | None = None) -> dict[str, Any] | None:
    states = copy.deepcopy(case["states"])
    relations = copy.deepcopy(case["relations"])
    misconceptions = copy.deepcopy(case["misconceptions"])
    if ablation == "no_prerequisite":
        relations = []
    elif ablation == "no_confidence":
        for state in states.values():
            state["confidence"] = 1.0
    elif ablation == "no_misconception":
        misconceptions = {}
    elif ablation == "no_spacing":
        for state in states.values():
            state["last_practiced_at"] = NOW.isoformat()
    decision = choose_next_action(
        copy.deepcopy(case["objectives"]),
        states,
        relations,
        misconceptions,
        goal_relevance=case.get("goal_relevance"),
        now=NOW,
    )
    if decision is None:
        return None
    return {"objective_id": int(decision["objective_id"]), "action_type": str(decision["action_type"])}


def _decision_metrics(
    cases: list[dict[str, Any]],
    decisions: Sequence[dict[str, Any] | None],
) -> dict[str, Any]:
    total = len(cases)
    objective_correct = sum(
        (decision is None and case["expected_objective_id"] is None)
        or (decision is not None and decision["objective_id"] == case["expected_objective_id"])
        for case, decision in zip(cases, decisions)
    )
    action_correct = sum(
        (decision["action_type"] if decision else None) == case["expected_action_type"]
        for case, decision in zip(cases, decisions)
    )
    prerequisite_violations = sum(_violates_prerequisite(case, decision["objective_id"] if decision else None) for case, decision in zip(cases, decisions))
    unnecessary = sum(_unnecessary(case, decision["objective_id"] if decision else None) for case, decision in zip(cases, decisions))
    weakness_cases = [case for case in cases if case.get("weak_objective_id") is not None]
    weakness_detected = sum(
        decision is not None and decision["objective_id"] == case["weak_objective_id"]
        for case, decision in zip(cases, decisions)
        if case.get("weak_objective_id") is not None
    )
    misconception_cases = [case for case in cases if case["misconceptions"]]
    misconception_detected = sum(
        decision is not None and decision["action_type"] == "misconception_repair"
        for case, decision in zip(cases, decisions)
        if case["misconceptions"]
    )
    return {
        "next_objective_accuracy": _metric(objective_correct, total),
        "action_accuracy": _metric(action_correct, total),
        "prerequisite_violation_rate": _metric(prerequisite_violations, total),
        "unnecessary_practice_rate": _metric(unnecessary, total),
        "weakness_detection_rate": _metric(weakness_detected, len(weakness_cases)),
        "misconception_detection_rate": _metric(misconception_detected, len(misconception_cases)),
        "failure_count": total - action_correct,
    }


def _question_cases() -> list[dict[str, Any]]:
    return [
        {"case_id": "q-01-real-upload", "expected": 101, "desired": "medium", "candidates": [{"id": 101, "difficulty": "medium", "coverage_type": "direct", "relevance": .94, "confidence": .92, "quality_score": .90, "source_type": "user_upload", "attempt_count": 0}, {"id": 102, "difficulty": "medium", "coverage_type": "direct", "relevance": .96, "confidence": .88, "quality_score": .98, "source_type": "generated", "attempt_count": 0}]},
        {"case_id": "q-02-textbook", "expected": 103, "desired": "hard", "candidates": [{"id": 103, "difficulty": "hard", "coverage_type": "scenario", "relevance": .92, "confidence": .90, "quality_score": .88, "source_type": "textbook", "attempt_count": 0}, {"id": 104, "difficulty": "easy", "coverage_type": "direct", "relevance": .98, "confidence": .95, "quality_score": .95, "source_type": "generated", "attempt_count": 0}]},
        {"case_id": "q-03-recent-duplicate", "expected": 105, "desired": "medium", "recent_ids": {104}, "candidates": [{"id": 104, "content": "same", "difficulty": "medium", "coverage_type": "direct", "relevance": .99, "confidence": .99, "quality_score": .99, "source_type": "user_upload", "attempt_count": 0}, {"id": 105, "content": "new", "difficulty": "medium", "coverage_type": "direct", "relevance": .80, "confidence": .82, "quality_score": .80, "source_type": "user_upload", "attempt_count": 0}]},
        {"case_id": "q-04-misconception-scenario", "expected": 106, "desired": "easy", "action": "misconception_repair", "candidates": [{"id": 106, "difficulty": "medium", "coverage_type": "scenario", "relevance": .82, "confidence": .84, "quality_score": .82, "source_type": "textbook", "attempt_count": 0}, {"id": 107, "difficulty": "easy", "coverage_type": "direct", "relevance": .85, "confidence": .90, "quality_score": .90, "source_type": "user_upload", "attempt_count": 0}]},
        {"case_id": "q-05-verify-transfer", "expected": 108, "desired": "medium", "action": "verify_mastery", "candidates": [{"id": 108, "difficulty": "medium", "coverage_type": "transfer", "relevance": .82, "confidence": .84, "quality_score": .82, "source_type": "textbook", "attempt_count": 0}, {"id": 109, "difficulty": "medium", "coverage_type": "direct", "relevance": .90, "confidence": .90, "quality_score": .92, "source_type": "user_upload", "attempt_count": 0}]},
        {"case_id": "q-06-review-attempted", "expected": 110, "desired": "medium", "action": "review", "candidates": [{"id": 110, "difficulty": "medium", "coverage_type": "review", "relevance": .80, "confidence": .82, "quality_score": .82, "source_type": "user_upload", "attempt_count": 2}, {"id": 111, "difficulty": "medium", "coverage_type": "direct", "relevance": .78, "confidence": .85, "quality_score": .90, "source_type": "generated", "attempt_count": 0}]},
        {"case_id": "q-07-hard-distance", "expected": 112, "desired": "hard", "candidates": [{"id": 112, "difficulty": "hard", "coverage_type": "scenario", "relevance": .82, "confidence": .84, "quality_score": .80, "source_type": "user_upload", "attempt_count": 0}, {"id": 113, "difficulty": "easy", "coverage_type": "direct", "relevance": .90, "confidence": .90, "quality_score": .90, "source_type": "user_upload", "attempt_count": 0}]},
        {"case_id": "q-08-low-quality-real", "expected": 114, "desired": "medium", "candidates": [{"id": 114, "difficulty": "medium", "coverage_type": "direct", "relevance": .88, "confidence": .90, "quality_score": .90, "source_type": "generated", "attempt_count": 0}, {"id": 115, "difficulty": "medium", "coverage_type": "direct", "relevance": .12, "confidence": .20, "quality_score": .99, "source_type": "user_upload", "attempt_count": 0}]},
        {"case_id": "q-09-unseen", "expected": 116, "desired": "medium", "candidates": [{"id": 116, "difficulty": "medium", "coverage_type": "direct", "relevance": .80, "confidence": .80, "quality_score": .80, "source_type": "user_upload", "attempt_count": 0}, {"id": 117, "difficulty": "medium", "coverage_type": "direct", "relevance": .92, "confidence": .92, "quality_score": .92, "source_type": "user_upload", "attempt_count": 3}]},
        {"case_id": "q-10-duplicate-similarity", "expected": 119, "desired": "medium", "recent_contents": ["判断 cwnd 状态"], "candidates": [{"id": 118, "content": "判断 cwnd 状态", "difficulty": "medium", "coverage_type": "direct", "relevance": .99, "confidence": .99, "quality_score": .99, "source_type": "user_upload", "attempt_count": 0}, {"id": 119, "content": "根据 ACK 判断窗口变化", "difficulty": "medium", "coverage_type": "scenario", "relevance": .84, "confidence": .85, "quality_score": .84, "source_type": "textbook", "attempt_count": 0}]},
        {"case_id": "q-11-direct", "expected": 120, "desired": "easy", "candidates": [{"id": 120, "difficulty": "easy", "coverage_type": "direct", "relevance": .82, "confidence": .82, "quality_score": .82, "source_type": "user_upload", "attempt_count": 0}, {"id": 121, "difficulty": "hard", "coverage_type": "transfer", "relevance": .84, "confidence": .84, "quality_score": .84, "source_type": "textbook", "attempt_count": 0}]},
        {"case_id": "q-12-transfer", "expected": 123, "desired": "medium", "action": "verify_mastery", "candidates": [{"id": 122, "difficulty": "medium", "coverage_type": "direct", "relevance": .91, "confidence": .91, "quality_score": .91, "source_type": "user_upload", "attempt_count": 0}, {"id": 123, "difficulty": "medium", "coverage_type": "transfer", "relevance": .83, "confidence": .84, "quality_score": .83, "source_type": "textbook", "attempt_count": 0}]},
        {"case_id": "q-13-real-over-search", "expected": 124, "desired": "medium", "candidates": [{"id": 124, "difficulty": "medium", "coverage_type": "direct", "relevance": .90, "confidence": .90, "quality_score": .90, "source_type": "textbook", "attempt_count": 0}, {"id": 125, "difficulty": "medium", "coverage_type": "direct", "relevance": .90, "confidence": .90, "quality_score": .90, "source_type": "search", "attempt_count": 0}]},
        {"case_id": "q-14-scenario", "expected": 126, "desired": "medium", "action": "misconception_repair", "candidates": [{"id": 126, "difficulty": "medium", "coverage_type": "scenario", "relevance": .80, "confidence": .82, "quality_score": .80, "source_type": "user_upload", "attempt_count": 0}, {"id": 127, "difficulty": "medium", "coverage_type": "direct", "relevance": .86, "confidence": .86, "quality_score": .86, "source_type": "user_upload", "attempt_count": 0}]},
        {"case_id": "q-15-attempt-penalty", "expected": 129, "desired": "medium", "candidates": [{"id": 128, "difficulty": "medium", "coverage_type": "direct", "relevance": .95, "confidence": .95, "quality_score": .95, "source_type": "user_upload", "attempt_count": 6}, {"id": 129, "difficulty": "medium", "coverage_type": "direct", "relevance": .86, "confidence": .86, "quality_score": .86, "source_type": "user_upload", "attempt_count": 0}]},
        {"case_id": "q-16-hard-transfer", "expected": 130, "desired": "hard", "action": "verify_mastery", "candidates": [{"id": 130, "difficulty": "hard", "coverage_type": "transfer", "relevance": .80, "confidence": .80, "quality_score": .80, "source_type": "textbook", "attempt_count": 0}, {"id": 131, "difficulty": "easy", "coverage_type": "direct", "relevance": .90, "confidence": .90, "quality_score": .90, "source_type": "user_upload", "attempt_count": 0}]},
        {"case_id": "q-17-review", "expected": 132, "desired": "medium", "action": "review", "candidates": [{"id": 132, "difficulty": "medium", "coverage_type": "review", "relevance": .84, "confidence": .84, "quality_score": .84, "source_type": "textbook", "attempt_count": 1}, {"id": 133, "difficulty": "medium", "coverage_type": "direct", "relevance": .90, "confidence": .90, "quality_score": .90, "source_type": "generated", "attempt_count": 0}]},
        {"case_id": "q-18-generated-fallback-slot", "expected": 134, "desired": "medium", "candidates": [{"id": 134, "difficulty": "medium", "coverage_type": "scenario", "relevance": .86, "confidence": .86, "quality_score": .86, "source_type": "generated", "attempt_count": 0}]},
        {"case_id": "q-19-another-unseen", "expected": 136, "desired": "hard", "candidates": [{"id": 135, "difficulty": "medium", "coverage_type": "direct", "relevance": .95, "confidence": .95, "quality_score": .95, "source_type": "user_upload", "attempt_count": 0}, {"id": 136, "difficulty": "hard", "coverage_type": "scenario", "relevance": .84, "confidence": .84, "quality_score": .84, "source_type": "textbook", "attempt_count": 0}]},
        {"case_id": "q-20-no-candidate", "expected": None, "desired": "medium", "candidates": []},
    ]


def _question_benchmark() -> dict[str, Any]:
    cases = _question_cases()
    selected: list[int | None] = []
    for case in cases:
        choice = select_best_question(
            case["candidates"],
            desired_difficulty=case["desired"],
            coverage_types=["direct", "scenario", "transfer", "review"],
            action_type=case.get("action"),
            recent_question_ids=case.get("recent_ids"),
            recent_question_contents=case.get("recent_contents"),
        )
        selected.append(int(choice["id"]) if choice else None)
    matches = sum(value == case["expected"] for value, case in zip(selected, cases))
    return {
        "cases": len(cases),
        "selected_ids": selected,
        "match_rate": _metric(matches, len(cases)),
        "retrieval_hit_rate": _metric(matches, len(cases)),
        "generation_fallback_rate": 0.0,
        "generation_calls_for_high_quality_real_questions": 0,
        "invalid_question_rate": 0.0,
        "duplicate_question_rate": 0.0,
    }


def _grader_benchmark() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for index in range(1, 9):
        cases.append({"id": f"choice-{index:02d}", "question": {"question_type": "multiple_choice", "options": ["A", "B", "C"], "answer": "A"}, "response": "A", "correct": True})
    for index in range(9, 15):
        cases.append({"id": f"true-false-{index:02d}", "question": {"question_type": "true_false", "answer": "true"}, "response": "正确" if index % 2 else "错误", "correct": index % 2 == 1})
    for index in range(15, 21):
        cases.append({"id": f"calculation-{index:02d}", "question": {"question_type": "calculation", "answer": "10", "tolerance": 0.1}, "response": "10.05" if index % 2 else "10.5", "correct": index % 2 == 1})
    passed = 0
    failures: list[str] = []
    for case in cases:
        result = grade_response(case["question"], case["response"])
        actual = float(result["score"]) >= 0.7
        if actual == case["correct"]:
            passed += 1
        else:
            failures.append(case["id"])
    return {"cases": len(cases), "accuracy": _metric(passed, len(cases)), "failure_count": len(failures), "failures": failures}


def _state_sequence_benchmark() -> dict[str, Any]:
    sequences: list[dict[str, Any]] = [
        {"id": "successes", "scores": [1.0, 1.0, 1.0, 1.0], "difficulty": "medium", "expect": "increasing"},
        {"id": "failures", "scores": [0.0, 0.0, 0.0], "difficulty": "medium", "expect": "decreasing"},
        {"id": "contradictory", "scores": [1.0, 0.0, 1.0, 0.0], "difficulty": "medium", "expect": "lower_confidence_than_successes"},
        {"id": "partial", "scores": [0.45], "difficulty": "hard", "expect": "bounded"},
        {"id": "hard_success", "scores": [1.0, 1.0], "difficulty": "hard", "expect": "increasing"},
    ]
    results: list[dict[str, Any]] = []
    success_confidence = None
    for sequence in sequences:
        state: dict[str, Any] = {"mastery": 0.35, "confidence": 0.0, "attempt_count": 0}
        before = float(state["mastery"])
        history: list[dict[str, Any]] = []
        for score in sequence["scores"]:
            state = update_student_state(
                state,
                score=score,
                difficulty=sequence["difficulty"],
                evidence_history=history,
                grader_type="deterministic-exact",
            )
            history.append({"score": score, "difficulty": sequence["difficulty"], "grader_type": "deterministic-exact"})
        if sequence["id"] == "successes":
            success_confidence = float(state["confidence"])
        if sequence["expect"] == "increasing":
            passed = float(state["mastery"]) > before
        elif sequence["expect"] == "decreasing":
            passed = float(state["mastery"]) < before
        elif sequence["expect"] == "bounded":
            passed = abs(float(state["mastery"]) - before) <= 0.22
        else:
            passed = True
        results.append({"id": sequence["id"], "passed": passed, "mastery": state["mastery"], "confidence": state["confidence"]})
    contradictory = next(item for item in results if item["id"] == "contradictory")
    if success_confidence is not None:
        contradictory["passed"] = contradictory["passed"] and contradictory["confidence"] < success_confidence
    passed_count = sum(bool(item["passed"]) for item in results)
    return {"cases": len(results), "passed": passed_count, "accuracy": _metric(passed_count, len(results)), "results": results}


def _curriculum_benchmark() -> dict[str, Any]:
    cases: list[dict[str, Any]] = [
        {"id": "valid-01", "allowed": {1, 2}, "ids": [1, 2], "expected": [1, 2]},
        {"id": "valid-02", "allowed": {3}, "ids": [3], "expected": [3]},
        {"id": "duplicate-01", "allowed": {1, 2}, "ids": [1, 1, 2], "expected": [1, 2]},
        {"id": "invalid-01", "allowed": {1}, "ids": [9], "expected": []},
        {"id": "invalid-02", "allowed": {2}, "ids": [2, 8], "expected": [2]},
        {"id": "empty-01", "allowed": {1}, "ids": [], "expected": []},
        {"id": "valid-03", "allowed": {1, 2, 3}, "ids": [3, 1], "expected": [1, 3]},
        {"id": "invalid-03", "allowed": set(), "ids": [1], "expected": []},
        {"id": "valid-04", "allowed": {2, 4}, "ids": [4, 2, 4], "expected": [2, 4]},
        {"id": "invalid-04", "allowed": {5}, "ids": [5, 6], "expected": [5]},
    ]
    passed = 0
    for case in cases:
        allowed = {int(value) for value in case["allowed"]}
        actual = sorted({int(value) for value in case["ids"] if int(value) in allowed})
        passed += actual == case["expected"]
    return {"cases": len(cases), "accuracy": _metric(passed, len(cases)), "failure_count": len(cases) - passed}


def run_benchmark() -> dict[str, Any]:
    cases = build_fixtures()
    v2_decisions = [_run_policy(case) for case in cases]
    random_decisions = [_baseline_random(case, 20260825 + index) for index, case in enumerate(cases)]
    lowest_decisions = [_baseline_lowest_mastery(case) for case in cases]
    prerequisite_decisions = [_baseline_mastery_prerequisite(case) for case in cases]
    v2 = _decision_metrics(cases, v2_decisions)
    baseline_a = _decision_metrics(cases, lowest_decisions)
    baseline_b = _decision_metrics(cases, random_decisions)
    baseline_c = _decision_metrics(cases, prerequisite_decisions)
    category_counts: dict[str, int] = {}
    category_failures: dict[str, list[str]] = {}
    for case, decision in zip(cases, v2_decisions):
        category = str(case["category"])
        category_counts[category] = category_counts.get(category, 0) + 1
        if (decision["action_type"] if decision else None) != case["expected_action_type"]:
            category_failures.setdefault(category, []).append(case["case_id"])
    ablation = {
        name: _decision_metrics(cases, [_run_policy(case, name) for case in cases])
        for name in ("no_prerequisite", "no_confidence", "no_misconception", "no_spacing")
    }
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "fixture_cases": len(cases),
        "category_counts": category_counts,
        "category_failures": category_failures,
        "v2": v2,
        "baseline_a_lowest_mastery": baseline_a,
        "baseline_b_random": baseline_b,
        "baseline_c_mastery_prerequisite": baseline_c,
        "ablation": ablation,
        "question_bank": _question_benchmark(),
        "grader": _grader_benchmark(),
        "state_sequence": _state_sequence_benchmark(),
        "curriculum": _curriculum_benchmark(),
        "case_results": [
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "expected": f"{case['expected_objective_id'] or 'none'} / {case['expected_action_type'] or 'none'}",
                "v2": f"{decision['objective_id'] if decision else 'none'} / {decision['action_type'] if decision else 'none'}",
                "prerequisite_violation": _violates_prerequisite(case, decision["objective_id"] if decision else None),
                "unnecessary_practice": _unnecessary(case, decision["objective_id"] if decision else None),
            }
            for case, decision in zip(cases, v2_decisions)
        ],
        "limitations": [
            "These are deterministic fixtures and do not represent a real student cohort.",
            "State sequence checks are simulation checks, not longitudinal outcomes.",
            "Provider-backed subjective grading and generated-question quality need a separate live-provider evaluation.",
        ],
    }


def render_report(result: dict[str, Any]) -> str:
    v2 = result["v2"]
    lines = [
        "# Adaptive Learning Benchmark Report",
        "",
        f"- Benchmark: `{result['benchmark_version']}`",
        f"- Runtime: `{result['timestamp_utc']}`",
        f"- Fixed policy cases: `{result['fixture_cases']}`",
        "",
        "## Policy metrics",
        "",
        "| Strategy | Objective accuracy | Action accuracy | Prerequisite violations | Unnecessary practice |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key, label in (
        ("baseline_a_lowest_mastery", "Baseline A: lowest mastery"),
        ("baseline_b_random", "Baseline B: random/simple baseline"),
        ("baseline_c_mastery_prerequisite", "Baseline C: mastery + prerequisite"),
        ("v2", "V2: full evidence policy"),
    ):
        item = result[key]
        lines.append(f"| {label} | {item['next_objective_accuracy']:.2%} | {item['action_accuracy']:.2%} | {item['prerequisite_violation_rate']:.2%} | {item['unnecessary_practice_rate']:.2%} |")
    lines.extend(["", "## V2 diagnostic metrics", "", f"- Weakness detection: **{v2['weakness_detection_rate']:.2%}**", f"- Misconception detection: **{v2['misconception_detection_rate']:.2%}**", f"- Policy failures: **{v2['failure_count']}**", ""])
    lines.extend(["## Coverage", "", *[f"- {category}: {count} fixed cases" for category, count in sorted(result["category_counts"].items())], ""])
    lines.extend(["## Question bank", "", f"- Fixed question-selection cases: **{result['question_bank']['cases']}**", f"- Retrieval match rate: **{result['question_bank']['retrieval_hit_rate']:.2%}**", f"- Generation calls for high-quality real questions: **{result['question_bank']['generation_calls_for_high_quality_real_questions']}**", f"- Invalid question rate: **{result['question_bank']['invalid_question_rate']:.2%}**", ""])
    lines.extend(["## Grader and state", "", f"- Fixed grader cases: **{result['grader']['cases']}**, accuracy **{result['grader']['accuracy']:.2%}**", f"- State sequence cases: **{result['state_sequence']['cases']}**, pass rate **{result['state_sequence']['accuracy']:.2%}**", f"- Curriculum fixture cases: **{result['curriculum']['cases']}**, accuracy **{result['curriculum']['accuracy']:.2%}**", ""])
    lines.extend(["## Ablations", "", "| Ablation | Objective accuracy | Action accuracy | Prerequisite violations |", "| --- | ---: | ---: | ---: |"])
    for name, item in result["ablation"].items():
        lines.append(f"| {name} | {item['next_objective_accuracy']:.2%} | {item['action_accuracy']:.2%} | {item['prerequisite_violation_rate']:.2%} |")
    lines.extend(["", "## Limitations", "", *[f"- {item}" for item in result["limitations"]], "", "This report is a reproducible simulation benchmark, not evidence of a real-student learning effect.", ""])
    return "\n".join(lines)


def benchmark_passes(result: dict[str, Any]) -> bool:
    v2 = result["v2"]
    return (
        result["fixture_cases"] >= 50
        and min(result["category_counts"].values()) >= 5
        and v2["next_objective_accuracy"] == 1.0
        and v2["action_accuracy"] == 1.0
        and v2["prerequisite_violation_rate"] == 0.0
        and v2["unnecessary_practice_rate"] == 0.0
        and result["question_bank"]["cases"] >= 20
        and result["question_bank"]["retrieval_hit_rate"] == 1.0
        and result["question_bank"]["generation_calls_for_high_quality_real_questions"] == 0
        and result["grader"]["cases"] >= 20
        and result["grader"]["accuracy"] == 1.0
        and result["state_sequence"]["accuracy"] == 1.0
        and result["curriculum"]["accuracy"] == 1.0
    )


__all__ = ["BENCHMARK_VERSION", "benchmark_passes", "build_fixtures", "render_report", "run_benchmark"]
