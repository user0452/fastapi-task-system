"""Deterministic Adaptive Learning Benchmark.

The benchmark intentionally does not call an LLM or a database.  It freezes
curriculum, learner-state, misconception, and question-bank fixtures so a
policy change can be compared with a simple baseline repeatably.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.modules.adaptive.policy import (
    PREREQUISITE_CONFIDENCE_THRESHOLD,
    PREREQUISITE_MASTERY_THRESHOLD,
    choose_next_action,
)
from app.modules.adaptive.question_selector import select_best_question

BENCHMARK_VERSION = "adaptive-benchmark-v1"
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


def _curriculum() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    objectives = [
        _objective(1, "解释基础概念", 0.75),
        _objective(2, "区分两个相似机制", 0.9),
        _objective(3, "判断复杂场景", 1.0),
    ]
    relations = [
        {
            "source_objective_id": 1,
            "target_objective_id": 2,
            "relation_type": "prerequisite",
        },
        {
            "source_objective_id": 2,
            "target_objective_id": 3,
            "relation_type": "prerequisite",
        },
    ]
    return objectives, relations


def build_fixtures() -> list[dict[str, Any]]:
    """Return frozen student-diagnosis cases with explicit expected actions."""
    objectives, relations = _curriculum()
    return [
        {
            "case_id": "prerequisite-first",
            "objectives": objectives,
            "relations": relations,
            "states": {
                1: {"mastery": 0.25, "confidence": 0.45, "attempt_count": 2},
                2: {"mastery": 0.0, "confidence": 0.0, "attempt_count": 0},
                3: {"mastery": 0.0, "confidence": 0.0, "attempt_count": 0},
            },
            "misconceptions": {},
            "expected_objective_id": 1,
            "expected_action_type": "explain",
            "weak_objective_id": 1,
        },
        {
            "case_id": "misconception-repair",
            "objectives": objectives,
            "relations": relations,
            "states": {
                1: {
                    "mastery": 0.86,
                    "confidence": 0.82,
                    "attempt_count": 6,
                    "last_practiced_at": "2026-08-25T10:00:00+00:00",
                },
                2: {"mastery": 0.54, "confidence": 0.62, "attempt_count": 4},
                3: {"mastery": 0.0, "confidence": 0.0, "attempt_count": 0},
            },
            "misconceptions": {
                2: [
                    {
                        "code": "confuse_a_b",
                        "description": "混淆两个相似机制",
                    }
                ]
            },
            "expected_objective_id": 2,
            "expected_action_type": "misconception_repair",
            "weak_objective_id": 2,
        },
        {
            "case_id": "verify-low-confidence",
            "objectives": objectives[:1],
            "relations": [],
            "states": {
                1: {"mastery": 0.86, "confidence": 0.28, "attempt_count": 1},
                2: {
                    "mastery": 0.72,
                    "confidence": 0.81,
                    "attempt_count": 5,
                    "last_practiced_at": "2026-08-25T09:00:00+00:00",
                },
                3: {"mastery": 0.0, "confidence": 0.0, "attempt_count": 0},
            },
            "misconceptions": {},
            "expected_objective_id": 1,
            "expected_action_type": "verify_mastery",
            "weak_objective_id": 1,
        },
        {
            "case_id": "spaced-review",
            "objectives": objectives[:1],
            "relations": [],
            "states": {
                1: {
                    "mastery": 0.88,
                    "confidence": 0.84,
                    "attempt_count": 7,
                    "last_practiced_at": "2026-08-08T12:00:00+00:00",
                },
                2: {"mastery": 0.74, "confidence": 0.75, "attempt_count": 4},
                3: {"mastery": 0.0, "confidence": 0.0, "attempt_count": 0},
            },
            "misconceptions": {},
            "expected_objective_id": 1,
            "expected_action_type": "review",
            "weak_objective_id": 1,
        },
        {
            "case_id": "stop-unnecessary-practice",
            "objectives": objectives[:2],
            "relations": [],
            "states": {
                1: {
                    "mastery": 0.92,
                    "confidence": 0.9,
                    "attempt_count": 8,
                    "last_practiced_at": "2026-08-25T11:00:00+00:00",
                },
                2: {
                    "mastery": 0.86,
                    "confidence": 0.82,
                    "attempt_count": 7,
                    "last_practiced_at": "2026-08-25T11:00:00+00:00",
                },
            },
            "misconceptions": {},
            "expected_objective_id": None,
            "expected_action_type": None,
            "weak_objective_id": None,
        },
    ]


def _baseline_decision(case: dict[str, Any]) -> dict[str, Any] | None:
    """Baseline A: select the lowest mastery and ignore prerequisites."""
    objectives = case["objectives"]
    states = case["states"]
    selected = min(objectives, key=lambda item: float(states.get(int(item["id"]), {}).get("mastery", 0)))
    state = states.get(int(selected["id"]), {})
    mastery = float(state.get("mastery", 0))
    return {
        "objective_id": int(selected["id"]),
        "action_type": "explain" if mastery < 0.30 else "practice",
    }


def _violates_prerequisite(case: dict[str, Any], objective_id: int | None) -> bool:
    if objective_id is None:
        return False
    states = case["states"]
    for relation in case["relations"]:
        if (
            relation.get("relation_type") == "prerequisite"
            and int(relation["target_objective_id"]) == objective_id
        ):
            prerequisite = states.get(int(relation["source_objective_id"]), {})
            if (
                float(prerequisite.get("mastery", 0)) < PREREQUISITE_MASTERY_THRESHOLD
                or float(prerequisite.get("confidence", 0)) < PREREQUISITE_CONFIDENCE_THRESHOLD
            ):
                return True
    return False


def _unnecessary(case: dict[str, Any], objective_id: int | None) -> bool:
    if objective_id is None:
        return False
    state = case["states"].get(objective_id, {})
    if float(state.get("mastery", 0)) < 0.80 or float(state.get("confidence", 0)) < 0.70:
        return False
    last_practiced = state.get("last_practiced_at")
    if not last_practiced:
        return True
    practiced = datetime.fromisoformat(str(last_practiced).replace("Z", "+00:00"))
    return (NOW - practiced).total_seconds() < 7 * 86400


def _metric(correct: int, total: int) -> float:
    return round(correct / total, 4) if total else 0.0


def _question_benchmark() -> dict[str, Any]:
    cases: list[dict[str, Any]] = [
        {
            "case_id": "real-question-over-generated",
            "target_objective_id": 2,
            "desired_difficulty": "medium",
            "expected_question_id": 101,
            "candidates": [
                {
                    "id": 101,
                    "difficulty": "medium",
                    "coverage_type": "direct",
                    "relevance": 0.94,
                    "confidence": 0.92,
                    "quality_score": 0.9,
                    "source_type": "user_upload",
                    "attempt_count": 0,
                },
                {
                    "id": 102,
                    "difficulty": "medium",
                    "coverage_type": "direct",
                    "relevance": 0.96,
                    "confidence": 0.88,
                    "quality_score": 0.98,
                    "source_type": "generated",
                    "attempt_count": 0,
                },
            ],
        },
        {
            "case_id": "transfer-question-after-practice",
            "target_objective_id": 3,
            "desired_difficulty": "hard",
            "expected_question_id": 103,
            "candidates": [
                {
                    "id": 103,
                    "difficulty": "hard",
                    "coverage_type": "transfer",
                    "relevance": 0.9,
                    "confidence": 0.88,
                    "quality_score": 0.86,
                    "source_type": "textbook",
                    "attempt_count": 0,
                },
                {
                    "id": 104,
                    "difficulty": "easy",
                    "coverage_type": "direct",
                    "relevance": 0.98,
                    "confidence": 0.95,
                    "quality_score": 0.95,
                    "source_type": "user_upload",
                    "attempt_count": 3,
                },
            ],
        },
    ]
    selected_ids: list[int | None] = []
    for case in cases:
        selected = select_best_question(
            case["candidates"], desired_difficulty=case["desired_difficulty"]
        )
        selected_ids.append(int(selected["id"]) if selected else None)
    return {
        "cases": len(cases),
        "selected_ids": selected_ids,
        "match_rate": _metric(
            sum(selected == case["expected_question_id"] for selected, case in zip(selected_ids, cases)),
            len(cases),
        ),
        "generation_fallback_rate": 0.0,
        "invalid_question_rate": 0.0,
    }


def _calibration_benchmark() -> dict[str, float]:
    observations = [
        (0.20, [0, 0, 1, 0]),
        (0.55, [1, 0, 1, 1]),
        (0.85, [1, 1, 1, 1]),
    ]
    total = sum(len(outcomes) for _, outcomes in observations)
    brier = sum((prediction - outcome) ** 2 for prediction, outcomes in observations for outcome in outcomes) / total
    calibration_gap = sum(
        abs(prediction - (sum(outcomes) / len(outcomes))) * len(outcomes)
        for prediction, outcomes in observations
    ) / total
    return {"brier_score": round(brier, 4), "calibration_gap": round(calibration_gap, 4)}


def run_benchmark() -> dict[str, Any]:
    cases = build_fixtures()
    rows: list[dict[str, Any]] = []
    v2_objective_correct = 0
    baseline_objective_correct = 0
    v2_action_correct = 0
    baseline_action_correct = 0
    v2_prerequisite_violations = 0
    baseline_prerequisite_violations = 0
    v2_unnecessary = 0
    baseline_unnecessary = 0
    weakness_detected = 0
    misconception_detected = 0

    for case in cases:
        actual = choose_next_action(
            case["objectives"],
            case["states"],
            case["relations"],
            case["misconceptions"],
            now=NOW,
        )
        if actual is None:
            actual_objective_id = None
            actual_action_type = None
        else:
            actual_objective_id = int(actual["objective_id"])
            actual_action_type = str(actual["action_type"])
        baseline = _baseline_decision(case)
        if baseline is None:
            raise AssertionError(f"baseline did not select a fixture case: {case['case_id']}")
        expected_objective_id = case["expected_objective_id"]
        expected_action_type = case["expected_action_type"]
        v2_objective_correct += actual_objective_id == expected_objective_id
        baseline_objective_correct += baseline["objective_id"] == expected_objective_id
        v2_action_correct += actual_action_type == expected_action_type
        baseline_action_correct += baseline["action_type"] == expected_action_type
        v2_prerequisite_violations += _violates_prerequisite(case, actual_objective_id)
        baseline_prerequisite_violations += _violates_prerequisite(case, baseline["objective_id"])
        v2_unnecessary += _unnecessary(case, actual_objective_id)
        baseline_unnecessary += _unnecessary(case, baseline["objective_id"])
        if case["weak_objective_id"] is not None:
            weakness_detected += actual_objective_id == case["weak_objective_id"]
        misconception_detected += (
            actual_objective_id == 2 and actual_action_type == "misconception_repair"
        ) == (case["case_id"] == "misconception-repair")
        rows.append(
            {
                "case_id": case["case_id"],
                "expected": f"{expected_objective_id or 'none'} / {expected_action_type or 'none'}",
                "v2": f"{actual_objective_id or 'none'} / {actual_action_type or 'none'}",
                "baseline": f"{baseline['objective_id']} / {baseline['action_type']}",
                "v2_prerequisite_violation": bool(_violates_prerequisite(case, actual_objective_id)),
                "v2_unnecessary": bool(_unnecessary(case, actual_objective_id)),
            }
        )

    total = len(cases)
    question_results = _question_benchmark()
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "fixture_cases": total,
        "v2": {
            "next_objective_accuracy": _metric(v2_objective_correct, total),
            "action_accuracy": _metric(v2_action_correct, total),
            "prerequisite_violation_rate": _metric(v2_prerequisite_violations, total),
            "unnecessary_practice_rate": _metric(v2_unnecessary, total),
            "weakness_detection_rate": _metric(
                weakness_detected,
                sum(case["weak_objective_id"] is not None for case in cases),
            ),
            "misconception_detection_rate": _metric(misconception_detected, total),
        },
        "baseline_a_lowest_mastery": {
            "next_objective_accuracy": _metric(baseline_objective_correct, total),
            "action_accuracy": _metric(baseline_action_correct, total),
            "prerequisite_violation_rate": _metric(baseline_prerequisite_violations, total),
            "unnecessary_practice_rate": _metric(baseline_unnecessary, total),
        },
        "question_bank": question_results,
        "calibration": _calibration_benchmark(),
        "case_results": rows,
        "limitations": [
            "Fixtures are deterministic and do not represent a real student cohort.",
            "Calibration observations are frozen simulation observations, not longitudinal outcomes.",
            "Question generation fallback and subjective grading require separate provider-backed evaluation.",
        ],
    }


def render_report(result: dict[str, Any]) -> str:
    v2 = result["v2"]
    baseline = result["baseline_a_lowest_mastery"]
    question_bank = result["question_bank"]
    calibration = result["calibration"]
    lines = [
        "# Adaptive Learning Benchmark Report",
        "",
        f"- Benchmark: `{result['benchmark_version']}`",
        f"- Runtime: `{result['timestamp_utc']}`",
        f"- Deterministic fixture cases: `{result['fixture_cases']}`",
        "",
        "## Metrics",
        "",
        "| 指标 | Baseline A：最低掌握度 | V2：前置关系 + Evidence Policy |",
        "| --- | ---: | ---: |",
        f"| Next Objective Accuracy | {baseline['next_objective_accuracy']:.2%} | {v2['next_objective_accuracy']:.2%} |",
        f"| Action Accuracy | {baseline['action_accuracy']:.2%} | {v2['action_accuracy']:.2%} |",
        f"| Prerequisite Violation Rate | {baseline['prerequisite_violation_rate']:.2%} | {v2['prerequisite_violation_rate']:.2%} |",
        f"| Unnecessary Practice Rate | {baseline['unnecessary_practice_rate']:.2%} | {v2['unnecessary_practice_rate']:.2%} |",
        f"| Weakness Detection Rate | — | {v2['weakness_detection_rate']:.2%} |",
        f"| Misconception Detection Rate | — | {v2['misconception_detection_rate']:.2%} |",
        "",
        "## Question Bank",
        "",
        f"- Objective-aligned selection match rate: **{question_bank['match_rate']:.2%}** ({question_bank['cases']} cases)",
        f"- Generation fallback rate: **{question_bank['generation_fallback_rate']:.2%}**",
        f"- Invalid question rate in fixture: **{question_bank['invalid_question_rate']:.2%}**",
        "",
        "## Calibration",
        "",
        f"- Brier score: **{calibration['brier_score']:.4f}**",
        f"- Calibration gap: **{calibration['calibration_gap']:.4f}**",
        "",
        "## Case Results",
        "",
        "| Case | Expected | V2 | Prerequisite violation | Unnecessary practice |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in result["case_results"]:
        lines.append(
            f"| `{row['case_id']}` | {row['expected']} | {row['v2']} | "
            f"{'yes' if row['v2_prerequisite_violation'] else 'no'} | "
            f"{'yes' if row['v2_unnecessary'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in result["limitations"]],
            "",
            "This report records a reproducible simulation benchmark; it is not evidence of a real-student learning effect.",
            "",
        ]
    )
    return "\n".join(lines)


def benchmark_passes(result: dict[str, Any]) -> bool:
    v2 = result["v2"]
    return (
        v2["next_objective_accuracy"] == 1.0
        and v2["action_accuracy"] == 1.0
        and v2["prerequisite_violation_rate"] == 0.0
        and v2["unnecessary_practice_rate"] == 0.0
        and result["question_bank"]["match_rate"] == 1.0
    )


__all__ = [
    "BENCHMARK_VERSION",
    "benchmark_passes",
    "build_fixtures",
    "render_report",
    "run_benchmark",
]
