"""Transparent, deterministic learning policy and student-state updater."""

from __future__ import annotations

from datetime import datetime, timezone
from math import exp
from typing import Any

POLICY_VERSION = "adaptive-policy-v2-deterministic-1"
STATE_MODEL_VERSION = "bkt-inspired-v1"
PREREQUISITE_MASTERY_THRESHOLD = 0.60
PREREQUISITE_CONFIDENCE_THRESHOLD = 0.35
MASTERED_MASTERY_THRESHOLD = 0.80
MASTERED_CONFIDENCE_THRESHOLD = 0.70
MAX_MASTERY_STEP = 0.22
CONFIDENCE_HISTORY_LIMIT = 20


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return clamp(float(value))
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _days_since(value: Any, now: datetime | None = None) -> float | None:
    practiced = _parse_datetime(value)
    if practiced is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0.0, (current - practiced).total_seconds() / 86400)


def _state_for(objective: dict[str, Any], states: dict[int, dict[str, Any]]) -> dict[str, Any]:
    objective_id = int(objective["id"])
    return states.get(objective_id, {})


def _prerequisite_ids(objective_id: int, relations: list[dict[str, Any]]) -> list[int]:
    """Return prerequisites using the V2 direction: source -> target."""
    return [
        int(relation["source_objective_id"])
        for relation in relations
        if relation.get("relation_type") == "prerequisite"
        and int(relation.get("target_objective_id") or 0) == objective_id
    ]


def prerequisite_eligibility(
    objective_id: int,
    relations: list[dict[str, Any]],
    states: dict[int, dict[str, Any]],
) -> tuple[bool, list[int]]:
    blocked: list[int] = []
    for prerequisite_id in _prerequisite_ids(objective_id, relations):
        state = states.get(prerequisite_id, {})
        if (
            _as_float(state.get("mastery")) < PREREQUISITE_MASTERY_THRESHOLD
            or _as_float(state.get("confidence")) < PREREQUISITE_CONFIDENCE_THRESHOLD
        ):
            blocked.append(prerequisite_id)
    return not blocked, blocked


def _objective_score(
    objective: dict[str, Any],
    state: dict[str, Any],
    *,
    eligible: bool,
    goal_relevance: float,
    now: datetime | None,
) -> tuple[float, dict[str, float]]:
    mastery = _as_float(state.get("mastery"))
    confidence = _as_float(state.get("confidence"))
    importance = _as_float(objective.get("importance"), 0.5)
    uncertainty = 1.0 - confidence
    weakness = 1.0 - mastery
    days_since = _days_since(state.get("last_practiced_at"), now)
    spacing = 0.0 if days_since is None else clamp(days_since / 14.0)
    attempts = _as_int(state.get("attempt_count"))
    recent_overpractice_penalty = (
        0.45 if mastery >= MASTERED_MASTERY_THRESHOLD and confidence >= MASTERED_CONFIDENCE_THRESHOLD else 0.0
    )
    if days_since is not None and days_since < 1.0:
        recent_overpractice_penalty += 0.18
    # Ineligible objectives are never preferred while their prerequisite is
    # unresolved.  A prerequisite objective will be present as its own
    # candidate and can therefore win normally.
    eligibility_factor = 1.0 if eligible else 0.0
    components = {
        "weakness": 0.44 * weakness,
        "uncertainty": 0.24 * uncertainty,
        "importance": 0.14 * importance,
        "goal_relevance": 0.10 * clamp(goal_relevance, 0.0, 1.0),
        "spacing": 0.08 * spacing,
        "recent_overpractice_penalty": recent_overpractice_penalty,
        "attempt_penalty": min(0.08, attempts * 0.01)
        if mastery >= MASTERED_MASTERY_THRESHOLD
        else 0.0,
    }
    score = sum(components.values()) - components["recent_overpractice_penalty"] - components[
        "attempt_penalty"
    ]
    return score * eligibility_factor, components


def select_objective(
    objectives: list[dict[str, Any]],
    states: dict[int, dict[str, Any]],
    relations: list[dict[str, Any]],
    *,
    goal_relevance: dict[int, float] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Select the next objective and return an explainable decision record."""
    goal_relevance = goal_relevance or {}
    active = [item for item in objectives if item.get("status", "active") == "active"]
    if not active:
        return None

    candidates: list[dict[str, Any]] = []
    for objective in active:
        objective_id = int(objective["id"])
        state = _state_for(objective, states)
        is_eligible, blocked = prerequisite_eligibility(objective_id, relations, states)
        score, components = _objective_score(
            objective,
            state,
            eligible=is_eligible,
            goal_relevance=goal_relevance.get(objective_id, 0.5),
            now=now,
        )
        candidates.append(
            {
                "objective": objective,
                "state": state,
                "score": round(score, 6),
                "components": components,
                "eligible": is_eligible,
                "blocked_by": blocked,
            }
        )

    eligible_candidates = [candidate for candidate in candidates if candidate["eligible"]]

    def recently_validated(candidate: dict[str, Any]) -> bool:
        days_since = _days_since(candidate["state"].get("last_practiced_at"), now)
        return (
            _as_float(candidate["state"].get("mastery")) >= MASTERED_MASTERY_THRESHOLD
            and _as_float(candidate["state"].get("confidence")) >= MASTERED_CONFIDENCE_THRESHOLD
            and (days_since is None or days_since < 7.0)
        )

    usable = [
        candidate
        for candidate in eligible_candidates
        if not recently_validated(candidate)
    ]
    if not usable:
        # A mastered, high-confidence objective with no review due date is a
        # deliberate stop condition.  Continuing to serve it would turn
        # unnecessary practice into the default policy behavior.
        if eligible_candidates and all(recently_validated(candidate) for candidate in eligible_candidates):
            return None
    if not usable:
        # This can only happen when a malformed graph contains a cycle.  Do
        # not jump through a prerequisite; choose the least-blocked node so
        # the API can explain the graph problem to the user.
        usable = sorted(candidates, key=lambda item: (len(item["blocked_by"]), item["score"]))[:1]
    selected = max(
        usable,
        key=lambda item: (
            item["score"],
            _as_float(item["objective"].get("importance"), 0.5),
            -int(item["objective"]["id"]),
        ),
    )
    objective = selected["objective"]
    state = selected["state"]
    reasons: list[str] = []
    if selected["blocked_by"]:
        reasons.append("前置目标尚未达到可练习阈值")
    if _as_float(state.get("mastery")) < 0.45:
        reasons.append("当前掌握度偏低")
    if _as_float(state.get("confidence")) < 0.45:
        reasons.append("学习证据仍然不足，置信度偏低")
    if selected["components"]["importance"] >= 0.10:
        reasons.append("课程重要性较高")
    if not reasons:
        reasons.append("根据最近学习证据保持间隔复习")
    return {
        "objective": objective,
        "state": state,
        "score": selected["score"],
        "reason": "；".join(reasons),
        "reasons": reasons,
        "components": selected["components"],
        "blocked_by": selected["blocked_by"],
        "policy_version": POLICY_VERSION,
    }


def select_action(
    objective: dict[str, Any],
    state: dict[str, Any],
    misconceptions: list[dict[str, Any]] | None = None,
    *,
    days_since_practice: float | None = None,
) -> dict[str, Any]:
    """Choose how to learn one already-selected objective."""
    misconceptions = [item for item in (misconceptions or []) if not item.get("resolved_at")]
    mastery = _as_float(state.get("mastery"))
    confidence = _as_float(state.get("confidence"))
    if misconceptions:
        misconception = misconceptions[0]
        return {
            "action_type": "misconception_repair",
            "desired_difficulty": "easy" if mastery < 0.45 else "medium",
            "reason": f"最近发现错误模式：{misconception.get('description') or misconception.get('code')}",
            "misconception": misconception,
            "expected_minutes": 8,
        }
    if mastery < 0.30:
        return {
            "action_type": "explain",
            "desired_difficulty": "easy",
            "reason": "当前掌握度较低，先建立可解释的基础模型",
            "expected_minutes": 8,
        }
    if mastery >= MASTERED_MASTERY_THRESHOLD and confidence < 0.55:
        return {
            "action_type": "verify_mastery",
            "desired_difficulty": "medium",
            "reason": "掌握度看起来较高，但证据数量不足，需要一次验证",
            "expected_minutes": 6,
        }
    if mastery >= 0.65 and days_since_practice is not None and days_since_practice >= 7:
        return {
            "action_type": "review",
            "desired_difficulty": "medium",
            "reason": "距离上次有效证据已经超过一周，安排间隔复习",
            "expected_minutes": 6,
        }
    return {
        "action_type": "practice",
        "desired_difficulty": "hard" if mastery >= 0.65 else "medium",
        "reason": "通过一题可验证练习补充当前学习证据",
        "expected_minutes": 8,
    }


def choose_next_action(
    objectives: list[dict[str, Any]],
    states: dict[int, dict[str, Any]],
    relations: list[dict[str, Any]],
    misconceptions_by_objective: dict[int, list[dict[str, Any]]] | None = None,
    *,
    goal_relevance: dict[int, float] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    decision = select_objective(
        objectives,
        states,
        relations,
        goal_relevance=goal_relevance,
        now=now,
    )
    if decision is None:
        return None
    objective_id = int(decision["objective"]["id"])
    state = decision["state"]
    action = select_action(
        decision["objective"],
        state,
        (misconceptions_by_objective or {}).get(objective_id, []),
        days_since_practice=_days_since(state.get("last_practiced_at"), now),
    )
    return {
        **decision,
        **action,
        "objective_id": objective_id,
        "priority": decision["score"],
        "policy_version": POLICY_VERSION,
    }


def confidence_components(
    prior: dict[str, Any] | None,
    evidence_history: list[dict[str, Any]] | None,
    *,
    current_score: float,
    current_difficulty: str,
    current_question_id: int | None = None,
    current_coverage_type: str | None = None,
    current_source_type: str | None = None,
    now: datetime | None = None,
) -> dict[str, float]:
    """Estimate confidence from quantity, consistency, quality, diversity and recency.

    This is intentionally a small inspectable estimator, not a second mastery
    model.  Contradictory scores reduce consistency even when the evidence
    count keeps growing.
    """
    prior = prior or {}
    history = list(evidence_history or [])[-CONFIDENCE_HISTORY_LIMIT:]
    history.append(
        {
            "score": current_score,
            "difficulty": current_difficulty,
            "question_id": current_question_id,
            "coverage_type": current_coverage_type,
            "source_type": current_source_type,
            "created_at": (now or datetime.now(timezone.utc)).isoformat(),
        }
    )
    scores = [_as_float(item.get("score")) for item in history]
    attempts = max(_as_int(prior.get("attempt_count")) + 1, len(scores))
    quantity = 1.0 - exp(-attempts / 4.0)
    if len(scores) <= 1:
        consistency = 0.35
    else:
        mean = sum(scores) / len(scores)
        variance = sum((score - mean) ** 2 for score in scores) / len(scores)
        transitions = sum(
            1
            for previous, current in zip(scores, scores[1:])
            if (previous >= 0.7) != (current >= 0.7)
        )
        variance_component = 1.0 - min(1.0, variance * 5.0)
        stability_component = 1.0 - min(1.0, transitions / max(len(scores) - 1, 1))
        consistency = clamp(variance_component * 0.55 + stability_component * 0.45)
    quality_weights = {
        "deterministic-exact": 0.95,
        "llm-rubric": 0.92,
        "deterministic-rubric-fallback": 0.70,
        "deterministic-keyword": 0.58,
    }
    quality = sum(
        quality_weights.get(str(item.get("grader_type") or ""), 0.72)
        for item in history
    ) / max(len(history), 1)
    if current_source_type:
        source_types = {str(item.get("source_type") or "") for item in history} | {current_source_type}
    else:
        source_types = {str(item.get("source_type") or "") for item in history}
    question_ids = {int(item["question_id"]) for item in history if item.get("question_id")}
    if current_question_id:
        question_ids.add(int(current_question_id))
    coverage_types = {str(item.get("coverage_type") or "") for item in history if item.get("coverage_type")}
    if current_coverage_type:
        coverage_types.add(current_coverage_type)
    difficulty_types = {str(item.get("difficulty") or "") for item in history if item.get("difficulty")}
    diversity = clamp(
        min(1.0, len(question_ids) / 4.0) * 0.45
        + min(1.0, len(coverage_types) / 3.0) * 0.25
        + min(1.0, len(difficulty_types) / 3.0) * 0.15
        + min(1.0, len(source_types) / 2.0) * 0.15
    )
    ages = [_days_since(item.get("created_at"), now) for item in history]
    recent_days = [age for age in ages if age is not None]
    recency = clamp(1.0 - (sum(recent_days) / len(recent_days)) / 30.0) if recent_days else 0.65
    confidence = clamp(
        quantity * 0.35
        + consistency * 0.30
        + diversity * 0.18
        + quality * 0.12
        + recency * 0.05
    )
    return {
        "quantity": round(quantity, 4),
        "consistency": round(consistency, 4),
        "diversity": round(diversity, 4),
        "quality": round(clamp(quality), 4),
        "recency": round(recency, 4),
        "confidence": round(confidence, 4),
    }


def update_student_state(
    prior: dict[str, Any] | None,
    *,
    score: float,
    difficulty: str = "medium",
    now: datetime | None = None,
    evidence_history: list[dict[str, Any]] | None = None,
    question_id: int | None = None,
    coverage_type: str | None = None,
    source_type: str | None = None,
    grader_type: str | None = None,
) -> dict[str, Any]:
    """Apply one evaluated evidence item using a bounded BKT-inspired update.

    The calculation remains deliberately inspectable: guess/slip/learn are
    fixed parameters, and the final change is capped so one answer cannot
    teleport a learner to mastery.
    """
    prior = prior or {}
    current_mastery = _as_float(prior.get("mastery"))
    current_confidence = _as_float(prior.get("confidence"))
    normalized_score = clamp(score)
    guess = 0.20 if difficulty == "easy" else 0.12 if difficulty == "medium" else 0.08
    slip = 0.12 if difficulty == "easy" else 0.10 if difficulty == "medium" else 0.08
    learn = 0.10 if difficulty == "easy" else 0.12 if difficulty == "medium" else 0.14
    p_correct = current_mastery * (1 - slip) + (1 - current_mastery) * guess
    if normalized_score >= 0.5:
        posterior = current_mastery * (1 - slip) / max(p_correct, 1e-6)
        target = posterior + (1 - posterior) * learn
    else:
        p_wrong = max(1 - p_correct, 1e-6)
        posterior = current_mastery * slip / p_wrong
        target = posterior * (1 - learn * 0.35)
    partial = normalized_score if 0.0 < normalized_score < 1.0 else None
    if partial is not None:
        target = target * (0.5 + partial) + current_mastery * (0.5 - partial)
    delta = max(-MAX_MASTERY_STEP, min(MAX_MASTERY_STEP, target - current_mastery))
    mastery = round(clamp(current_mastery + delta), 4)

    attempts = _as_int(prior.get("attempt_count")) + 1
    correct = _as_int(prior.get("correct_count")) + (1 if normalized_score >= 0.7 else 0)
    incorrect = _as_int(prior.get("incorrect_count")) + (1 if normalized_score < 0.7 else 0)
    success_streak = _as_int(prior.get("success_streak")) + 1 if normalized_score >= 0.7 else 0
    failure_streak = _as_int(prior.get("failure_streak")) + 1 if normalized_score < 0.7 else 0
    components = confidence_components(
        prior,
        [
            {
                **item,
                "grader_type": item.get("grader_type") or "deterministic-keyword",
            }
            for item in (evidence_history or [])
        ],
        current_score=normalized_score,
        current_difficulty=difficulty,
        current_question_id=question_id,
        current_coverage_type=coverage_type,
        current_source_type=source_type,
        now=now,
    )
    if grader_type:
        components["quality"] = round(
            clamp(components["quality"] + (0.08 if grader_type in {"llm-rubric", "deterministic-exact"} else 0.0)),
            4,
        )
        components["confidence"] = round(
            clamp(
                components["quantity"] * 0.35
                + components["consistency"] * 0.30
                + components["diversity"] * 0.18
                + components["quality"] * 0.12
                + components["recency"] * 0.05
            ),
            4,
        )
    confidence = components["confidence"]
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    if mastery >= MASTERED_MASTERY_THRESHOLD and confidence >= MASTERED_CONFIDENCE_THRESHOLD:
        state = "mastered"
    elif mastery < 0.35:
        state = "weak"
    elif mastery < 0.65:
        state = "learning"
    else:
        state = "progressing"
    reason = (
        f"BKT-inspired update: prior={current_mastery:.3f}, score={normalized_score:.3f}, "
        f"difficulty={difficulty}, learn={learn:.2f}, guess={guess:.2f}, slip={slip:.2f}, "
        f"bounded_delta={delta:+.3f}, confidence_components={components}"
    )
    return {
        "mastery": mastery,
        "confidence": confidence,
        "attempt_count": attempts,
        "correct_count": correct,
        "incorrect_count": incorrect,
        "success_streak": success_streak,
        "failure_streak": failure_streak,
        "state": state,
        "model_version": STATE_MODEL_VERSION,
        "last_practiced_at": timestamp,
        "last_success_at": timestamp if normalized_score >= 0.7 else prior.get("last_success_at"),
        "last_failure_at": timestamp if normalized_score < 0.7 else prior.get("last_failure_at"),
        "mastery_before": round(current_mastery, 4),
        "confidence_before": round(current_confidence, 4),
        "quantity_confidence": components["quantity"],
        "consistency_confidence": components["consistency"],
        "diversity_confidence": components["diversity"],
        "quality_confidence": components["quality"],
        "recency_confidence": components["recency"],
        "update_reason": reason,
    }


__all__ = [
    "POLICY_VERSION",
    "STATE_MODEL_VERSION",
    "choose_next_action",
    "clamp",
    "confidence_components",
    "prerequisite_eligibility",
    "select_action",
    "select_objective",
    "update_student_state",
]
