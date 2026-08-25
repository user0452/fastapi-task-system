"""Application services for the evidence-backed Adaptive Tutor."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.llm.agent_runtime import invoke_agent_content
from app.integrations.llm.model_provider import get_llm
from app.integrations.llm.objective_extractor import extract_learning_objectives
from app.modules.adaptive import repository
from app.modules.adaptive.grader import grade_response
from app.modules.adaptive.objective_tagger import align_question_to_objectives
from app.modules.adaptive.policy import choose_next_action, update_student_state
from app.modules.adaptive.question_generator import generate_grounded_question
from app.modules.adaptive.question_import import normalize_and_deduplicate, parse_question_bank
from app.modules.courses.service import get_user_course
from app.modules.materials import repository as material_repository
from app.modules.materials.service import (
    get_course_evidence_context,
    list_user_course_materials,
    search_course_materials,
)

DETERMINISTIC_GRADER_TYPE = "deterministic-rubric-fallback"
DETERMINISTIC_GRADER_VERSION = "deterministic-rubric-fallback-v2"


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


def _confidence_explanation(state: dict[str, Any]) -> str:
    attempts = int(state.get("attempt_count") or 0)
    components = {
        "数量": float(state.get("quantity_confidence") or 0),
        "一致性": float(state.get("consistency_confidence") or 0),
        "题型/来源多样性": float(state.get("diversity_confidence") or 0),
        "评分质量": float(state.get("quality_confidence") or 0),
        "近期性": float(state.get("recency_confidence") or 0),
    }
    strongest = "、".join(
        f"{name}{value:.0%}" for name, value in components.items()
    )
    if attempts == 0:
        return "还没有 Learning Evidence，当前置信度为 0。"
    return f"基于 {attempts} 条 Evidence；置信度拆分为 {strongest}。"


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
        recent_questions = repository.recent_questions_for_objective(
            cursor,
            user_id,
            course_id,
            int(decision["objective_id"]),
        )
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
            action_type=str(decision.get("action_type") or "practice"),
            recent_question_ids={
                int(item["id"])
                for item in recent_questions[:2]
                if item.get("id") is not None
            },
            recent_question_contents=[str(item.get("content") or "") for item in recent_questions[:3]],
        )
        if question is None:
            objective = decision["objective"]
            evidence_rows = repository.list_objective_evidence(cursor, user_id, course_id).get(
                int(decision["objective_id"]), []
            )
            evidence_blocks = [
                {
                    "material_id": item.get("material_id"),
                    "material_title": item.get("material_title"),
                    "heading_path": item.get("heading_path"),
                    "page_start": item.get("page_number"),
                    "page_end": item.get("page_number"),
                    "chunk_ids": [int(item["chunk_id"])],
                    "evidence_text": f"[chunk_id={item['chunk_id']}] {item.get('snippet') or ''}",
                }
                for item in evidence_rows[:5]
            ]
            generated = generate_grounded_question(
                objective=objective,
                evidence_blocks=evidence_blocks,
                difficulty=str(decision.get("desired_difficulty") or "medium"),
                recent_questions=recent_questions,
                user_id=user_id,
            )
            if generated is not None:
                question = repository.create_question(
                    cursor,
                    user_id=user_id,
                    course_id=course_id,
                    item={
                        **generated,
                        "source_type": "generated",
                        "model": (generated.get("generation_context") or {}).get("model"),
                        "prompt_version": (generated.get("generation_context") or {}).get("prompt_version"),
                        "raw_provenance": {"evidence_blocks": evidence_blocks},
                    },
                    objective_ids=[int(decision["objective_id"])],
                    generation_context=generated.get("generation_context"),
                )
            else:
                decision["action_type"] = "explain"
                decision["reason"] = (
                    f"{decision.get('reason', '')}；当前没有通过验证的题目，先进行基于资料的讲解"
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
    grade_result: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    action_type: str | None = None,
) -> dict[str, Any]:
    if idempotency_key:
        existing = repository.get_evidence_by_idempotency(
            cursor,
            user_id,
            course_id,
            source_type,
            idempotency_key,
        )
        if existing is not None:
            return {
                "idempotent": True,
                "evidence_id": int(existing["id"]),
                "objective_id": int(existing["objective_id"]),
                "question_id": existing.get("question_id"),
                "attempt_id": existing.get("attempt_id"),
                "score": float(existing.get("score") or 0),
                "feedback": "这次提交已经记录过，返回原 Evidence。",
                "state": {
                    "mastery": float(existing.get("mastery_after") or 0),
                    "confidence": float(existing.get("confidence_after") or 0),
                },
                "update_reason": existing.get("update_reason"),
                "grader": {
                    "type": existing.get("grader_type"),
                    "version": existing.get("grader_version"),
                    "model": existing.get("grader_model"),
                    "prompt_version": existing.get("grader_prompt_version"),
                },
            }
    objective = next(
        (
            item
            for item in repository.list_objectives(cursor, user_id, course_id)
            if int(item["id"]) == int(objective_id)
        ),
        {"id": objective_id},
    )
    if question is None:
        if grade_result is None:
            raise AppError("Tutor Check 必须先经过 Grader", 422, "TUTOR_CHECK_NOT_GRADED")
        score = float(grade_result.get("score") or 0)
        feedback = str(grade_result.get("feedback") or "已完成 Tutor Check。")
        question_id = None
        difficulty = "easy"
        attempt_id = None
    else:
        grade_result = grade_response(
            question,
            response,
            objective=objective,
            user_id=user_id,
        )
        score = float(grade_result.get("score") or 0)
        feedback = str(grade_result.get("feedback") or "已完成评分。")
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
            grader_type=str(grade_result.get("grader_type") or DETERMINISTIC_GRADER_TYPE),
            grader_version=str(grade_result.get("grader_version") or DETERMINISTIC_GRADER_VERSION),
            feedback=feedback,
            grader_model=grade_result.get("grader_model"),
            grader_prompt_version=grade_result.get("grader_prompt_version"),
            metadata={
                "correctness": grade_result.get("correctness"),
                "key_reasoning": grade_result.get("key_reasoning"),
                "completeness": grade_result.get("completeness"),
            },
            idempotency_key=idempotency_key,
        )
    detected = (grade_result or {}).get("misconception") or {}
    misconception_code = misconception_code or detected.get("code")
    misconception_text = misconception_text or detected.get("description")
    misconception_confidence = misconception_confidence or detected.get("confidence")
    if score < 0.45 and not misconception_code:
        misconception_code = "missing_key_evidence"
        misconception_text = "回答未覆盖该目标要求的关键判断依据。"
        misconception_confidence = 0.65
    history = repository.recent_evidence_for_objective(
        cursor,
        user_id,
        course_id,
        objective_id,
        limit=20,
    )
    prior = repository.get_state(cursor, user_id, course_id, objective_id)
    active_misconceptions = repository.list_misconceptions(cursor, user_id, course_id).get(objective_id, [])
    coverage_type = None
    evidence_source_type = source_type
    if question:
        coverage_type = next(
            (
                str(item.get("coverage_type"))
                for item in question.get("objectives") or []
                if int(item.get("objective_id") or 0) == int(objective_id)
            ),
            None,
        )
    update = update_student_state(
        prior,
        score=score,
        difficulty=difficulty,
        evidence_history=history,
        question_id=question_id,
        coverage_type=coverage_type,
        source_type=evidence_source_type,
        grader_type=str((grade_result or {}).get("grader_type") or DETERMINISTIC_GRADER_TYPE),
    )
    repository.save_state(cursor, user_id, course_id, objective_id, _db_state(update))
    grader_type = str((grade_result or {}).get("grader_type") or DETERMINISTIC_GRADER_TYPE)
    grader_version = str((grade_result or {}).get("grader_version") or DETERMINISTIC_GRADER_VERSION)
    evidence_id = repository.create_learning_evidence(
        cursor,
        user_id=user_id,
        course_id=course_id,
        objective_id=objective_id,
        source_type=source_type,
        question_id=question_id,
        attempt_id=attempt_id,
        action_id=action_id,
        idempotency_key=idempotency_key,
        response=response,
        score=score,
        difficulty=difficulty,
        grader_type=grader_type,
        grader_version=grader_version,
        misconception_code=misconception_code,
        misconception_text=misconception_text,
        misconception_confidence=misconception_confidence,
        update=update,
        grader_model=(grade_result or {}).get("grader_model"),
        grader_prompt_version=(grade_result or {}).get("grader_prompt_version"),
        metadata={
            "correctness": (grade_result or {}).get("correctness"),
            "key_reasoning": (grade_result or {}).get("key_reasoning"),
            "completeness": (grade_result or {}).get("completeness"),
            "action_type": action_type,
            "coverage_type": coverage_type,
        },
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
    elif score >= 0.7 and active_misconceptions and action_type == "misconception_repair":
        for misconception in active_misconceptions:
            repository.confirm_misconception(
                cursor,
                user_id=user_id,
                course_id=course_id,
                objective_id=objective_id,
                code=str(misconception["code"]),
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
        "grader": {
            "type": grader_type,
            "version": grader_version,
            "model": (grade_result or {}).get("grader_model"),
            "prompt_version": (grade_result or {}).get("grader_prompt_version"),
            "correctness": (grade_result or {}).get("correctness"),
            "key_reasoning": (grade_result or {}).get("key_reasoning"),
            "completeness": (grade_result or {}).get("completeness"),
        },
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
            objective["confidence_explanation"] = _confidence_explanation(objective)
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
        objective["confidence_explanation"] = _confidence_explanation(objective)
    return objective


def get_sources(user_id: int, course_id: int) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        questions = repository.list_questions(cursor, user_id, course_id)
        import_batches = repository.list_import_batches(cursor, user_id, course_id)
        counts = repository.course_counts(cursor, user_id, course_id)
    return {
        "materials": list_user_course_materials(user_id, course_id),
        "questions": questions,
        "import_batches": import_batches,
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
            tagging = None
            if not objective_ids:
                tagging = align_question_to_objectives(
                    content,
                    item.get("answer"),
                    objective_rows,
                    question_type=str(item.get("question_type") or "short_answer"),
                    coverage_type=str(item.get("coverage_type") or "direct"),
                    user_id=user_id,
                )
                objective_ids = [
                    int(alignment["objective_id"])
                    for alignment in tagging.get("alignments") or []
                ]
            if not objective_ids and item.get("source_type") == "generated":
                raise AppError("生成题必须关联合法 Learning Objective", 422, "QUESTION_OBJECTIVE_REQUIRED")
            question = repository.create_question(
                cursor,
                user_id=user_id,
                course_id=course_id,
                item=item,
                objective_ids=objective_ids,
                generation_context=item.get("generation_context"),
            )
            if tagging:
                question["tagging"] = tagging
            created.append(_public_question(question) or {"id": question["id"]})
        if created:
            # Question Bank changes alter the retrieval side of the policy;
            # queued actions created before the import must be recomputed.
            repository.supersede_queued_actions(cursor, user_id, course_id)
    return {"created": created, "skipped": skipped, "created_count": len(created)}


def _question_import_preview(
    user_id: int,
    course_id: int,
    filename: str,
    content: bytes,
    idempotency_key: str,
) -> dict[str, Any]:
    _require_course(user_id, course_id)
    parsed, duplicate_count = normalize_and_deduplicate(parse_question_bank(content, filename))
    with get_cursor() as cursor:
        objectives = repository.list_objectives(cursor, user_id, course_id)
        preview: list[dict[str, Any]] = []
        matched = 0
        unmatched = 0
        invalid = 0
        for item in parsed:
            payload = item.to_dict()
            payload.update(
                {
                    "source_type": "user_upload",
                    "source_file": filename[:255],
                    "raw_provenance": {
                        **(payload.get("raw_provenance") or {}),
                        "import_filename": filename[:255],
                    },
                }
            )
            if item.parse_status == "invalid":
                invalid += 1
                preview.append(payload)
                continue
            tagging = align_question_to_objectives(
                item.content,
                item.answer,
                objectives,
                question_type=item.question_type,
                coverage_type="scenario" if item.question_type == "scenario" else "direct",
                user_id=user_id,
            )
            alignments = tagging.get("alignments") or []
            payload["objective_ids"] = [int(link["objective_id"]) for link in alignments]
            payload["tagging"] = tagging
            payload["validation"] = {
                "parse_status": item.parse_status,
                "parse_error": item.parse_error,
                "tagger_type": tagging.get("tagger_type"),
            }
            if alignments and item.parse_status == "ready":
                matched += 1
            else:
                unmatched += 1
            preview.append(payload)
        batch = repository.create_import_batch(
            cursor,
            user_id=user_id,
            course_id=course_id,
            filename=filename,
            file_type=Path(filename).suffix.casefold().lstrip("."),
            idempotency_key=idempotency_key,
            items=preview,
            parsed_count=len(preview),
            matched_count=matched,
            unmatched_count=unmatched,
            invalid_count=invalid + duplicate_count,
        )
    return {
        "batch": {
            key: batch.get(key)
            for key in (
                "id", "filename", "file_type", "status", "parsed_count",
                "matched_count", "unmatched_count", "invalid_count", "created_at",
            )
        },
        "items": batch.get("items") or preview,
        "duplicate_count": duplicate_count,
    }


async def preview_question_bank_upload(
    user_id: int,
    course_id: int,
    filename: str,
    content: bytes,
    idempotency_key: str | None,
) -> dict[str, Any]:
    key = idempotency_key or sha256(
        f"{user_id}:{course_id}:{filename}:{sha256(content).hexdigest()}".encode("utf-8")
    ).hexdigest()
    try:
        return _question_import_preview(user_id, course_id, filename, content, key)
    except ValueError as exc:
        raise AppError(str(exc), 422, "QUESTION_IMPORT_PARSE_FAILED") from exc


def commit_question_import(user_id: int, course_id: int, batch_id: int) -> dict[str, Any]:
    _require_course(user_id, course_id)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with get_cursor() as cursor:
        batch = repository.get_import_batch(cursor, user_id, course_id, batch_id)
        if batch is None:
            raise AppError("题库导入批次不存在或无访问权限", 404, "QUESTION_IMPORT_BATCH_NOT_FOUND")
        if batch.get("status") == "imported":
            return {"batch": batch, "created": [], "skipped": [], "idempotent": True}
        for item in batch.get("items") or []:
            if item.get("parse_status") == "invalid":
                skipped.append({"content": item.get("content"), "reason": item.get("parse_error") or "invalid"})
                continue
            content = str(item.get("content") or "").strip()
            if repository.question_exists(cursor, user_id, course_id, content):
                skipped.append({"content": content, "reason": "duplicate"})
                continue
            question = repository.create_question(
                cursor,
                user_id=user_id,
                course_id=course_id,
                item={
                    **item,
                    "source_type": "user_upload",
                    "source_file": batch.get("filename"),
                    "import_batch_id": batch_id,
                    "raw_provenance": item.get("raw_provenance") or {},
                    "validation": item.get("validation") or {},
                    "relevance": max(
                        [float(link.get("relevance") or 0) for link in item.get("tagging", {}).get("alignments", [])]
                        or [0.0]
                    ),
                    "confidence": max(
                        [float(link.get("confidence") or 0) for link in item.get("tagging", {}).get("alignments", [])]
                        or [0.0]
                    ),
                    "coverage_type": (item.get("tagging", {}).get("alignments") or [{}])[0].get("coverage_type", "direct"),
                },
                objective_ids=[int(value) for value in item.get("objective_ids") or []],
                import_batch_id=batch_id,
            )
            created.append(_public_question(question) or {"id": question["id"]})
        repository.mark_import_batch_imported(cursor, user_id, course_id, batch_id)
        if created:
            repository.supersede_queued_actions(cursor, user_id, course_id)
        refreshed = repository.get_import_batch(cursor, user_id, course_id, batch_id) or batch
    return {"batch": refreshed, "created": created, "skipped": skipped, "created_count": len(created)}


def tag_question_objectives(
    user_id: int,
    course_id: int,
    question_id: int,
    objective_ids: list[int] | None = None,
) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        objectives = repository.list_objectives(cursor, user_id, course_id)
        allowed = {int(item["id"]): item for item in objectives}
        question = repository.get_question(cursor, user_id, course_id, question_id)
        if question is None:
            raise AppError("题目不存在或无访问权限", 404, "QUESTION_NOT_FOUND")
        if objective_ids:
            invalid = [value for value in objective_ids if int(value) not in allowed]
            if invalid:
                raise AppError("题目关联了不属于当前课程的学习目标", 422, "QUESTION_OBJECTIVE_INVALID")
            links = [
                {"objective_id": int(value), "relevance": 0.9, "confidence": 1.0, "coverage_type": "direct"}
                for value in sorted(set(objective_ids))
            ]
        else:
            tagging = align_question_to_objectives(
                question["content"],
                question.get("answer"),
                objectives,
                question_type=str(question.get("question_type") or "short_answer"),
                user_id=user_id,
            )
            links = tagging.get("alignments") or []
        if not repository.replace_question_objectives(
            cursor,
            user_id=user_id,
            course_id=course_id,
            question_id=question_id,
            objective_links=links,
        ):
            raise AppError("题目不存在或无访问权限", 404, "QUESTION_NOT_FOUND")
        repository.supersede_queued_actions(cursor, user_id, course_id)
        return _public_question(repository.get_question(cursor, user_id, course_id, question_id)) or {}


TUTOR_PROMPT_VERSION = "adaptive-tutor-grounded-v1"


def _tutor_context(user_id: int, course_id: int, action_id: int | None, objective_id: int | None) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        action = repository.get_action(cursor, user_id, action_id) if action_id else repository.get_active_action(cursor, user_id, course_id)
        if action is not None and int(action["course_id"]) != int(course_id):
            raise AppError("学习动作不属于当前课程", 403, "ACTION_COURSE_MISMATCH")
        selected_objective_id = int(objective_id or (action or {}).get("objective_id") or 0)
        objectives = repository.list_objectives(cursor, user_id, course_id)
        objective = next((item for item in objectives if int(item["id"]) == selected_objective_id), None)
        if objective is None:
            objective = objectives[0] if objectives else None
        if objective is None:
            raise AppError("当前课程还没有可用 Learning Objective", 409, "TUTOR_OBJECTIVE_NOT_READY")
        selected_objective_id = int(objective["id"])
        evidence = repository.evidence_for_objective(cursor, user_id, course_id, selected_objective_id, limit=6)
        objective_evidence = repository.list_objective_evidence(
            cursor, user_id, course_id
        ).get(selected_objective_id, [])
        misconceptions = repository.list_misconceptions(cursor, user_id, course_id).get(selected_objective_id, [])
        relations = repository.list_relations(cursor, user_id, course_id)
        prerequisites = [
            relation
            for relation in relations
            if relation["relation_type"] == "prerequisite"
            and int(relation["target_objective_id"]) == selected_objective_id
        ]
    query = " ".join(
        str(value or "")
        for value in (objective.get("title"), objective.get("description"), objective.get("required_ability"))
    )
    try:
        retrieval = search_course_materials(user_id, course_id, query, 5)
        citations = list(retrieval.get("citations") or [])
        evidence_context = get_course_evidence_context(
            user_id,
            course_id,
            [int(item["chunk_id"]) for item in citations[:3] if item.get("chunk_id")],
            neighbor_window=1,
            max_tokens=8000,
        ) if citations else {"evidence_blocks": []}
    except Exception:
        citations = []
        evidence_context = {"evidence_blocks": []}
    if not citations and objective_evidence:
        # RAG is the primary path. Objective provenance is a deterministic
        # safety net for freshly indexed material or an unavailable vector
        # index; it still keeps Tutor grounded in course-owned chunks.
        citations = [
            {
                "chunk_id": int(item["chunk_id"]),
                "material_id": item.get("material_id"),
                "material_title": item.get("material_title"),
                "heading_path": item.get("heading_path"),
                "page_number": item.get("page_number"),
                "score": float(item.get("confidence") or 0),
                "snippet": str(item.get("snippet") or "")[:500],
                "provenance_type": "objective_evidence_fallback",
            }
            for item in objective_evidence[:5]
        ]
        evidence_context = {
            "evidence_blocks": [
                {
                    "material_id": item.get("material_id"),
                    "material_title": item.get("material_title"),
                    "heading_path": item.get("heading_path"),
                    "page_start": item.get("page_number"),
                    "page_end": item.get("page_number"),
                    "chunk_ids": [int(item["chunk_id"])],
                    "evidence_text": f"[chunk_id={item['chunk_id']}] {item.get('snippet') or ''}",
                }
                for item in objective_evidence[:5]
            ]
        }
    return {
        "objective": {
            "id": selected_objective_id,
            "title": objective.get("title"),
            "description": objective.get("description"),
            "required_ability": objective.get("required_ability"),
            "difficulty": objective.get("difficulty"),
        },
        "state": {
            "mastery": float(objective.get("mastery") or 0),
            "confidence": float(objective.get("confidence") or 0),
            "state": objective.get("state"),
            "attempt_count": int(objective.get("attempt_count") or 0),
            "consistency_confidence": float(objective.get("consistency_confidence") or 0),
            "diversity_confidence": float(objective.get("diversity_confidence") or 0),
        },
        "current_action": action,
        "recent_evidence": evidence,
        "active_misconception": misconceptions[:3],
        "prerequisites": prerequisites,
        "relevant_course_evidence": evidence_context.get("evidence_blocks") or [],
        "citations": citations[:5],
    }


def _policy_explanation(context: dict[str, Any]) -> str:
    action = context.get("current_action") or {}
    objective = context.get("objective") or {}
    reason = str(action.get("reason") or "当前证据需要一次可验证学习动作")
    return f"系统当前选择“{objective.get('title') or '这个目标'}”，因为：{reason}。完成后会根据新 Evidence 重新计算，而不是提前生成固定路线。"


def tutor_chat(
    user_id: int,
    course_id: int,
    *,
    message: str,
    intent: str = "explain",
    action_id: int | None = None,
    objective_id: int | None = None,
) -> dict[str, Any]:
    context = _tutor_context(user_id, course_id, action_id, objective_id)
    if intent == "why_this_action":
        reply = _policy_explanation(context)
        provider = "deterministic-policy"
    else:
        prompt_context = {
            "objective": context["objective"],
            "state": context["state"],
            "current_action": context.get("current_action"),
            "recent_evidence": context["recent_evidence"],
            "active_misconception": context["active_misconception"],
            "prerequisites": context["prerequisites"],
            "relevant_course_evidence": context["relevant_course_evidence"],
        }
        try:
            reply = invoke_agent_content(
                [
                    SystemMessage(
                        content=(
                            "你是 Adaptive Tutor 的教学交互层。只能解释和提问，不能修改 mastery、confidence、"
                            "misconception 或 schedule。课程事实必须优先依据提供的 evidence；如果 evidence 不足，"
                            "明确说资料不足，不得编造。根据 intent 进行解释、换例子、提示、拆步骤或苏格拉底式提问。"
                            "回答短而具体，最后给一个学生可以完成的下一步。"
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"intent={intent}\n教学上下文：{json.dumps(prompt_context, ensure_ascii=False, default=str)}\n"
                            f"学生请求：{message}"
                        )
                    ),
                ],
                model=get_llm(user_id),
            )
            provider = "llm"
        except Exception as exc:
            evidence = context.get("relevant_course_evidence") or []
            snippet = str(evidence[0].get("evidence_text") or "").strip()[:500] if evidence else ""
            reply = (
                f"围绕“{context['objective']['title']}”，先抓住这个可检查的能力：{context['objective']['required_ability']}。"
                + (f"课程资料证据：{snippet}" if snippet else "当前没有检索到足够课程证据，请先补充资料。")
                + "\n这次对话不会直接改变你的 Student Model。"
            )
            provider = "deterministic-tutor-fallback"
            context["fallback_reason"] = str(exc)[:300]
    tutor_check = None
    if intent == "check_understanding":
        objective = context["objective"]
        check_question = f"请用自己的话说明：{objective['required_ability']}"
        reference_answer = str(objective.get("description") or objective.get("required_ability") or "")
        with get_cursor() as cursor:
            tutor_check = repository.create_tutor_check(
                cursor,
                user_id=user_id,
                course_id=course_id,
                objective_id=int(objective["id"]),
                action_id=int(context["current_action"]["id"]) if context.get("current_action") else None,
                question=check_question,
                reference_answer=reference_answer,
                rubric="结论正确、给出判断依据，并能说明一个边界或场景。",
            )
        tutor_check = {
            "id": int(tutor_check["id"]),
            "question": check_question,
            "objective_id": int(objective["id"]),
        }
    return {
        "course_id": course_id,
        "intent": intent,
        "reply": reply,
        "provider": provider,
        "prompt_version": TUTOR_PROMPT_VERSION if provider == "llm" else None,
        "objective": context["objective"],
        "state": context["state"],
        "citations": context["citations"],
        "tutor_check": tutor_check,
        "evidence_written": False,
    }


def submit_tutor_check(
    user_id: int,
    course_id: int,
    check_id: int,
    response: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        check = repository.get_tutor_check(cursor, user_id, course_id, check_id)
        if check is None:
            raise AppError("Tutor Check 不存在或无访问权限", 404, "TUTOR_CHECK_NOT_FOUND")
        if check.get("status") == "submitted":
            return {
                "idempotent": True,
                "check": check,
                "evidence_id": check.get("evidence_id"),
            }
        key = idempotency_key or sha256(
            f"tutor-check:{check_id}:{response}".encode("utf-8")
        ).hexdigest()
        existing = repository.get_evidence_by_idempotency(cursor, user_id, course_id, "tutor_check", key)
        if existing is not None:
            return {"idempotent": True, "evidence_id": int(existing["id"]), "state": existing}
        objective = next(
            (
                item
                for item in repository.list_objectives(cursor, user_id, course_id)
                if int(item["id"]) == int(check["objective_id"])
            ),
            None,
        )
        if objective is None:
            raise AppError("Tutor Check 对应的 Learning Objective 已不存在", 409, "TUTOR_CHECK_OBJECTIVE_MISSING")
        grade = grade_response(
            {
                "content": check["question"],
                "question_type": "scenario",
                "answer": check["reference_answer"],
                "rubric": check.get("rubric"),
                "difficulty": "easy",
            },
            response,
            objective=objective,
            user_id=user_id,
        )
        result = _record_evidence(
            cursor,
            user_id=user_id,
            course_id=course_id,
            objective_id=int(check["objective_id"]),
            source_type="tutor_check",
            response=response,
            question=None,
            action_id=int(check["action_id"]) if check.get("action_id") else None,
            grade_result=grade,
            idempotency_key=key,
            action_type="explain",
        )
        refreshed = repository.complete_tutor_check(
            cursor,
            user_id=user_id,
            course_id=course_id,
            check_id=check_id,
            response=response,
            score=float(result["score"]),
            grader_type=str(result["grader"]["type"]),
            grader_version=str(result["grader"]["version"]),
            grader_model=result["grader"].get("model"),
            grader_prompt_version=result["grader"].get("prompt_version"),
            evidence_id=int(result["evidence_id"]),
        )
        result["check"] = refreshed
        result["next_action"] = _ensure_next_action(cursor, user_id, course_id)
        return result


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
            existing = repository.evidence_for_action(cursor, user_id, action_id)
            if existing is not None:
                return {
                    "idempotent": True,
                    "evidence_id": int(existing["id"]),
                    "objective_id": int(existing["objective_id"]),
                    "score": float(existing.get("score") or 0),
                    "state": {
                        "mastery": float(existing.get("mastery_after") or 0),
                        "confidence": float(existing.get("confidence_after") or 0),
                    },
                    "next_action": _ensure_next_action(cursor, user_id, int(action["course_id"])),
                }
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
        if question is None:
            raise AppError(
                "讲解动作必须通过 Tutor Check 提交，不能把普通文本直接写入 Evidence",
                409,
                "EXPLAIN_REQUIRES_TUTOR_CHECK",
            )
        idempotency_key = payload.get("idempotency_key") or sha256(
            f"action:{action_id}:{payload['response']}".encode("utf-8")
        ).hexdigest()
        existing = repository.get_evidence_by_idempotency(
            cursor,
            user_id,
            int(action["course_id"]),
            "practice",
            idempotency_key,
        )
        if existing is not None:
            return {
                "idempotent": True,
                "evidence_id": int(existing["id"]),
                "objective_id": int(existing["objective_id"]),
                "score": float(existing.get("score") or 0),
                "next_action": _ensure_next_action(cursor, user_id, int(action["course_id"])),
            }
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
            idempotency_key=idempotency_key,
            action_type=str(action.get("action_type") or ""),
        )
        result["completed_action"] = _public_action(cursor, user_id, repository.get_action(cursor, user_id, action_id))
        result["next_action"] = _ensure_next_action(cursor, user_id, int(action["course_id"]))
        return result


def start_diagnostic(user_id: int, course_id: int, question_count: int = 6) -> dict[str, Any]:
    _require_course(user_id, course_id)
    with get_cursor() as cursor:
        objectives = repository.list_objectives(cursor, user_id, course_id)
        relations = repository.list_relations(cursor, user_id, course_id)
        dependent_counts: dict[int, int] = {}
        prerequisite_counts: dict[int, int] = {}
        for relation in relations:
            if relation.get("relation_type") != "prerequisite":
                continue
            source_id = int(relation["source_objective_id"])
            target_id = int(relation["target_objective_id"])
            dependent_counts[source_id] = dependent_counts.get(source_id, 0) + 1
            prerequisite_counts[target_id] = prerequisite_counts.get(target_id, 0) + 1

        def diagnostic_priority(item: dict[str, Any]) -> tuple[float, float, int]:
            objective_id = int(item["id"])
            confidence = float(item.get("confidence") or 0)
            attempts = int(item.get("attempt_count") or 0)
            uncertainty = 1.0 - confidence
            coverage_gap = 1.0 - min(1.0, attempts / 3.0)
            importance = float(item.get("importance") or 0)
            hub_bonus = min(1.0, dependent_counts.get(objective_id, 0) / 3.0)
            prerequisite_bonus = min(1.0, prerequisite_counts.get(objective_id, 0) / 3.0)
            score = (
                importance * 0.35
                + uncertainty * 0.25
                + coverage_gap * 0.20
                + hub_bonus * 0.12
                + prerequisite_bonus * 0.08
            )
            return score, importance, -objective_id

        selected: list[dict[str, Any]] = []
        seen_question_ids: set[int] = set()
        selected_objective_ids: set[int] = set()
        ranked_objectives = sorted(objectives, key=diagnostic_priority, reverse=True)
        for objective in ranked_objectives:
            question = repository.find_best_question(
                cursor,
                user_id=user_id,
                course_id=course_id,
                objective_id=int(objective["id"]),
                desired_difficulty="medium",
                coverage_types=["diagnostic", "scenario", "direct"],
                recent_question_ids=seen_question_ids,
            )
            if question and int(question["id"]) not in seen_question_ids:
                selected.append(_public_question(question) or {})
                seen_question_ids.add(int(question["id"]))
                selected_objective_ids.add(int(objective["id"]))
            if len(selected) >= question_count:
                break
        # If the first pass has fewer than the requested number, allow a
        # second question for an already-covered objective, but still avoid
        # repeating the exact question or an already recent attempt.
        if len(selected) < question_count:
            for objective in ranked_objectives:
                question = repository.find_best_question(
                    cursor,
                    user_id=user_id,
                    course_id=course_id,
                    objective_id=int(objective["id"]),
                    desired_difficulty="medium",
                    coverage_types=["diagnostic", "scenario", "direct", "transfer"],
                    recent_question_ids=seen_question_ids,
                )
                if question and int(question["id"]) not in seen_question_ids:
                    selected.append(_public_question(question) or {})
                    seen_question_ids.add(int(question["id"]))
                if len(selected) >= question_count:
                    break
    return {
        "course_id": course_id,
        "questions": selected,
        "question_count": len(selected),
        "selection_policy": "importance+uncertainty+coverage+prerequisite-hub+diversity",
    }


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
            for link in objectives:
                objective_id = int(link["objective_id"])
                idempotency_key = sha256(
                    f"diagnostic:{question['id']}:{objective_id}:{answer['response']}".encode("utf-8")
                ).hexdigest()
                result = _record_evidence(
                    cursor,
                    user_id=user_id,
                    course_id=course_id,
                    objective_id=objective_id,
                    source_type="diagnostic",
                    response=answer["response"],
                    question=question,
                    action_id=None,
                    idempotency_key=idempotency_key,
                    action_type="diagnose",
                )
                results.append(result)
        # Diagnostic evidence invalidates a queued snapshot made before the
        # diagnosis. The next action must be selected from the new state.
        repository.supersede_queued_actions(cursor, user_id, course_id)
        next_action = _ensure_next_action(cursor, user_id, course_id)
    return {
        "results": results,
        "next_action": next_action,
        "count": len(results),
        "question_count": len(answers),
    }


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
    "commit_question_import",
    "get_next_action",
    "get_objective_detail",
    "get_overview",
    "get_progress",
    "get_sources",
    "rebuild_curriculum",
    "preview_question_bank_upload",
    "start_action",
    "start_diagnostic",
    "submit_action",
    "submit_diagnostic",
    "submit_tutor_check",
    "tag_question_objectives",
    "tutor_chat",
]
