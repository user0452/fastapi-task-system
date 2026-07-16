import json
from datetime import date, datetime

from sqlalchemy import select

from app.models import model_as_dict, reflected_model


def _row(entity) -> dict | None:
    return model_as_dict(entity) if entity is not None else None


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
    QuizSet = reflected_model("quiz_sets")
    QuizQuestion = reflected_model("quiz_questions")
    quiz_json = json.dumps({"questions": questions, "purpose": purpose}, ensure_ascii=False)
    quiz_set = QuizSet(
        user_id=user_id,
        course_id=course["id"],
        title=title,
        course_name=course["name"],
        topic="课程诊断",
        quiz_json=quiz_json,
        purpose=purpose,
    )
    cursor.session.add(quiz_set)
    cursor.session.flush()
    stored_questions = []
    for question in questions:
        stored = QuizQuestion(
            quiz_set_id=quiz_set.id,
            knowledge_point_id=question["knowledge_point_id"],
            question_type=question.get("question_type", "short_answer"),
            question=question["question"],
            answer=question["answer"],
            difficulty=question.get("difficulty", "medium"),
        )
        cursor.session.add(stored)
        cursor.session.flush()
        stored_questions.append({**question, "id": stored.id, "quiz_set_id": quiz_set.id})
    return {
        "id": quiz_set.id,
        "course_id": course["id"],
        "title": title,
        "course_name": course["name"],
        "purpose": purpose,
        "questions": stored_questions,
    }


def get_quiz_set(cursor, quiz_set_id: int, user_id: int) -> dict | None:
    QuizSet = reflected_model("quiz_sets")
    QuizQuestion = reflected_model("quiz_questions")
    LearningEvaluation = reflected_model("learning_evaluations")
    quiz_model = cursor.session.scalar(
        select(QuizSet).where(QuizSet.id == quiz_set_id, QuizSet.user_id == user_id)
    )
    quiz = _row(quiz_model)
    if quiz is None:
        return None
    quiz["questions"] = [
        _row(question)
        for question in cursor.session.scalars(
            select(QuizQuestion).where(QuizQuestion.quiz_set_id == quiz_set_id).order_by(QuizQuestion.id)
        )
    ]
    quiz["submitted"] = cursor.session.scalar(
        select(LearningEvaluation.id)
        .where(LearningEvaluation.user_id == user_id, LearningEvaluation.quiz_set_id == quiz_set_id)
        .limit(1)
    ) is not None
    return quiz


def get_latest_diagnostic_id(cursor, user_id: int, course_id: int) -> int | None:
    QuizSet = reflected_model("quiz_sets")
    return cursor.session.scalar(
        select(QuizSet.id)
        .where(QuizSet.user_id == user_id, QuizSet.course_id == course_id, QuizSet.purpose == "diagnostic")
        .order_by(QuizSet.id.desc())
        .limit(1)
    )


def get_latest_practice_id(cursor, user_id: int, course_id: int) -> int | None:
    QuizSet = reflected_model("quiz_sets")
    return cursor.session.scalar(
        select(QuizSet.id)
        .where(QuizSet.user_id == user_id, QuizSet.course_id == course_id, QuizSet.purpose == "practice")
        .order_by(QuizSet.id.desc())
        .limit(1)
    )


def create_evaluation(
    cursor,
    user_id: int,
    course_id: int,
    quiz_set_id: int,
    evaluation: dict,
) -> int:
    LearningEvaluation = reflected_model("learning_evaluations")
    stored = LearningEvaluation(
        user_id=user_id,
        course_id=course_id,
        quiz_set_id=quiz_set_id,
        score=evaluation["score"],
        level=evaluation["level"],
        weak_points_json=json.dumps(evaluation.get("weak_points", []), ensure_ascii=False),
        suggestions_json=json.dumps(evaluation.get("suggestions", []), ensure_ascii=False),
        evaluation_json=json.dumps(evaluation, ensure_ascii=False),
    )
    cursor.session.add(stored)
    cursor.session.flush()
    return stored.id


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
    EvaluationAnswer = reflected_model("evaluation_answers")
    cursor.session.add(
        EvaluationAnswer(
            evaluation_id=evaluation_id,
            question_id=question["id"],
            knowledge_point_id=question.get("knowledge_point_id"),
            user_answer=review["user_answer"],
            score=review["score"],
            feedback=review.get("feedback", ""),
        )
    )


def get_mastery(cursor, user_id: int, course_id: int, point_id: int) -> dict | None:
    MasteryRecord = reflected_model("mastery_records")
    record = cursor.session.scalar(
        select(MasteryRecord).where(
            MasteryRecord.user_id == user_id,
            MasteryRecord.course_id == course_id,
            MasteryRecord.knowledge_point_id == point_id,
        )
    )
    row = _row(record)
    if row is None:
        return None
    return {
        "id": row["id"],
        "mastery": row["mastery"],
        "low_score_streak": row["low_score_streak"],
        "last_evaluation_id": row["last_evaluation_id"],
    }


def save_mastery(
    cursor,
    user_id: int,
    course_id: int,
    point_id: int,
    mastery: float,
    low_score_streak: int,
    evaluation_id: int,
) -> dict:
    MasteryRecord = reflected_model("mastery_records")
    session = cursor.session
    record = session.scalar(
        select(MasteryRecord)
        .where(
            MasteryRecord.user_id == user_id,
            MasteryRecord.course_id == course_id,
            MasteryRecord.knowledge_point_id == point_id,
        )
        .with_for_update()
    )
    if record is None:
        record = MasteryRecord(
            user_id=user_id,
            course_id=course_id,
            knowledge_point_id=point_id,
            mastery=mastery,
            low_score_streak=low_score_streak,
            last_evaluation_id=evaluation_id,
        )
        session.add(record)
    else:
        record.mastery = mastery
        record.low_score_streak = low_score_streak
        record.last_evaluation_id = evaluation_id
    session.flush()
    return {
        "id": record.id,
        "mastery": record.mastery,
        "low_score_streak": record.low_score_streak,
        "last_evaluation_id": record.last_evaluation_id,
    }


def create_mastery_change(
    cursor,
    mastery_record_id: int,
    evaluation_id: int,
    before: float,
    after: float,
    reason: str,
) -> int:
    MasteryChange = reflected_model("mastery_changes")
    change = MasteryChange(
        mastery_record_id=mastery_record_id,
        evaluation_id=evaluation_id,
        before_value=before,
        after_value=after,
        reason=reason,
    )
    cursor.session.add(change)
    cursor.session.flush()
    return change.id


def archive_active_plans(cursor, user_id: int, course_id: int) -> None:
    StudyPlan = reflected_model("study_plans")
    for plan in cursor.session.scalars(
        select(StudyPlan).where(
            StudyPlan.user_id == user_id,
            StudyPlan.course_id == course_id,
            StudyPlan.status.in_(("draft", "active")),
        )
    ):
        plan.status = "archived"


def create_plan(cursor, user_id: int, course_id: int, title: str, start: date, end: date) -> int:
    StudyPlan = reflected_model("study_plans")
    plan = StudyPlan(
        user_id=user_id,
        course_id=course_id,
        title=title,
        start_date=start,
        end_date=end,
        status="active",
    )
    cursor.session.add(plan)
    cursor.session.flush()
    return plan.id


def create_session(
    cursor,
    user_id: int,
    course_id: int,
    plan_id: int | None,
    scheduled_date: date,
    estimated_minutes: int,
) -> int:
    StudySession = reflected_model("study_sessions")
    session = StudySession(
        user_id=user_id,
        course_id=course_id,
        plan_id=plan_id,
        scheduled_date=scheduled_date,
        estimated_minutes=estimated_minutes,
        status="planned",
    )
    cursor.session.add(session)
    cursor.session.flush()
    return session.id


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
    StudySessionItem = reflected_model("study_session_items")
    if source_key:
        existing = cursor.session.scalar(
            select(StudySessionItem).where(
                StudySessionItem.session_id == session_id,
                StudySessionItem.source_key == source_key,
            )
        )
        if existing:
            return existing.id
    item = StudySessionItem(
        session_id=session_id,
        knowledge_point_id=point_id,
        item_type=item_type,
        title=title,
        content_ref=json.dumps(content_ref, ensure_ascii=False),
        sort_order=sort_order,
        status="pending",
        source_key=source_key,
    )
    cursor.session.add(item)
    cursor.session.flush()
    return item.id


def get_session(cursor, session_id: int, user_id: int) -> dict | None:
    StudySession = reflected_model("study_sessions")
    session_model = cursor.session.scalar(
        select(StudySession).where(StudySession.id == session_id, StudySession.user_id == user_id)
    )
    session = _row(session_model)
    if session is None:
        return None
    session["items"] = list_session_items(cursor, session_id)
    return session


def list_session_items(cursor, session_id: int) -> list[dict]:
    StudySessionItem = reflected_model("study_session_items")
    KnowledgePoint = reflected_model("knowledge_points")
    rows = cursor.session.execute(
        select(StudySessionItem, KnowledgePoint.name.label("knowledge_point_name"))
        .outerjoin(KnowledgePoint, KnowledgePoint.id == StudySessionItem.knowledge_point_id)
        .where(StudySessionItem.session_id == session_id)
        .order_by(StudySessionItem.sort_order, StudySessionItem.id)
    )
    items = []
    for item_model, point_name in rows:
        row = _row(item_model) or {}
        content_ref = row.get("content_ref")
        row["content_ref"] = json.loads(content_ref or "{}") if isinstance(content_ref, str) else content_ref or {}
        row["knowledge_point_name"] = point_name
        items.append(row)
    return items


def get_today_session(cursor, user_id: int, course_id: int, today: date) -> dict | None:
    StudySession = reflected_model("study_sessions")
    session_id = cursor.session.scalar(
        select(StudySession.id)
        .where(
            StudySession.user_id == user_id,
            StudySession.course_id == course_id,
            StudySession.scheduled_date == today,
            StudySession.status.in_(("planned", "in_progress", "completed", "evaluated")),
        )
        .order_by(StudySession.scheduled_date, StudySession.id)
        .limit(1)
    )
    return get_session(cursor, session_id, user_id) if session_id else None


def get_latest_question_for_point(
    cursor,
    user_id: int,
    course_id: int,
    point_id: int,
) -> dict | None:
    QuizQuestion = reflected_model("quiz_questions")
    QuizSet = reflected_model("quiz_sets")
    question = cursor.session.scalar(
        select(QuizQuestion)
        .join(QuizSet, QuizSet.id == QuizQuestion.quiz_set_id)
        .where(
            QuizSet.user_id == user_id,
            QuizSet.course_id == course_id,
            QuizQuestion.knowledge_point_id == point_id,
        )
        .order_by(QuizQuestion.id.desc())
        .limit(1)
    )
    return _row(question)


def update_session_status(
    cursor,
    session_id: int,
    user_id: int,
    status: str,
    actual_minutes: int | None = None,
) -> None:
    StudySession = reflected_model("study_sessions")
    session_model = cursor.session.scalar(
        select(StudySession).where(StudySession.id == session_id, StudySession.user_id == user_id)
    )
    if session_model is None:
        return
    if status == "in_progress":
        session_model.status = status
        session_model.started_at = session_model.started_at or datetime.now()
    else:
        session_model.status = status
        session_model.actual_minutes = actual_minutes if actual_minutes is not None else session_model.actual_minutes
        session_model.completed_at = datetime.now()


def get_questions_by_ids(cursor, question_ids: list[int], user_id: int) -> list[dict]:
    if not question_ids:
        return []
    QuizQuestion = reflected_model("quiz_questions")
    QuizSet = reflected_model("quiz_sets")
    rows = cursor.session.execute(
        select(QuizQuestion, QuizSet.title.label("quiz_title"), QuizSet.course_id)
        .join(QuizSet, QuizSet.id == QuizQuestion.quiz_set_id)
        .where(QuizQuestion.id.in_(question_ids), QuizSet.user_id == user_id)
        .order_by(QuizQuestion.id)
    )
    questions = []
    for question, quiz_title, course_id in rows:
        row = _row(question) or {}
        row["quiz_title"] = quiz_title
        row["course_id"] = course_id
        questions.append(row)
    return questions


def get_or_create_session_for_date(
    cursor,
    user_id: int,
    course_id: int,
    scheduled_date: date,
    estimated_minutes: int,
) -> int:
    StudySession = reflected_model("study_sessions")
    StudyPlan = reflected_model("study_plans")
    existing = cursor.session.scalar(
        select(StudySession)
        .where(
            StudySession.user_id == user_id,
            StudySession.course_id == course_id,
            StudySession.scheduled_date == scheduled_date,
        )
        .order_by(StudySession.id)
        .limit(1)
    )
    if existing:
        return existing.id
    plan_id = cursor.session.scalar(
        select(StudyPlan.id)
        .where(StudyPlan.user_id == user_id, StudyPlan.course_id == course_id, StudyPlan.status == "active")
        .order_by(StudyPlan.id.desc())
        .limit(1)
    )
    return create_session(
        cursor,
        user_id,
        course_id,
        plan_id,
        scheduled_date,
        estimated_minutes,
    )


def set_session_adaptation_reason(cursor, session_id: int, reason: str) -> None:
    StudySession = reflected_model("study_sessions")
    session_model = cursor.session.get(StudySession, session_id)
    if session_model is not None:
        session_model.adaptation_reason = reason


def reschedule_session(
    cursor,
    session_id: int,
    user_id: int,
    scheduled_date: date,
    estimated_minutes: int | None = None,
) -> dict | None:
    StudySession = reflected_model("study_sessions")
    session_model = cursor.session.scalar(
        select(StudySession).where(
            StudySession.id == session_id,
            StudySession.user_id == user_id,
            StudySession.status.in_(("planned", "in_progress")),
        )
    )
    if session_model is None:
        return None
    session_model.scheduled_date = scheduled_date
    if estimated_minutes is not None:
        session_model.estimated_minutes = estimated_minutes
    session_model.adaptation_reason = f"用户调整至 {scheduled_date.isoformat()}"
    cursor.session.flush()
    return get_session(cursor, session_id, user_id)


def get_course_plan(cursor, user_id: int, course_id: int) -> dict | None:
    StudyPlan = reflected_model("study_plans")
    StudySession = reflected_model("study_sessions")
    plan_model = cursor.session.scalar(
        select(StudyPlan)
        .where(StudyPlan.user_id == user_id, StudyPlan.course_id == course_id, StudyPlan.status == "active")
        .order_by(StudyPlan.id.desc())
        .limit(1)
    )
    plan = _row(plan_model)
    if plan is None:
        return None
    session_ids = cursor.session.scalars(
        select(StudySession.id)
        .where(
            StudySession.user_id == user_id,
            StudySession.course_id == course_id,
            StudySession.plan_id == plan["id"],
        )
        .order_by(StudySession.scheduled_date, StudySession.id)
    )
    plan["sessions"] = [get_session(cursor, session_id, user_id) for session_id in session_ids]
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
