"""Application services for the evidence-backed Adaptive Tutor."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.llm.objective_extractor import extract_learning_objectives
from app.modules.adaptive import repository
from app.modules.adaptive.policy import choose_next_action, update_student_state
from app.modules.courses.service import get_user_course
from app.modules.materials import repository as material_repository
from app.modules.materials.service import list_user_course_materials

DETERMINISTIC_GRADER_TYPE = "deterministic-keyword"
DETERMINISTIC_GRADER_VERSION = "keyword-overlap-v1"


def _require_course(user_id: int, course_id: int) -> dict[str, Any]:
    return get_user_course(user_id, course_id)


def _db_datetime(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _db_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "last_practiced_at": _db_datetime(state.get("last_practiced_at")),
        "last_success_at": _db_datetime(state.get("last_success_at")),
        "last_failure_at": _db_datetime(state.get("last_failure_at")),
    }


def _public_question(question: dict[str, Any] | None) -> dict[str, Any] | None:
    if question is None:
        return None
    visible = dict(question)
    for key in ("answer", "rubric"):
        visible.pop(key, None)
    visible.pop("generation_context_json", None)
    return visible


def _public_action(cursor, user_id: int, action: dict[str, Any] | None) -> dict[str, Any] | None:
    if action is None:
        return None
    visible = dict(action)
    if visible.get("question_id"):
        question = repository.get_question(
            cursor,
            user_id,
            int(visible["course_id"]),
            int(visible["question_id"]),
        )
        visible["question"] = _public_question(question)
    else:
        visible["question"] = None
    visible["priority"] = float(visible.get("priority") or 0)
    visible["objective_id"] = int(visible["objective_id"])
    if visible.get("question_id"):
        visible["question_id"] = int(visible["question_id"])
    return visible


def _policy_inputs(cursor, user_id: int, course_id: int) -> tuple[list[dict], list[dict], dict[int, list[dict]]]:
    objectives = repository.list_objectives(cursor, user_id, course_id)
    relations = repository.list_relations(cursor, user_id, course_id)
    misconceptions = repository.list_misconceptions(cursor, user_id, course_id)
    return objectives, relations, misconceptions


def _ensure_next_action(cursor, user_id: int, course_id: int) -> dict[str, Any] | None:
    active = repository.get_active_action(cursor, user_id, course_id)
    if active is not None:
        return _public_action(cursor, user_id, repository.get_action(cursor, user_id, int(active["id"])))
    objectives, relations, misconceptions = _policy_inputs(cursor, user_id, course_id)
    states = {int(item["id"]): item for item in objectives}
    decision = choose_next_action(objectives, states, relations, misconceptions)
    if decision is None:
        return None
    question = None
    if decision["action_type"] in {
        "practice",
        "verify_mastery",
        "review",
        "misconception_repair",
        "transfer",
    }:
        question = repository.find_best_question(
            cursor,
            user_id=user_id,
            course_id=course_id,
            objective_id=int(decision["objective_id"]),
            desired_difficulty=str(decision.get("desired_difficulty") or "medium"),
            coverage_types=[
                "scenario",
                "transfer",
                "diagnostic",
                "review",
                "direct",
            ],
        )
        decision["question_id"] = int(question["id"]) if question else None
    decision["reason"] = f"{decision.get('reason', '')}；{decision.get('action_type')}"
    action = repository.create_action(
        cursor,
        user_id=user_id,
        course_id=course_id,
        decision=decision,
    )
    return _public_action(cursor, user_id, repository.get_action(cursor, user_id, int(action["id"])))


def _grade_answer(question: dict[str, Any], response: str) -> tuple[float, str]:
    answer = str(question.get("answer") or "").strip()
    normalized_response = str(response or "").strip().lower()
    normalized_answer = answer.lower()
    if not normalized_response:
        return 0.0, "回答为空，尚未形成可验证证据。"
    if normalized_answer and normalized_answer in normalized_response:
        return 0.95, "回答覆盖了参考答案的核心表述。"

    def tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]+", value.lower())
            if len(token) > 1
        }

    expected = tokens(answer)
    actual = tokens(normalized_response)
    if not expected:
        return (0.6 if len(normalized_response) >= 12 else 0.25), "已收到回答，参考答案缺少可拆分的关键词。"
    # Chinese text often has no whitespace, so exact token-set intersection
    # would undercount a response that contains every expected phrase.
    matched = sum(1 for token in expected if token in normalized_response or token in actual)
    overlap = matched / len(expected)
    score = 0.15 + overlap * 0.78
    score = max(0.0, min(0.95, score))
    if overlap >= 0.7:
        feedback = "回答覆盖了大部分关键依据，可以继续练习场景迁移。"
    elif overlap >= 0.35:
        feedback = "回答触及部分关键依据，还需要补充条件、判断过程或边界。"
    else:
        feedback = "回答没有覆盖参考答案中的主要判断依据。"
    return round(score, 4), feedback


def _record_evidence(
    cursor,
    *,
    user_id: int,
    course_id: int,
    objective_id: int,
    source_type: str,
    response: str,
    question: dict[str, Any] | None,
    action_id: int | None,
    misconception_code: str | None = None,
    misconception_text: str | None = None,
    misconception_confidence: float | None = None,
) -> dict[str, Any]:
    if question is None:
        score, feedback = 0.55, "完成了讲解后的自检，系统将其作为较弱的 tutor_check 证据。"
        question_id = None
        difficulty = "easy"
        attempt_id = None
    else:
        score, feedback = _grade_answer(question, response)
        question_id = int(question["id"])
        difficulty = str(question.get("difficulty") or "medium")
        attempt_id = repository.create_question_attempt(
            cursor,
            user_id=user_id,
            course_id=course_id,
            question_id=question_id,
            action_id=action_id,
            response=response,
            score=score,
            grader_type=DETERMINISTIC_GRADER_TYPE,
            grader_version=DETERMINISTIC_GRADER_VERSION,
            feedback=feedback,
        )
    if score < 0.45 and not misconception_code:
        misconception_code = "missing_key_evidence"
        misconception_text = misconception_text or "回答未覆盖该目标要求的关键判断依据。"
        misconception_confidence = misconception_confidence or 0.65
    prior = repository.get_state(cursor, user_id, course_id, objective_id)
    active_misconceptions = repository.list_misconceptions(
        cursor, user_id, course_id
    ).get(objective_id, [])
    update = update_student_state(
        prior,
        score=score,
        difficulty=difficulty,
    )
    repository.save_state(cursor, user_id, course_id, objective_id, _db_state(update))
    evidence_id = repository.create_learning_evidence(
        cursor,
        user_id=user_id,
        course_id=course_id,
        objective_id=objective_id,
        source_type=source_type,
        question_id=question_id,
        attempt_id=attempt_id,
        response=response,
        score=score,
        difficulty=difficulty,
        grader_type=DETERMINISTIC_GRADER_TYPE,
        grader_version=DETERMINISTIC_GRADER_VERSION,
        misconception_code=misconception_code,
        misconception_text=misconception_text,
        misconception_confidence=misconception_confidence,
        update=update,
    )
    if misconception_code and misconception_text:
        repository.upsert_misconception(
            cursor,
            user_id=user_id,
            course_id=course_id,
            objective_id=objective_id,
            code=misconception_code,
            description=misconception_text,
            confidence=misconception_confidence or 0.5,
        )
    elif score >= 0.7 and active_misconceptions:
        repository.resolve_misconceptions(
            cursor,
            user_id=user_id,
            course_id=course_id,
            objective_id=objective_id,
        )
    if action_id is not None:
        repository.complete_action(cursor, user_id, action_id)
    return {
        "evidence_id": evidence_id,
        "objective_id": objective_id,
        "question_id": question_id,
        "attempt_id": attempt_id,
        "score": score,
        "feedback": feedback,
        "misconception_code": misconception_code,
        "misconception_text": misconception_text,
        "state": {
            key: update[key]
            for key in (
                "mastery",
                "confidence",
                "attempt_count",
                "correct_count",
                "incorrect_count",
                "success_streak",
                "failure_streak",
                "state",
            )
        },
        "update_reason": update["update_reason"],
    }


def get_overview(user_id: int, course_id: int) -> dict[str, Any]:
    course = _require_course(user_id, course_id)
    with get_cursor() as cursor:
        objectives, relations, misconceptions = _policy_inputs(cursor, user_id, course_id)
        evidence = repository.list_objective_evidence(cursor, user_id, course_id)
        latest_build = repository.latest_curriculum_build(cursor, user_id, course_id)
        counts = repository.course_counts(cursor, user_id, course_id)
        next_action = _ensure_next_action(cursor, user_id, course_id)
    status = latest_build["status"] if latest_build else "pending"
    if status not in {"ready", "degraded", "failed"}:
        status = "pending"
    return {
        "course": course,
        "curriculum": {
            "status": status,
            "latest_build": latest_build,
            "objective_count": len(objectives),
        },
        "next_action": next_action,
        "objectives": objectives,
        "relations": relations,
        "misconceptions": misconceptions,
        "evidence_by_objective": evidence,
        "counts": counts,
    }


def get_next_action(user_id: int, course_id: int) -> dict[str, Any] | None:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        return _ensure_next_action(cursor, user_id, course_id)


def get_progress(user_id: int, course_id: int) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        objectives = repository.list_objectives(cursor, user_id, course_id)
        relations = repository.list_relations(cursor, user_id, course_id)
        misconceptions = repository.list_misconceptions(cursor, user_id, course_id)
        prerequisites_by_target: dict[int, list[dict[str, Any]]] = {}
        dependents_by_source: dict[int, list[dict[str, Any]]] = {}
        for relation in relations:
            if relation["relation_type"] != "prerequisite":
                continue
            prerequisites_by_target.setdefault(int(relation["target_objective_id"]), []).append(relation)
            dependents_by_source.setdefault(int(relation["source_objective_id"]), []).append(relation)
        for objective in objectives:
            objective_id = int(objective["id"])
            objective["evidence"] = repository.evidence_for_objective(
                cursor, user_id, course_id, objective_id, limit=8
            )
            objective["misconceptions"] = misconceptions.get(objective_id, [])
            objective["prerequisites"] = prerequisites_by_target.get(objective_id, [])
            objective["dependents"] = dependents_by_source.get(objective_id, [])
    groups = {"mastered": 0, "progressing": 0, "learning": 0, "weak": 0, "unknown": 0}
    for item in objectives:
        groups[str(item.get("state") or "unknown")] = groups.get(str(item.get("state") or "unknown"), 0) + 1
    return {
        "course_id": course_id,
        "objectives": objectives,
        "relations": relations,
        "status_counts": groups,
    }


def get_objective_detail(user_id: int, course_id: int, objective_id: int) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        objectives = [
            item
            for item in repository.list_objectives(cursor, user_id, course_id)
            if int(item["id"]) == int(objective_id)
        ]
        if not objectives:
            raise AppError("学习目标不存在或无访问权限", 404, "OBJECTIVE_NOT_FOUND")
        objective = objectives[0]
        objective["evidence"] = repository.evidence_for_objective(
            cursor, user_id, course_id, int(objective_id), limit=50
        )
        objective["misconceptions"] = repository.list_misconceptions(
            cursor, user_id, course_id
        ).get(int(objective_id), [])
        objective["prerequisites"] = [
            relation
            for relation in repository.list_relations(cursor, user_id, course_id)
            if relation["relation_type"] == "prerequisite"
            and relation["target_objective_id"] == int(objective_id)
        ]
        objective["dependents"] = [
            relation
            for relation in repository.list_relations(cursor, user_id, course_id)
            if relation["relation_type"] == "prerequisite"
            and relation["source_objective_id"] == int(objective_id)
        ]
    return objective


def get_sources(user_id: int, course_id: int) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        questions = repository.list_questions(cursor, user_id, course_id)
        counts = repository.course_counts(cursor, user_id, course_id)
    return {
        "materials": list_user_course_materials(user_id, course_id),
        "questions": questions,
        "counts": counts,
    }


def add_question_bank(user_id: int, course_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    _require_course(user_id, course_id)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with get_cursor() as cursor:
        objective_rows = repository.list_objectives(cursor, user_id, course_id)
        allowed_objectives = {int(item["id"]) for item in objective_rows}
        for item in items:
            content = str(item["content"]).strip()
            objective_ids = sorted({int(value) for value in item.get("objective_ids") or []})
            invalid = [value for value in objective_ids if value not in allowed_objectives]
            if invalid:
                raise AppError(
                    "题目关联了不属于当前课程的学习目标",
                    422,
                    "QUESTION_OBJECTIVE_INVALID",
                    {"objective_ids": invalid},
                )
            source_material_id = item.get("source_material_id")
            if source_material_id is not None:
                material = material_repository.get_material(cursor, int(source_material_id), user_id)
                if material is None or int(material["course_id"]) != int(course_id):
                    raise AppError(
                        "题目来源资料不属于当前课程",
                        422,
                        "QUESTION_SOURCE_MATERIAL_INVALID",
                    )
            if repository.question_exists(cursor, user_id, course_id, content):
                skipped.append({"content": content, "reason": "duplicate"})
                continue
            if not objective_ids and item.get("source_type") != "user_upload":
                raise AppError("非用户题库题必须先关联 Learning Objective", 422, "QUESTION_OBJECTIVE_REQUIRED")
            question = repository.create_question(
                cursor,
                user_id=user_id,
                course_id=course_id,
                item=item,
                objective_ids=objective_ids,
                generation_context=item.get("generation_context"),
            )
            created.append(_public_question(question) or {"id": question["id"]})
    return {"created": created, "skipped": skipped, "created_count": len(created)}


def start_action(user_id: int, action_id: int) -> dict[str, Any]:
    with get_cursor() as cursor:
        action = repository.get_action(cursor, user_id, action_id)
        if action is None:
            raise AppError("学习动作不存在或无访问权限", 404, "LEARNING_ACTION_NOT_FOUND")
        if action["status"] == "queued":
            action = repository.start_action(cursor, user_id, action_id) or action
        return _public_action(cursor, user_id, action) or action


def submit_action(user_id: int, action_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    with get_cursor() as cursor:
        action = repository.get_action(cursor, user_id, action_id)
        if action is None:
            raise AppError("学习动作不存在或无访问权限", 404, "LEARNING_ACTION_NOT_FOUND")
        if action["status"] == "completed":
            raise AppError("该学习动作已经完成", 409, "LEARNING_ACTION_COMPLETED")
        if action["status"] == "queued":
            action = repository.start_action(cursor, user_id, action_id) or action
        question = None
        if action.get("question_id"):
            question = repository.get_question(
                cursor,
                user_id,
                int(action["course_id"]),
                int(action["question_id"]),
            )
            if question is None:
                raise AppError("学习动作关联的题目不存在", 409, "LEARNING_QUESTION_MISSING")
        result = _record_evidence(
            cursor,
            user_id=user_id,
            course_id=int(action["course_id"]),
            objective_id=int(action["objective_id"]),
            source_type="practice" if question else "tutor_check",
            response=payload["response"],
            question=question,
            action_id=action_id,
            misconception_code=payload.get("misconception_code"),
            misconception_text=payload.get("misconception_text"),
            misconception_confidence=payload.get("misconception_confidence"),
        )
        result["completed_action"] = _public_action(cursor, user_id, repository.get_action(cursor, user_id, action_id))
        result["next_action"] = _ensure_next_action(cursor, user_id, int(action["course_id"]))
        return result


def start_diagnostic(user_id: int, course_id: int, question_count: int = 6) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        objectives = repository.list_objectives(cursor, user_id, course_id)
        selected: list[dict[str, Any]] = []
        seen_question_ids: set[int] = set()
        for objective in sorted(objectives, key=lambda item: (-float(item.get("importance") or 0), int(item["id"]))):
            question = repository.find_best_question(
                cursor,
                user_id=user_id,
                course_id=course_id,
                objective_id=int(objective["id"]),
                desired_difficulty="medium",
                coverage_types=["diagnostic", "scenario", "direct"],
            )
            if question and int(question["id"]) not in seen_question_ids:
                selected.append(_public_question(question) or {})
                seen_question_ids.add(int(question["id"]))
            if len(selected) >= question_count:
                break
    return {"course_id": course_id, "questions": selected, "question_count": len(selected)}


def submit_diagnostic(user_id: int, course_id: int, answers: list[dict[str, Any]]) -> dict[str, Any]:
    _require_course(user_id, course_id)
    results: list[dict[str, Any]] = []
    with get_cursor() as cursor:
        for answer in answers:
            question = repository.get_question(cursor, user_id, course_id, int(answer["question_id"]))
            if question is None:
                raise AppError("诊断题不存在或无访问权限", 404, "DIAGNOSTIC_QUESTION_NOT_FOUND")
            objectives = question.get("objectives") or []
            if not objectives:
                continue
            result = _record_evidence(
                cursor,
                user_id=user_id,
                course_id=course_id,
                objective_id=int(objectives[0]["objective_id"]),
                source_type="diagnostic",
                response=answer["response"],
                question=question,
                action_id=None,
            )
            results.append(result)
        next_action = _ensure_next_action(cursor, user_id, course_id)
    return {"results": results, "next_action": next_action, "count": len(results)}


def rebuild_curriculum(user_id: int, course_id: int, material_id: int | None = None) -> dict[str, Any]:
    course = _require_course(user_id, course_id)
    with get_cursor() as cursor:
        materials = material_repository.list_course_materials(cursor, course_id, user_id)
        candidates = [item for item in materials if item.get("processing_status") == "ready"]
        if material_id is not None:
            candidates = [item for item in candidates if int(item["id"]) == int(material_id)]
        if not candidates:
            raise AppError("没有可用于构建 Curriculum 的已就绪资料", 409, "CURRICULUM_MATERIAL_NOT_READY")
        material = candidates[0]
        chunks = material_repository.get_material_chunks(cursor, int(material["id"]), user_id)
    extraction = extract_learning_objectives(
        course["name"],
        material["title"],
        chunks,
        user_id=user_id,
    )
    with get_cursor() as cursor:
        return repository.persist_curriculum(
            cursor,
            user_id=user_id,
            course_id=course_id,
            material_id=int(material["id"]),
            chunks=chunks,
            extraction=extraction,
        )


__all__ = [
    "add_question_bank",
    "get_next_action",
    "get_objective_detail",
    "get_overview",
    "get_progress",
    "get_sources",
    "rebuild_curriculum",
    "start_action",
    "start_diagnostic",
    "submit_action",
    "submit_diagnostic",
]
