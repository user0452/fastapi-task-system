"""Persistence boundary for the Adaptive Tutor domain.

All writes are scoped by both ``user_id`` and ``course_id``.  The repository
does not contain policy decisions; it only persists facts and loads the
deterministic policy input.
"""

from __future__ import annotations

import json
from typing import Any

from app.modules.adaptive.question_selector import select_best_question


def _rows(cursor) -> list[dict[str, Any]]:
    return list(cursor.fetchall())


def _row(cursor) -> dict[str, Any] | None:
    return cursor.fetchone()


def create_curriculum_build(
    cursor,
    *,
    user_id: int,
    course_id: int,
    material_id: int | None,
    status: str,
    extraction_confidence: float,
    model: str | None,
    prompt_version: str | None,
    error_message: str | None,
) -> int:
    cursor.execute(
        """
        INSERT INTO curriculum_builds
            (user_id, course_id, material_id, status, extraction_confidence,
             model, prompt_version, error_message, completed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s IN ('ready', 'degraded', 'failed')
                     THEN CURRENT_TIMESTAMP(6) ELSE NULL END)
        """,
        (
            user_id,
            course_id,
            material_id,
            status,
            extraction_confidence,
            model,
            prompt_version,
            error_message,
            status,
        ),
    )
    return int(cursor.lastrowid)


def latest_curriculum_build(cursor, user_id: int, course_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT id, material_id, status, extraction_confidence, model,
               prompt_version, error_message, created_at, completed_at
        FROM curriculum_builds
        WHERE user_id = %s AND course_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id, course_id),
    )
    return _row(cursor)


def _objective_by_title(cursor, user_id: int, course_id: int, title: str) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT id, user_id, course_id, title, description, required_ability,
               importance, difficulty, status, extraction_confidence,
               curriculum_version, created_at, updated_at
        FROM learning_objectives
        WHERE user_id = %s AND course_id = %s AND title = %s
        LIMIT 1
        """,
        (user_id, course_id, title),
    )
    return _row(cursor)


def persist_curriculum(
    cursor,
    *,
    user_id: int,
    course_id: int,
    material_id: int,
    chunks: list[dict[str, Any]],
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Persist a validated extraction and every objective's chunk provenance."""
    status = str(extraction.get("status") or "failed")
    raw_objectives = list(extraction.get("objectives") or []) if status != "failed" else []
    prompt_version = str(extraction.get("prompt_version") or "objective-extraction-v2")
    model = str(extraction.get("model") or "mock")
    error_message = str(extraction.get("error") or "")[:2000] or None
    confidence = float(extraction.get("extraction_confidence") or 0.0)
    build_id = create_curriculum_build(
        cursor,
        user_id=user_id,
        course_id=course_id,
        material_id=material_id,
        status=status,
        extraction_confidence=confidence,
        model=model,
        prompt_version=prompt_version,
        error_message=error_message,
    )

    chunk_by_index = {
        int(chunk["chunk_index"]): chunk
        for chunk in chunks
        if chunk.get("chunk_index") is not None
    }
    objective_ids: dict[str, int] = {}
    stored_objectives: list[dict[str, Any]] = []
    for item in raw_objectives:
        title = str(item.get("title") or "").strip()[:255]
        description = str(item.get("description") or "").strip()[:5000]
        ability = str(item.get("required_ability") or "").strip()[:500]
        if len(title) < 8 or not description or not ability:
            continue
        importance = max(0.0, min(1.0, float(item.get("importance") or 0.5)))
        item_difficulty = str(item.get("difficulty") or "medium")
        if item_difficulty not in {"easy", "medium", "hard"}:
            item_difficulty = "medium"
        item_confidence = max(0.0, min(1.0, float(item.get("confidence") or confidence)))
        cursor.execute(
            """
            INSERT INTO learning_objectives
                (user_id, course_id, title, description, required_ability,
                 importance, difficulty, extraction_confidence, curriculum_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                description = VALUES(description),
                required_ability = VALUES(required_ability),
                importance = VALUES(importance),
                difficulty = VALUES(difficulty),
                extraction_confidence = GREATEST(extraction_confidence, VALUES(extraction_confidence)),
                curriculum_version = VALUES(curriculum_version),
                status = 'active'
            """,
            (
                user_id,
                course_id,
                title,
                description,
                ability,
                importance,
                item_difficulty,
                item_confidence,
                prompt_version,
            ),
        )
        objective = _objective_by_title(cursor, user_id, course_id, title)
        if objective is None:
            continue
        objective_id = int(objective["id"])
        objective_ids[title] = objective_id
        stored_objectives.append(objective)
        for chunk_index in item.get("chunk_indices") or []:
            chunk = chunk_by_index.get(int(chunk_index))
            if chunk is None:
                continue
            cursor.execute(
                """
                INSERT IGNORE INTO objective_evidence
                    (user_id, course_id, objective_id, material_id, chunk_id, confidence)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    course_id,
                    objective_id,
                    material_id,
                    int(chunk["id"]),
                    item_confidence,
                ),
            )

    for relation in extraction.get("relations") or []:
        source_id = objective_ids.get(str(relation.get("source_title") or "").strip())
        target_id = objective_ids.get(str(relation.get("target_title") or "").strip())
        relation_type = str(relation.get("relation_type") or "prerequisite").strip()
        if not source_id or not target_id or source_id == target_id:
            continue
        if relation_type != "prerequisite":
            continue
        evidence_chunk_id = None
        raw_index = relation.get("evidence_chunk_index")
        if raw_index is not None and int(raw_index) in chunk_by_index:
            evidence_chunk_id = int(chunk_by_index[int(raw_index)]["id"])
        cursor.execute(
            """
            INSERT INTO objective_relations
                (user_id, course_id, source_objective_id, target_objective_id,
                 relation_type, confidence, rationale, evidence_chunk_id)
            VALUES (%s, %s, %s, %s, 'prerequisite', %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                confidence = GREATEST(confidence, VALUES(confidence)),
                rationale = COALESCE(VALUES(rationale), rationale),
                evidence_chunk_id = COALESCE(VALUES(evidence_chunk_id), evidence_chunk_id)
            """,
            (
                user_id,
                course_id,
                source_id,
                target_id,
                max(0.0, min(1.0, float(relation.get("confidence") or 0.0))),
                str(relation.get("rationale") or "")[:500] or None,
                evidence_chunk_id,
            ),
        )
    return {
        "build_id": build_id,
        "status": status,
        "objective_count": len(stored_objectives),
        "objectives": stored_objectives,
        "error": error_message,
    }


def list_objectives(cursor, user_id: int, course_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT objective.id, objective.title, objective.description,
               objective.required_ability, objective.importance,
               objective.difficulty, objective.status,
               objective.extraction_confidence, objective.curriculum_version,
               objective.created_at, objective.updated_at,
               COALESCE(state.mastery, 0) AS mastery,
               COALESCE(state.confidence, 0) AS confidence,
               COALESCE(state.attempt_count, 0) AS attempt_count,
               COALESCE(state.correct_count, 0) AS correct_count,
               COALESCE(state.incorrect_count, 0) AS incorrect_count,
               COALESCE(state.success_streak, 0) AS success_streak,
               COALESCE(state.failure_streak, 0) AS failure_streak,
               state.last_practiced_at, state.last_success_at,
               state.last_failure_at, COALESCE(state.state, 'unknown') AS learner_state
        FROM learning_objectives objective
        LEFT JOIN student_objective_states state
          ON state.objective_id = objective.id
         AND state.user_id = objective.user_id
         AND state.course_id = objective.course_id
        WHERE objective.user_id = %s AND objective.course_id = %s
          AND objective.status = 'active'
        ORDER BY objective.importance DESC, objective.id ASC
        """,
        (user_id, course_id),
    )
    rows = _rows(cursor)
    for row in rows:
        row["id"] = int(row["id"])
        row["mastery"] = float(row.get("mastery") or 0)
        row["confidence"] = float(row.get("confidence") or 0)
        row["importance"] = float(row.get("importance") or 0)
        row["extraction_confidence"] = float(row.get("extraction_confidence") or 0)
        row["state"] = row.pop("learner_state")
    return rows


def list_relations(cursor, user_id: int, course_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT relation.id, relation.source_objective_id, relation.target_objective_id,
               relation.relation_type, relation.confidence, relation.rationale,
               source.title AS source_title, target.title AS target_title
        FROM objective_relations relation
        JOIN learning_objectives source ON source.id = relation.source_objective_id
        JOIN learning_objectives target ON target.id = relation.target_objective_id
        WHERE relation.user_id = %s AND relation.course_id = %s
          AND source.status = 'active' AND target.status = 'active'
        ORDER BY relation.id
        """,
        (user_id, course_id),
    )
    rows = _rows(cursor)
    for row in rows:
        row["id"] = int(row["id"])
        row["source_objective_id"] = int(row["source_objective_id"])
        row["target_objective_id"] = int(row["target_objective_id"])
        row["confidence"] = float(row.get("confidence") or 0)
    return rows


def list_objective_evidence(cursor, user_id: int, course_id: int) -> dict[int, list[dict[str, Any]]]:
    cursor.execute(
        """
        SELECT evidence.objective_id, evidence.chunk_id, evidence.confidence,
               chunk.chunk_index, chunk.page_number, chunk.heading_path,
               chunk.chunk_text, material.id AS material_id,
               material.title AS material_title, material.filename
        FROM objective_evidence evidence
        JOIN course_material_chunks chunk ON chunk.id = evidence.chunk_id
        JOIN course_materials material ON material.id = evidence.material_id
        WHERE evidence.user_id = %s AND evidence.course_id = %s
        ORDER BY evidence.objective_id, evidence.confidence DESC, evidence.id
        """,
        (user_id, course_id),
    )
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in _rows(cursor):
        objective_id = int(row.pop("objective_id"))
        if len(grouped.setdefault(objective_id, [])) >= 5:
            continue
        row["chunk_id"] = int(row["chunk_id"])
        row["confidence"] = float(row.get("confidence") or 0)
        row["snippet"] = str(row.pop("chunk_text") or "")[:500]
        grouped[objective_id].append(row)
    return grouped


def get_question(cursor, user_id: int, course_id: int, question_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT id, content, question_type, answer, rubric, explanation,
               difficulty, source_type, source_material_id, source_url,
               quality_score, status, model, prompt_version,
               generation_context_json, created_at
        FROM questions
        WHERE id = %s AND user_id = %s AND course_id = %s
        """,
        (question_id, user_id, course_id),
    )
    question = _row(cursor)
    if question is None:
        return None
    question["quality_score"] = float(question.get("quality_score") or 0)
    if isinstance(question.get("generation_context_json"), str):
        try:
            question["generation_context"] = json.loads(question.pop("generation_context_json"))
        except json.JSONDecodeError:
            question["generation_context"] = None
    else:
        question["generation_context"] = question.pop("generation_context_json", None)
    cursor.execute(
        """
        SELECT link.objective_id, link.relevance, link.coverage_type,
               link.confidence, objective.title
        FROM question_objectives link
        JOIN learning_objectives objective ON objective.id = link.objective_id
        WHERE link.question_id = %s
        ORDER BY link.relevance DESC, link.objective_id
        """,
        (question_id,),
    )
    question["objectives"] = []
    for link in _rows(cursor):
        question["objectives"].append(
            {
                "objective_id": int(link["objective_id"]),
                "title": link["title"],
                "relevance": float(link.get("relevance") or 0),
                "coverage_type": link["coverage_type"],
                "confidence": float(link.get("confidence") or 0),
            }
        )
    # Answers are durable facts, but never expose the reference answer to the
    # student-facing action payload.
    return question


def list_questions(cursor, user_id: int, course_id: int, limit: int = 200) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT q.id, q.content, q.question_type, q.difficulty, q.source_type,
               q.source_material_id, q.source_url, q.quality_score, q.status,
               q.created_at, COUNT(DISTINCT attempt.id) AS attempt_count,
               GROUP_CONCAT(DISTINCT objective.title ORDER BY objective.id SEPARATOR ', ') AS objective_titles
        FROM questions q
        LEFT JOIN question_attempts attempt ON attempt.question_id = q.id
        LEFT JOIN question_objectives link ON link.question_id = q.id
        LEFT JOIN learning_objectives objective ON objective.id = link.objective_id
        WHERE q.user_id = %s AND q.course_id = %s
        GROUP BY q.id, q.content, q.question_type, q.difficulty, q.source_type,
                 q.source_material_id, q.source_url, q.quality_score, q.status, q.created_at
        ORDER BY q.created_at DESC, q.id DESC
        LIMIT %s
        """,
        (user_id, course_id, min(max(int(limit), 1), 500)),
    )
    rows = _rows(cursor)
    for row in rows:
        row["quality_score"] = float(row.get("quality_score") or 0)
        row["attempt_count"] = int(row.get("attempt_count") or 0)
    return rows


def question_exists(cursor, user_id: int, course_id: int, content: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM questions WHERE user_id = %s AND course_id = %s AND content = %s LIMIT 1",
        (user_id, course_id, content),
    )
    return _row(cursor) is not None


def create_question(
    cursor,
    *,
    user_id: int,
    course_id: int,
    item: dict[str, Any],
    objective_ids: list[int],
    generation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = "active" if objective_ids else "unmatched"
    cursor.execute(
        """
        INSERT INTO questions
            (user_id, course_id, content, question_type, answer, rubric,
             explanation, difficulty, source_type, source_material_id,
             source_url, quality_score, status, model, prompt_version,
             generation_context_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            course_id,
            item["content"],
            item.get("question_type", "short_answer"),
            item["answer"],
            item.get("rubric"),
            item.get("explanation"),
            item.get("difficulty", "medium"),
            item.get("source_type", "user_upload"),
            item.get("source_material_id"),
            item.get("source_url"),
            float(item.get("quality_score", 0.8)),
            status,
            item.get("model"),
            item.get("prompt_version"),
            json.dumps(generation_context, ensure_ascii=False) if generation_context else None,
        ),
    )
    question_id = int(cursor.lastrowid)
    for objective_id in objective_ids:
        cursor.execute(
            """
            INSERT INTO question_objectives
                (question_id, objective_id, relevance, coverage_type, confidence)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                relevance = GREATEST(relevance, VALUES(relevance)),
                confidence = GREATEST(confidence, VALUES(confidence)),
                coverage_type = VALUES(coverage_type)
            """,
            (
                question_id,
                objective_id,
                float(item.get("relevance", 0.9)),
                item.get("coverage_type", "direct"),
                float(item.get("confidence", 0.9)),
            ),
        )
    return get_question(cursor, user_id, course_id, question_id) or {"id": question_id}


def find_best_question(
    cursor,
    *,
    user_id: int,
    course_id: int,
    objective_id: int,
    desired_difficulty: str,
    coverage_types: list[str] | None = None,
) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT q.id, q.content, q.question_type, q.answer, q.rubric,
               q.explanation, q.difficulty, q.source_type, q.source_material_id,
               q.source_url, q.quality_score, link.relevance, link.coverage_type,
               link.confidence, COUNT(DISTINCT attempt.id) AS attempt_count,
               MAX(attempt.created_at) AS last_attempt_at,
               SUM(CASE WHEN attempt.score >= 0.7 THEN 1 ELSE 0 END) AS correct_count
        FROM questions q
        JOIN question_objectives link ON link.question_id = q.id
        LEFT JOIN question_attempts attempt
          ON attempt.question_id = q.id AND attempt.user_id = %s
        WHERE q.user_id = %s AND q.course_id = %s
          AND link.objective_id = %s AND q.status = 'active'
        GROUP BY q.id, q.content, q.question_type, q.answer, q.rubric,
                 q.explanation, q.difficulty, q.source_type, q.source_material_id,
                 q.source_url, q.quality_score, link.relevance,
                 link.coverage_type, link.confidence
        """,
        (user_id, user_id, course_id, objective_id),
    )
    candidates = _rows(cursor)
    selected = select_best_question(
        candidates,
        desired_difficulty=desired_difficulty,
        coverage_types=coverage_types,
    )
    if selected is None:
        return None
    return get_question(cursor, user_id, course_id, int(selected["id"]))


def get_active_action(cursor, user_id: int, course_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT id, objective_id, action_type, priority, reason, expected_minutes,
               desired_difficulty, question_id, policy_version, status,
               created_at, started_at, completed_at
        FROM learning_actions
        WHERE user_id = %s AND course_id = %s AND status IN ('queued', 'in_progress')
        ORDER BY CASE WHEN status = 'in_progress' THEN 0 ELSE 1 END,
                 priority DESC, id DESC
        LIMIT 1
        """,
        (user_id, course_id),
    )
    return _row(cursor)


def create_action(cursor, *, user_id: int, course_id: int, decision: dict[str, Any]) -> dict[str, Any]:
    cursor.execute(
        """
        INSERT INTO learning_actions
            (user_id, course_id, objective_id, action_type, priority,
             reason, expected_minutes, desired_difficulty, question_id,
             policy_version, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'queued')
        """,
        (
            user_id,
            course_id,
            int(decision["objective_id"]),
            decision["action_type"],
            float(decision["priority"]),
            decision["reason"],
            int(decision.get("expected_minutes") or 8),
            decision.get("desired_difficulty", "medium"),
            decision.get("question_id"),
            decision.get("policy_version"),
        ),
    )
    action_id = int(cursor.lastrowid)
    cursor.execute(
        """
        SELECT id, objective_id, action_type, priority, reason, expected_minutes,
               desired_difficulty, question_id, policy_version, status,
               created_at, started_at, completed_at
        FROM learning_actions WHERE id = %s
        """,
        (action_id,),
    )
    return _row(cursor) or {"id": action_id}


def get_action(cursor, user_id: int, action_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT action.id, action.user_id, action.course_id, action.objective_id,
               action.action_type, action.priority, action.reason,
               action.expected_minutes, action.desired_difficulty,
               action.question_id, action.policy_version, action.status,
               action.created_at, action.started_at, action.completed_at,
               objective.title AS objective_title,
               objective.description AS objective_description,
               objective.required_ability
        FROM learning_actions action
        JOIN learning_objectives objective ON objective.id = action.objective_id
        WHERE action.id = %s AND action.user_id = %s
        """,
        (action_id, user_id),
    )
    return _row(cursor)


def start_action(cursor, user_id: int, action_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        UPDATE learning_actions
        SET status = 'in_progress', started_at = COALESCE(started_at, CURRENT_TIMESTAMP(6))
        WHERE id = %s AND user_id = %s AND status = 'queued'
        """,
        (action_id, user_id),
    )
    return get_action(cursor, user_id, action_id)


def complete_action(cursor, user_id: int, action_id: int) -> None:
    cursor.execute(
        """
        UPDATE learning_actions
        SET status = 'completed', completed_at = CURRENT_TIMESTAMP(6)
        WHERE id = %s AND user_id = %s AND status IN ('queued', 'in_progress')
        """,
        (action_id, user_id),
    )


def get_state(cursor, user_id: int, course_id: int, objective_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT id, mastery, confidence, attempt_count, correct_count,
               incorrect_count, success_streak, failure_streak,
               last_practiced_at, last_success_at, last_failure_at,
               state, model_version
        FROM student_objective_states
        WHERE user_id = %s AND course_id = %s AND objective_id = %s
        FOR UPDATE
        """,
        (user_id, course_id, objective_id),
    )
    row = _row(cursor)
    if row is not None:
        for key in ("mastery", "confidence"):
            row[key] = float(row.get(key) or 0)
    return row


def save_state(cursor, user_id: int, course_id: int, objective_id: int, state: dict[str, Any]) -> None:
    cursor.execute(
        """
        INSERT INTO student_objective_states
            (user_id, course_id, objective_id, mastery, confidence,
             attempt_count, correct_count, incorrect_count, success_streak,
             failure_streak, last_practiced_at, last_success_at,
             last_failure_at, state, model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            mastery = VALUES(mastery), confidence = VALUES(confidence),
            attempt_count = VALUES(attempt_count), correct_count = VALUES(correct_count),
            incorrect_count = VALUES(incorrect_count), success_streak = VALUES(success_streak),
            failure_streak = VALUES(failure_streak), last_practiced_at = VALUES(last_practiced_at),
            last_success_at = VALUES(last_success_at), last_failure_at = VALUES(last_failure_at),
            state = VALUES(state), model_version = VALUES(model_version)
        """,
        (
            user_id,
            course_id,
            objective_id,
            state["mastery"],
            state["confidence"],
            state["attempt_count"],
            state["correct_count"],
            state["incorrect_count"],
            state["success_streak"],
            state["failure_streak"],
            state.get("last_practiced_at"),
            state.get("last_success_at"),
            state.get("last_failure_at"),
            state["state"],
            state.get("model_version", "bkt-inspired-v1"),
        ),
    )


def create_question_attempt(
    cursor,
    *,
    user_id: int,
    course_id: int,
    question_id: int,
    action_id: int | None,
    response: str,
    score: float,
    grader_type: str,
    grader_version: str,
    feedback: str,
) -> int:
    cursor.execute(
        """
        INSERT INTO question_attempts
            (user_id, course_id, question_id, action_id, response, score,
             grader_type, grader_version, feedback)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            course_id,
            question_id,
            action_id,
            response,
            score,
            grader_type,
            grader_version,
            feedback[:5000],
        ),
    )
    return int(cursor.lastrowid)


def create_learning_evidence(
    cursor,
    *,
    user_id: int,
    course_id: int,
    objective_id: int,
    source_type: str,
    question_id: int | None,
    attempt_id: int | None,
    response: str | None,
    score: float,
    difficulty: str,
    grader_type: str,
    grader_version: str,
    misconception_code: str | None,
    misconception_text: str | None,
    misconception_confidence: float | None,
    update: dict[str, Any],
) -> int:
    cursor.execute(
        """
        INSERT INTO learning_evidence
            (user_id, course_id, objective_id, source_type, question_id,
             attempt_id, response, score, difficulty, grader_type,
             grader_version, misconception_code, misconception_text,
             misconception_confidence, mastery_before, mastery_after,
             confidence_before, confidence_after, update_reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            course_id,
            objective_id,
            source_type,
            question_id,
            attempt_id,
            response,
            score,
            difficulty,
            grader_type,
            grader_version,
            misconception_code,
            misconception_text,
            misconception_confidence,
            update.get("mastery_before"),
            update.get("mastery"),
            update.get("confidence_before"),
            update.get("confidence"),
            update.get("update_reason"),
        ),
    )
    return int(cursor.lastrowid)


def upsert_misconception(
    cursor,
    *,
    user_id: int,
    course_id: int,
    objective_id: int,
    code: str,
    description: str,
    confidence: float,
) -> None:
    cursor.execute(
        """
        INSERT INTO misconceptions
            (user_id, course_id, objective_id, code, description, confidence)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            description = VALUES(description),
            confidence = GREATEST(confidence, VALUES(confidence)),
            occurrence_count = occurrence_count + 1,
            last_seen_at = CURRENT_TIMESTAMP(6),
            resolved_at = NULL
        """,
        (user_id, course_id, objective_id, code[:100], description[:500], confidence),
    )


def resolve_misconceptions(
    cursor,
    *,
    user_id: int,
    course_id: int,
    objective_id: int,
    code: str | None = None,
) -> int:
    """Resolve active misconception records after strong contrary evidence."""
    if code:
        cursor.execute(
            """
            UPDATE misconceptions
            SET resolved_at = CURRENT_TIMESTAMP(6)
            WHERE user_id = %s AND course_id = %s AND objective_id = %s
              AND code = %s AND resolved_at IS NULL
            """,
            (user_id, course_id, objective_id, code[:100]),
        )
    else:
        cursor.execute(
            """
            UPDATE misconceptions
            SET resolved_at = CURRENT_TIMESTAMP(6)
            WHERE user_id = %s AND course_id = %s AND objective_id = %s
              AND resolved_at IS NULL
            """,
            (user_id, course_id, objective_id),
        )
    return int(cursor.rowcount or 0)


def list_misconceptions(cursor, user_id: int, course_id: int) -> dict[int, list[dict[str, Any]]]:
    cursor.execute(
        """
        SELECT id, objective_id, code, description, confidence,
               occurrence_count, first_seen_at, last_seen_at, resolved_at
        FROM misconceptions
        WHERE user_id = %s AND course_id = %s AND resolved_at IS NULL
        ORDER BY last_seen_at DESC, id DESC
        """,
        (user_id, course_id),
    )
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in _rows(cursor):
        objective_id = int(row.pop("objective_id"))
        row["id"] = int(row["id"])
        row["confidence"] = float(row.get("confidence") or 0)
        row["occurrence_count"] = int(row.get("occurrence_count") or 0)
        grouped.setdefault(objective_id, []).append(row)
    return grouped


def evidence_for_objective(cursor, user_id: int, course_id: int, objective_id: int, limit: int = 20) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT id, source_type, question_id, attempt_id, response, score,
               difficulty, grader_type, grader_version, misconception_code,
               misconception_text, misconception_confidence, mastery_before,
               mastery_after, confidence_before, confidence_after,
               update_reason, created_at
        FROM learning_evidence
        WHERE user_id = %s AND course_id = %s AND objective_id = %s
        ORDER BY created_at DESC, id DESC
        LIMIT %s
        """,
        (user_id, course_id, objective_id, min(max(int(limit), 1), 100)),
    )
    rows = _rows(cursor)
    for row in rows:
        row["score"] = float(row.get("score") or 0)
        for key in ("mastery_before", "mastery_after", "confidence_before", "confidence_after"):
            if row.get(key) is not None:
                row[key] = float(row[key])
    return rows


def course_counts(cursor, user_id: int, course_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, table in (
        ("objective_count", "learning_objectives"),
        ("question_count", "questions"),
        ("evidence_count", "learning_evidence"),
    ):
        cursor.execute(
            f"SELECT COUNT(*) AS total FROM {table} WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        )
        counts[key] = int((_row(cursor) or {}).get("total") or 0)
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM questions q
        LEFT JOIN question_objectives link ON link.question_id = q.id
        WHERE q.user_id = %s AND q.course_id = %s AND link.question_id IS NULL
        """,
        (user_id, course_id),
    )
    counts["unmatched_question_count"] = int((_row(cursor) or {}).get("total") or 0)
    return counts


__all__ = [
    "course_counts",
    "create_action",
    "create_curriculum_build",
    "create_learning_evidence",
    "create_question",
    "create_question_attempt",
    "evidence_for_objective",
    "find_best_question",
    "get_action",
    "get_active_action",
    "get_question",
    "get_state",
    "latest_curriculum_build",
    "list_misconceptions",
    "list_objective_evidence",
    "list_objectives",
    "list_questions",
    "list_relations",
    "persist_curriculum",
    "question_exists",
    "resolve_misconceptions",
    "save_state",
    "start_action",
    "complete_action",
    "upsert_misconception",
]
