import json
from datetime import date


def list_points_with_mastery(cursor, user_id: int, course_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT kp.id, kp.name, kp.description, kp.sort_order,
               COALESCE(mr.mastery, 0) AS mastery,
               mr.id AS mastery_record_id,
               COALESCE(mr.low_score_streak, 0) AS low_score_streak,
               mr.last_evaluation_id
        FROM knowledge_points kp
        LEFT JOIN mastery_records mr
          ON mr.knowledge_point_id = kp.id
         AND mr.user_id = %s
         AND mr.course_id = %s
        WHERE kp.user_id = %s AND kp.course_id = %s
        ORDER BY mastery ASC, kp.sort_order ASC, kp.id ASC
        """,
        (user_id, course_id, user_id, course_id),
    )
    return list(cursor.fetchall())


def create_quiz_set(
    cursor,
    user_id: int,
    course: dict,
    title: str,
    purpose: str,
    questions: list[dict],
) -> dict:
    quiz_json = json.dumps({"questions": questions, "purpose": purpose}, ensure_ascii=False)
    cursor.execute(
        """
        INSERT INTO quiz_sets
            (user_id, course_id, title, course_name, topic, quiz_json, purpose)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, course["id"], title, course["name"], "课程诊断", quiz_json, purpose),
    )
    quiz_set_id = cursor.lastrowid
    stored_questions = []
    for question in questions:
        cursor.execute(
            """
            INSERT INTO quiz_questions
                (quiz_set_id, knowledge_point_id, question_type, question, answer, difficulty)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                quiz_set_id,
                question["knowledge_point_id"],
                question.get("question_type", "short_answer"),
                question["question"],
                question["answer"],
                question.get("difficulty", "medium"),
            ),
        )
        stored_questions.append({**question, "id": cursor.lastrowid, "quiz_set_id": quiz_set_id})
    return {
        "id": quiz_set_id,
        "course_id": course["id"],
        "title": title,
        "course_name": course["name"],
        "purpose": purpose,
        "questions": stored_questions,
    }


def get_quiz_set(cursor, quiz_set_id: int, user_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, user_id, course_id, title, course_name, topic, purpose, created_at
        FROM quiz_sets
        WHERE id = %s AND user_id = %s
        """,
        (quiz_set_id, user_id),
    )
    quiz = cursor.fetchone()
    if quiz is None:
        return None
    cursor.execute(
        """
        SELECT id, quiz_set_id, knowledge_point_id, question_type,
               question, answer, difficulty, created_at
        FROM quiz_questions
        WHERE quiz_set_id = %s
        ORDER BY id
        """,
        (quiz_set_id,),
    )
    quiz["questions"] = list(cursor.fetchall())
    cursor.execute(
        """
        SELECT EXISTS(
            SELECT 1 FROM learning_evaluations
            WHERE user_id = %s AND quiz_set_id = %s
        ) AS submitted
        """,
        (user_id, quiz_set_id),
    )
    quiz["submitted"] = bool(cursor.fetchone()["submitted"])
    return quiz


def get_latest_diagnostic_id(cursor, user_id: int, course_id: int) -> int | None:
    cursor.execute(
        """
        SELECT id FROM quiz_sets
        WHERE user_id = %s AND course_id = %s AND purpose = 'diagnostic'
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, course_id),
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def get_latest_practice_id(cursor, user_id: int, course_id: int) -> int | None:
    cursor.execute(
        """
        SELECT id FROM quiz_sets
        WHERE user_id = %s AND course_id = %s AND purpose = 'practice'
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, course_id),
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def create_evaluation(
    cursor,
    user_id: int,
    course_id: int,
    quiz_set_id: int,
    evaluation: dict,
) -> int:
    cursor.execute(
        """
        INSERT INTO learning_evaluations
            (user_id, course_id, quiz_set_id, score, level,
             weak_points_json, suggestions_json, evaluation_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            course_id,
            quiz_set_id,
            evaluation["score"],
            evaluation["level"],
            json.dumps(evaluation.get("weak_points", []), ensure_ascii=False),
            json.dumps(evaluation.get("suggestions", []), ensure_ascii=False),
            json.dumps(evaluation, ensure_ascii=False),
        ),
    )
    return cursor.lastrowid


def get_evaluation_attempt(cursor, user_id: int, attempt_key: str, *, for_update: bool = False) -> dict | None:
    lock = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT id, user_id, course_id, quiz_set_id, study_session_id,
               attempt_key, request_hash, status, evaluation_id, result_json, error_message,
               started_at, completed_at, created_at, updated_at
        FROM evaluation_attempts
        WHERE user_id = %s AND attempt_key = %s{lock}
        """,
        (user_id, attempt_key),
    )
    row = cursor.fetchone()
    if row and row.get("result_json") is not None:
        row["result"] = json.loads(row.pop("result_json"))
    elif row:
        row.pop("result_json", None)
        row["result"] = None
    return row


def claim_evaluation_attempt(
    cursor,
    *,
    user_id: int,
    course_id: int,
    quiz_set_id: int,
    study_session_id: int | None,
    attempt_key: str,
    request_hash: str,
    started_at,
    stale_before,
) -> tuple[dict, bool]:
    """Claim exactly one model-evaluation attempt for a quiz.

    A failed or abandoned attempt can be reclaimed. Completed attempts are
    returned to the caller so retries can serve the persisted result.
    """
    cursor.execute(
        """
        INSERT IGNORE INTO evaluation_attempts
            (user_id, course_id, quiz_set_id, study_session_id, attempt_key,
             request_hash, status, started_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'evaluating', %s)
        """,
        (user_id, course_id, quiz_set_id, study_session_id, attempt_key, request_hash, started_at),
    )
    if cursor.rowcount:
        created = get_evaluation_attempt(cursor, user_id, attempt_key, for_update=True)
        if created is None:
            raise RuntimeError("evaluation attempt insert succeeded but the row was not found")
        return created, True

    attempt = get_evaluation_attempt(cursor, user_id, attempt_key, for_update=True)
    if attempt is None:
        raise RuntimeError("evaluation attempt could not be claimed or loaded")
    reclaimable = (
        attempt["status"] == "failed"
        or (attempt["status"] == "evaluating" and attempt["updated_at"] < stale_before)
    )
    if reclaimable:
        cursor.execute(
            """
            UPDATE evaluation_attempts
            SET study_session_id = %s, request_hash = %s, status = 'evaluating',
                evaluation_id = NULL, result_json = NULL, error_message = NULL,
                started_at = %s, completed_at = NULL
            WHERE id = %s
            """,
            (study_session_id, request_hash, started_at, attempt["id"]),
        )
        reclaimed = get_evaluation_attempt(cursor, user_id, attempt_key, for_update=True)
        if reclaimed is None:
            raise RuntimeError("evaluation attempt reclaim succeeded but the row was not found")
        return reclaimed, True
    return attempt, False


def finish_evaluation_attempt(
    cursor,
    attempt_id: int,
    evaluation_id: int,
    result: dict,
    completed_at,
) -> None:
    cursor.execute(
        """
        UPDATE evaluation_attempts
        SET status = 'completed', evaluation_id = %s, result_json = %s,
            error_message = NULL, completed_at = %s
        WHERE id = %s AND status = 'evaluating'
        """,
        (evaluation_id, json.dumps(result, ensure_ascii=False, default=str), completed_at, attempt_id),
    )


def update_evaluation_attempt_result(cursor, attempt_id: int, result: dict) -> None:
    cursor.execute(
        "UPDATE evaluation_attempts SET result_json = %s WHERE id = %s AND status = 'completed'",
        (json.dumps(result, ensure_ascii=False, default=str), attempt_id),
    )


def fail_evaluation_attempt(cursor, attempt_id: int, error_message: str, completed_at) -> None:
    cursor.execute(
        """
        UPDATE evaluation_attempts
        SET status = 'failed', error_message = %s, completed_at = %s
        WHERE id = %s AND status = 'evaluating'
        """,
        (error_message[:2000], completed_at, attempt_id),
    )


def create_evaluation_answer(
    cursor,
    evaluation_id: int,
    question: dict,
    review: dict,
) -> None:
    cursor.execute(
        """
        INSERT INTO evaluation_answers
            (evaluation_id, question_id, knowledge_point_id,
             user_answer, score, feedback)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            evaluation_id,
            question["id"],
            question.get("knowledge_point_id"),
            review["user_answer"],
            review["score"],
            review.get("feedback", ""),
        ),
    )


def get_mastery(cursor, user_id: int, course_id: int, point_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, mastery, low_score_streak, last_evaluation_id
        FROM mastery_records
        WHERE user_id = %s AND course_id = %s AND knowledge_point_id = %s
        """,
        (user_id, course_id, point_id),
    )
    return cursor.fetchone()


def save_mastery(
    cursor,
    user_id: int,
    course_id: int,
    point_id: int,
    mastery: float,
    low_score_streak: int,
    evaluation_id: int,
) -> dict:
    cursor.execute(
        """
        INSERT INTO mastery_records
            (user_id, course_id, knowledge_point_id, mastery,
             low_score_streak, last_evaluation_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            mastery = VALUES(mastery),
            low_score_streak = VALUES(low_score_streak),
            last_evaluation_id = VALUES(last_evaluation_id),
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, course_id, point_id, mastery, low_score_streak, evaluation_id),
    )
    mastery_row = get_mastery(cursor, user_id, course_id, point_id)
    if mastery_row is None:
        raise RuntimeError("mastery upsert succeeded but the row could not be reloaded")
    return mastery_row


def create_mastery_change(
    cursor,
    mastery_record_id: int,
    evaluation_id: int,
    before: float,
    after: float,
    reason: str,
) -> int:
    cursor.execute(
        """
        INSERT INTO mastery_changes
            (mastery_record_id, evaluation_id, before_value, after_value, reason)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (mastery_record_id, evaluation_id, before, after, reason),
    )
    return cursor.lastrowid


def archive_active_plans(cursor, user_id: int, course_id: int) -> None:
    cursor.execute(
        """
        UPDATE study_plans
        SET status = 'archived'
        WHERE user_id = %s AND course_id = %s AND status IN ('draft', 'active')
        """,
        (user_id, course_id),
    )


def create_plan(cursor, user_id: int, course_id: int, title: str, start: date, end: date) -> int:
    cursor.execute(
        """
        INSERT INTO study_plans
            (user_id, course_id, title, start_date, end_date, status)
        VALUES (%s, %s, %s, %s, %s, 'active')
        """,
        (user_id, course_id, title, start, end),
    )
    return cursor.lastrowid


def create_session(
    cursor,
    user_id: int,
    course_id: int,
    plan_id: int | None,
    scheduled_date: date,
    estimated_minutes: int,
) -> int:
    cursor.execute(
        """
        INSERT INTO study_sessions
            (user_id, course_id, plan_id, scheduled_date, estimated_minutes, status)
        VALUES (%s, %s, %s, %s, %s, 'planned')
        """,
        (user_id, course_id, plan_id, scheduled_date, estimated_minutes),
    )
    return cursor.lastrowid


def add_session_item(
    cursor,
    session_id: int,
    point_id: int | None,
    item_type: str,
    title: str,
    content_ref: dict,
    sort_order: int,
    source_key: str | None = None,
) -> int:
    if source_key:
        cursor.execute(
            "SELECT id FROM study_session_items WHERE session_id = %s AND source_key = %s",
            (session_id, source_key),
        )
        existing = cursor.fetchone()
        if existing:
            return existing["id"]
    cursor.execute(
        """
        INSERT INTO study_session_items
            (session_id, knowledge_point_id, item_type, title,
             content_ref, sort_order, status, source_key)
        VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
        """,
        (
            session_id,
            point_id,
            item_type,
            title,
            json.dumps(content_ref, ensure_ascii=False),
            sort_order,
            source_key,
        ),
    )
    return cursor.lastrowid


def get_session(cursor, session_id: int, user_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, user_id, course_id, plan_id, scheduled_date,
               estimated_minutes, actual_minutes, status, adaptation_reason,
               started_at, completed_at, created_at, updated_at
        FROM study_sessions
        WHERE id = %s AND user_id = %s
        """,
        (session_id, user_id),
    )
    session = cursor.fetchone()
    if session is None:
        return None
    session["items"] = list_session_items(cursor, session_id)
    return session


def list_session_items(cursor, session_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT item.id, item.session_id, item.knowledge_point_id,
               item.item_type, item.title, item.content_ref,
               item.sort_order, item.status, item.source_key,
               kp.name AS knowledge_point_name
        FROM study_session_items item
        LEFT JOIN knowledge_points kp ON kp.id = item.knowledge_point_id
        WHERE item.session_id = %s
        ORDER BY item.sort_order, item.id
        """,
        (session_id,),
    )
    items = []
    for row in cursor.fetchall():
        row["content_ref"] = json.loads(row.get("content_ref") or "{}")
        items.append(row)
    return items


def get_today_session(cursor, user_id: int, course_id: int, today: date) -> dict | None:
    cursor.execute(
        """
        SELECT id
        FROM study_sessions
        WHERE user_id = %s AND course_id = %s AND scheduled_date = %s
          AND status IN ('planned', 'in_progress', 'completed', 'evaluated')
        ORDER BY scheduled_date, id
        LIMIT 1
        """,
        (user_id, course_id, today),
    )
    row = cursor.fetchone()
    return get_session(cursor, row["id"], user_id) if row else None


def get_latest_question_for_point(
    cursor,
    user_id: int,
    course_id: int,
    point_id: int,
) -> dict | None:
    cursor.execute(
        """
        SELECT qq.id, qq.quiz_set_id, qq.knowledge_point_id,
               qq.question_type, qq.question, qq.answer, qq.difficulty
        FROM quiz_questions qq
        JOIN quiz_sets qs ON qs.id = qq.quiz_set_id
        WHERE qs.user_id = %s AND qs.course_id = %s
          AND qq.knowledge_point_id = %s
        ORDER BY qq.id DESC
        LIMIT 1
        """,
        (user_id, course_id, point_id),
    )
    return cursor.fetchone()


def update_session_status(
    cursor,
    session_id: int,
    user_id: int,
    status: str,
    actual_minutes: int | None = None,
) -> None:
    if status == "in_progress":
        cursor.execute(
            """
            UPDATE study_sessions SET status = %s, started_at = COALESCE(started_at, NOW())
            WHERE id = %s AND user_id = %s
            """,
            (status, session_id, user_id),
        )
    else:
        cursor.execute(
            """
            UPDATE study_sessions
            SET status = %s, actual_minutes = COALESCE(%s, actual_minutes), completed_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (status, actual_minutes, session_id, user_id),
        )


def get_questions_by_ids(cursor, question_ids: list[int], user_id: int) -> list[dict]:
    if not question_ids:
        return []
    placeholders = ",".join(["%s"] * len(question_ids))
    cursor.execute(
        f"""
        SELECT qq.id, qq.quiz_set_id, qq.knowledge_point_id,
               qq.question_type, qq.question, qq.answer, qq.difficulty,
               qs.title AS quiz_title, qs.course_id
        FROM quiz_questions qq
        JOIN quiz_sets qs ON qs.id = qq.quiz_set_id
        WHERE qq.id IN ({placeholders}) AND qs.user_id = %s
        ORDER BY qq.id
        """,
        (*question_ids, user_id),
    )
    return list(cursor.fetchall())


def get_or_create_session_for_date(
    cursor,
    user_id: int,
    course_id: int,
    scheduled_date: date,
    estimated_minutes: int,
) -> int:
    cursor.execute(
        """
        SELECT id, plan_id FROM study_sessions
        WHERE user_id = %s AND course_id = %s AND scheduled_date = %s
        ORDER BY id LIMIT 1
        """,
        (user_id, course_id, scheduled_date),
    )
    existing = cursor.fetchone()
    if existing:
        return existing["id"]
    cursor.execute(
        """
        SELECT id FROM study_plans
        WHERE user_id = %s AND course_id = %s AND status = 'active'
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, course_id),
    )
    plan = cursor.fetchone()
    return create_session(
        cursor,
        user_id,
        course_id,
        plan["id"] if plan else None,
        scheduled_date,
        estimated_minutes,
    )


def set_session_adaptation_reason(cursor, session_id: int, reason: str) -> None:
    cursor.execute(
        "UPDATE study_sessions SET adaptation_reason = %s WHERE id = %s",
        (reason, session_id),
    )


def reschedule_session(
    cursor,
    session_id: int,
    user_id: int,
    scheduled_date: date,
    estimated_minutes: int | None = None,
) -> dict | None:
    cursor.execute(
        """
        UPDATE study_sessions
        SET scheduled_date = %s,
            estimated_minutes = COALESCE(%s, estimated_minutes),
            adaptation_reason = %s
        WHERE id = %s AND user_id = %s
          AND status IN ('planned', 'in_progress')
        """,
        (
            scheduled_date,
            estimated_minutes,
            f"用户调整至 {scheduled_date.isoformat()}",
            session_id,
            user_id,
        ),
    )
    return get_session(cursor, session_id, user_id) if cursor.rowcount else None


def get_course_plan(cursor, user_id: int, course_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, user_id, course_id, title, start_date, end_date,
               status, created_at, updated_at
        FROM study_plans
        WHERE user_id = %s AND course_id = %s AND status = 'active'
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, course_id),
    )
    plan = cursor.fetchone()
    if plan is None:
        return None
    cursor.execute(
        """
        SELECT id FROM study_sessions
        WHERE user_id = %s AND course_id = %s AND plan_id = %s
        ORDER BY scheduled_date, id
        """,
        (user_id, course_id, plan["id"]),
    )
    plan["sessions"] = [get_session(cursor, row["id"], user_id) for row in cursor.fetchall()]
    return plan


def practice_statistics(cursor, user_id: int, course_id: int) -> dict:
    cursor.execute(
        """
        SELECT COUNT(*) AS attempts, COALESCE(AVG(evaluation.score), 0) AS average_score,
               COALESCE(MAX(evaluation.score), 0) AS best_score
        FROM learning_evaluations evaluation
        JOIN quiz_sets quiz ON quiz.id = evaluation.quiz_set_id
        WHERE evaluation.user_id = %s AND evaluation.course_id = %s
          AND quiz.purpose IN ('practice', 'diagnostic')
        """,
        (user_id, course_id),
    )
    summary = cursor.fetchone()
    cursor.execute(
        """
        SELECT question.question_type, COUNT(*) AS total,
               ROUND(AVG(answer.score), 2) AS average_score
        FROM evaluation_answers answer
        JOIN learning_evaluations evaluation ON evaluation.id = answer.evaluation_id
        JOIN quiz_questions question ON question.id = answer.question_id
        WHERE evaluation.user_id = %s AND evaluation.course_id = %s
        GROUP BY question.question_type
        ORDER BY total DESC, question.question_type
        """,
        (user_id, course_id),
    )
    type_distribution = list(cursor.fetchall())
    cursor.execute(
        """
        SELECT evaluation.id, evaluation.score, evaluation.level,
               quiz.purpose, quiz.title, evaluation.created_at
        FROM learning_evaluations evaluation
        JOIN quiz_sets quiz ON quiz.id = evaluation.quiz_set_id
        WHERE evaluation.user_id = %s AND evaluation.course_id = %s
        ORDER BY evaluation.id DESC
        LIMIT 20
        """,
        (user_id, course_id),
    )
    trend = list(cursor.fetchall())
    trend.reverse()
    cursor.execute(
        """
        SELECT COUNT(*) AS answered,
               SUM(answer.score >= 60) AS passed,
               SUM(answer.score < 60) AS wrong
        FROM evaluation_answers answer
        JOIN learning_evaluations evaluation ON evaluation.id = answer.evaluation_id
        WHERE evaluation.user_id = %s AND evaluation.course_id = %s
        """,
        (user_id, course_id),
    )
    answers = cursor.fetchone()
    answered = int(answers["answered"] or 0)
    return {
        "attempts": int(summary["attempts"] or 0),
        "average_score": round(float(summary["average_score"] or 0), 2),
        "best_score": round(float(summary["best_score"] or 0), 2),
        "answered": answered,
        "passed": int(answers["passed"] or 0),
        "wrong": int(answers["wrong"] or 0),
        "accuracy": round(int(answers["passed"] or 0) / answered * 100, 2) if answered else 0,
        "type_distribution": type_distribution,
        "trend": trend,
    }


def list_wrong_answers(cursor, user_id: int, course_id: int, limit: int = 100) -> list[dict]:
    cursor.execute(
        """
        SELECT answer.id, answer.evaluation_id, answer.question_id,
               answer.knowledge_point_id, point.name AS knowledge_point_name,
               question.question_type, question.question, question.answer AS reference_answer,
               answer.user_answer, answer.score, answer.feedback, answer.created_at
        FROM evaluation_answers answer
        JOIN learning_evaluations evaluation ON evaluation.id = answer.evaluation_id
        JOIN quiz_questions question ON question.id = answer.question_id
        LEFT JOIN knowledge_points point ON point.id = answer.knowledge_point_id
        WHERE evaluation.user_id = %s AND evaluation.course_id = %s
          AND answer.score < 60
        ORDER BY answer.id DESC
        LIMIT %s
        """,
        (user_id, course_id, limit),
    )
    return list(cursor.fetchall())


def persist_practice_result_in_agent_message(
    cursor,
    user_id: int,
    course_id: int,
    quiz_set_id: int,
    result: dict,
) -> int | None:
    cursor.execute(
        """
        SELECT id, tool_calls
        FROM agent_chat_messages
        WHERE user_id = %s AND course_id = %s AND role = 'assistant'
          AND tool_calls IS NOT NULL
        ORDER BY id DESC
        LIMIT 100
        """,
        (user_id, course_id),
    )
    for row in cursor.fetchall():
        try:
            tool_calls = json.loads(row["tool_calls"])
        except (TypeError, json.JSONDecodeError):
            continue
        changed = False
        for card in tool_calls.get("cards") or []:
            practice = card.get("data") if card.get("type") == "practice" else None
            if practice and practice.get("id") == quiz_set_id:
                practice["submitted"] = True
                practice["result"] = result
                changed = True
        if changed:
            cursor.execute(
                "UPDATE agent_chat_messages SET tool_calls = %s WHERE id = %s AND user_id = %s",
                (json.dumps(tool_calls, ensure_ascii=False, default=str), row["id"], user_id),
            )
            return row["id"]
    return None


def progress_summary(cursor, user_id: int, course_id: int) -> dict:
    cursor.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(status IN ('completed', 'evaluated')) AS completed,
               COALESCE(SUM(actual_minutes), 0) AS actual_minutes
        FROM study_sessions
        WHERE user_id = %s AND course_id = %s
        """,
        (user_id, course_id),
    )
    sessions = cursor.fetchone()
    points = list_points_with_mastery(cursor, user_id, course_id)
    cursor.execute(
        """
        SELECT change_row.id, record.knowledge_point_id, point.name AS knowledge_point_name,
               change_row.before_value, change_row.after_value, change_row.reason,
               change_row.evaluation_id, change_row.created_at
        FROM mastery_changes change_row
        JOIN mastery_records record ON record.id = change_row.mastery_record_id
        JOIN knowledge_points point ON point.id = record.knowledge_point_id
        WHERE record.user_id = %s AND record.course_id = %s
        ORDER BY change_row.id DESC
        LIMIT 10
        """,
        (user_id, course_id),
    )
    recent_changes = list(cursor.fetchall())
    cursor.execute(
        """
        SELECT id FROM study_sessions
        WHERE user_id = %s AND course_id = %s
          AND scheduled_date >= CURRENT_DATE
          AND status IN ('planned', 'in_progress')
        ORDER BY scheduled_date, id
        LIMIT 3
        """,
        (user_id, course_id),
    )
    upcoming_sessions = [get_session(cursor, row["id"], user_id) for row in cursor.fetchall()]
    return {
        "session_total": sessions["total"] or 0,
        "session_completed": int(sessions["completed"] or 0),
        "actual_minutes": int(sessions["actual_minutes"] or 0),
        "knowledge_points": points,
        "weak_points": [point for point in points if float(point["mastery"]) < 60],
        "recent_changes": recent_changes,
        "upcoming_sessions": upcoming_sessions,
    }
