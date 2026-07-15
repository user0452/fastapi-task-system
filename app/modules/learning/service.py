import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.llm.diagnostic_generator import generate_diagnostic_questions
from app.integrations.llm.evaluation import evaluate_quiz_answers
from app.integrations.llm.practice_generator import generate_practice_questions
from app.modules.audit.service import record_audit
from app.modules.courses import repository as course_repository
from app.modules.courses.service import get_user_course
from app.modules.learning import repository


def _public_quiz(quiz: dict) -> dict:
    public = dict(quiz)
    public["questions"] = [
        {key: value for key, value in question.items() if key != "answer"}
        for question in quiz.get("questions", [])
    ]
    return public


def get_diagnostic(user_id: int, quiz_set_id: int) -> dict:
    with get_cursor() as cursor:
        quiz = repository.get_quiz_set(cursor, quiz_set_id, user_id)
    if quiz is None or quiz.get("purpose") != "diagnostic":
        raise AppError("诊断题不存在或无访问权限", 404, "DIAGNOSTIC_NOT_FOUND")
    record_audit(user_id, "COURSE_DIAGNOSTIC_VIEWED", "quiz_set", quiz_set_id, {"course_id": quiz["course_id"]})
    return _public_quiz(quiz)


def get_latest_course_diagnostic(user_id: int, course_id: int) -> dict | None:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        quiz_set_id = repository.get_latest_diagnostic_id(cursor, user_id, course_id)
        quiz = repository.get_quiz_set(cursor, quiz_set_id, user_id) if quiz_set_id else None
        record_audit(
            user_id,
            "COURSE_DIAGNOSTIC_VIEWED",
            "course",
            course_id,
            {"quiz_set_id": quiz_set_id},
            cursor=cursor,
        )
    return _public_quiz(quiz) if quiz else None


def generate_diagnostic(
    user_id: int,
    course_id: int,
    question_count: int = 6,
    question_provider: Callable = generate_diagnostic_questions,
) -> dict:
    course = get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        points = repository.list_points_with_mastery(cursor, user_id, course_id)
    if len(points) < 3:
        raise AppError(
            "至少需要 3 个知识点才能生成诊断题，请先完成资料处理",
            409,
            "KNOWLEDGE_POINTS_NOT_READY",
        )
    questions = question_provider(course, points, question_count)
    covered = {item["knowledge_point_id"] for item in questions}
    if len(questions) < 5 or len(covered) < 3:
        raise AppError("诊断题未覆盖足够知识点", 502, "DIAGNOSTIC_GENERATION_INVALID")
    with get_cursor() as cursor:
        quiz = repository.create_quiz_set(
            cursor,
            user_id,
            course,
            f"{course['name']}入门诊断",
            "diagnostic",
            questions[:question_count],
        )
        record_audit(
            user_id,
            "COURSE_DIAGNOSTIC_GENERATED",
            "quiz_set",
            quiz["id"],
            {"course_id": course_id, "question_count": len(quiz["questions"])},
            cursor=cursor,
        )
    return _public_quiz(quiz)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _evaluation_request_hash(quiz_set_id: int, answers: list[dict]) -> str:
    canonical: list[dict[str, Any]] = sorted(
        (
            {"question_id": int(item["question_id"]), "user_answer": str(item.get("user_answer") or "").strip()}
            for item in answers
        ),
        key=lambda item: int(item["question_id"]),
    )
    payload = json.dumps(
        {"quiz_set_id": quiz_set_id, "answers": canonical},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evaluation_attempt_key(quiz_set_id: int, study_session_id: int | None = None) -> str:
    if study_session_id is None:
        return f"quiz:{quiz_set_id}"
    return f"session:{study_session_id}:quiz:{quiz_set_id}"


def _claim_evaluation(
    user_id: int,
    course_id: int,
    quiz_set_id: int,
    answers: list[dict],
    study_session_id: int | None = None,
) -> tuple[dict, dict | None]:
    now = _utc_now()
    request_hash = _evaluation_request_hash(quiz_set_id, answers)
    attempt_key = _evaluation_attempt_key(quiz_set_id, study_session_id)
    with get_cursor() as cursor:
        attempt, claimed = repository.claim_evaluation_attempt(
            cursor,
            user_id=user_id,
            course_id=course_id,
            quiz_set_id=quiz_set_id,
            study_session_id=study_session_id,
            attempt_key=attempt_key,
            request_hash=request_hash,
            started_at=now,
            stale_before=now - timedelta(minutes=3),
        )
    if claimed:
        return attempt, None
    if attempt and attempt["status"] == "completed":
        if attempt["request_hash"] != request_hash:
            raise AppError("该题集已经使用另一份答案提交", 409, "EVALUATION_ALREADY_SUBMITTED")
        return attempt, attempt.get("result")
    raise AppError("答案正在评分，请勿重复提交", 409, "EVALUATION_IN_PROGRESS")


def _run_evaluator(attempt: dict, quiz: dict, answers: list[dict], evaluator: Callable) -> dict:
    try:
        return evaluator(
            quiz_set_id=quiz["id"],
            quiz_title=quiz["title"],
            questions=quiz["questions"],
            user_answers=answers,
            profile=None,
        )
    except Exception as exc:
        with get_cursor() as cursor:
            repository.fail_evaluation_attempt(cursor, attempt["id"], str(exc), _utc_now())
        raise


def _persist_evaluation_and_update_mastery(
    cursor,
    user_id: int,
    course_id: int,
    quiz: dict,
    evaluation: dict,
    initial: bool,
) -> tuple[dict, list[dict]]:
    evaluation_id = repository.create_evaluation(
        cursor,
        user_id,
        course_id,
        quiz["id"],
        evaluation,
    )
    evaluation["id"] = evaluation_id

    question_map = {question["id"]: question for question in quiz["questions"]}
    scores_by_point: dict[int, list[float]] = defaultdict(list)
    for review in evaluation.get("question_reviews", []):
        question = question_map.get(review["question_id"])
        if question is None:
            continue
        repository.create_evaluation_answer(cursor, evaluation_id, question, review)
        point_id = question.get("knowledge_point_id")
        if point_id:
            scores_by_point[point_id].append(float(review["score"]))

    changes = []
    for point_id, scores in scores_by_point.items():
        assessment_score = sum(scores) / len(scores)
        existing = repository.get_mastery(cursor, user_id, course_id, point_id)
        before = float(existing["mastery"]) if existing else 0.0
        after = assessment_score if initial or existing is None else before * 0.7 + assessment_score * 0.3
        after = round(max(0.0, min(100.0, after)), 2)
        old_streak = int(existing["low_score_streak"]) if existing else 0
        low_score_streak = old_streak + 1 if assessment_score < 60 else 0
        reason = (
            f"诊断得分 {assessment_score:.1f}，建立初始掌握度"
            if initial or existing is None
            else f"原掌握度 {before:.1f} × 0.7 + 本次得分 {assessment_score:.1f} × 0.3"
        )
        record = repository.save_mastery(
            cursor,
            user_id,
            course_id,
            point_id,
            after,
            low_score_streak,
            evaluation_id,
        )
        change_id = repository.create_mastery_change(
            cursor,
            record["id"],
            evaluation_id,
            before,
            after,
            reason,
        )
        changes.append(
            {
                "id": change_id,
                "knowledge_point_id": point_id,
                "assessment_score": round(assessment_score, 2),
                "before": before,
                "after": after,
                "reason": reason,
                "evaluation_id": evaluation_id,
                "low_score_streak": low_score_streak,
            }
        )
    return evaluation, changes


def _plan_length(course: dict) -> int:
    exam_at = course.get("exam_at")
    if not exam_at:
        return 7
    remaining = (exam_at.date() - date.today()).days + 1
    return max(3, min(14, remaining)) if remaining > 0 else 3


def generate_study_plan(user_id: int, course_id: int, diagnostic_quiz: dict | None = None) -> dict:
    course = get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        points = repository.list_points_with_mastery(cursor, user_id, course_id)
    if not points:
        raise AppError("课程尚未建立知识点", 409, "KNOWLEDGE_POINTS_NOT_READY")

    question_by_point: dict[int, dict] = {}
    diagnostic_quiz_id = diagnostic_quiz.get("id") if diagnostic_quiz else None
    if diagnostic_quiz:
        for question in diagnostic_quiz.get("questions", []):
            question_by_point.setdefault(question.get("knowledge_point_id"), question)
        covered_points = [point for point in points if point["id"] in question_by_point]
        if covered_points:
            points = covered_points

    days = _plan_length(course)
    start = date.today()
    end = start + timedelta(days=days - 1)
    session_ids = []
    with get_cursor() as cursor:
        repository.archive_active_plans(cursor, user_id, course_id)
        plan_id = repository.create_plan(
            cursor,
            user_id,
            course_id,
            f"{course['name']}冲刺计划",
            start,
            end,
        )
        for day_index in range(days):
            point = points[day_index % len(points)]
            session_id = repository.create_session(
                cursor,
                user_id,
                course_id,
                plan_id,
                start + timedelta(days=day_index),
                course["daily_minutes"],
            )
            session_ids.append(session_id)
            repository.add_session_item(
                cursor,
                session_id,
                point["id"],
                "explanation",
                f"学习：{point['name']}",
                {"knowledge_point_id": point["id"]},
                0,
                f"plan:explanation:{point['id']}",
            )
            question = question_by_point.get(point["id"])
            if question and diagnostic_quiz_id is not None:
                repository.add_session_item(
                    cursor,
                    session_id,
                    point["id"],
                    "practice",
                    f"练习：{point['name']}",
                    {
                        "quiz_set_id": diagnostic_quiz_id,
                        "question_id": question["id"],
                    },
                    1,
                    f"plan:practice:{question['id']}",
                )
        repository.set_session_adaptation_reason(cursor, session_ids[0], "根据诊断掌握度生成首日学习内容")
        cursor.execute(
            "UPDATE courses SET status = 'active' WHERE id = %s AND user_id = %s",
            (course_id, user_id),
        )
        sessions = [repository.get_session(cursor, session_id, user_id) for session_id in session_ids]
        record_audit(
            user_id,
            "COURSE_PLAN_GENERATED",
            "study_plan",
            plan_id,
            {"course_id": course_id, "days": days},
            cursor=cursor,
        )
    return {
        "id": plan_id,
        "course_id": course_id,
        "title": f"{course['name']}冲刺计划",
        "start_date": start,
        "end_date": end,
        "days": days,
        "status": "active",
        "sessions": sessions,
    }


def submit_diagnostic(
    user_id: int,
    quiz_set_id: int,
    answers: list[dict],
    evaluator: Callable = evaluate_quiz_answers,
) -> dict:
    with get_cursor() as cursor:
        quiz = repository.get_quiz_set(cursor, quiz_set_id, user_id)
        if quiz is None or quiz.get("purpose") != "diagnostic":
            raise AppError("诊断题不存在或无访问权限", 404, "DIAGNOSTIC_NOT_FOUND")
        if quiz.get("submitted"):
            attempt = repository.get_evaluation_attempt(
                cursor, user_id, _evaluation_attempt_key(quiz_set_id)
            )
            if attempt and attempt["status"] == "completed" and attempt.get("result"):
                return attempt["result"]
            raise AppError("诊断已经提交，请直接进入今日学习", 409, "DIAGNOSTIC_ALREADY_SUBMITTED")
        allowed_ids = {question["id"] for question in quiz["questions"]}
        submitted = [item for item in answers if item["question_id"] in allowed_ids]
        if not submitted:
            raise AppError("至少填写一道诊断题答案", 400, "ANSWERS_REQUIRED")

    attempt, cached = _claim_evaluation(
        user_id,
        quiz["course_id"],
        quiz_set_id,
        submitted,
    )
    if cached is not None:
        return cached
    evaluation = _run_evaluator(attempt, quiz, submitted, evaluator)

    with get_cursor() as cursor:
        current = repository.get_quiz_set(cursor, quiz_set_id, user_id)
        if current is None or current.get("purpose") != "diagnostic":
            raise AppError("诊断题不存在或无访问权限", 404, "DIAGNOSTIC_NOT_FOUND")
        if current.get("submitted"):
            raise AppError("诊断已经提交，请直接进入今日学习", 409, "DIAGNOSTIC_ALREADY_SUBMITTED")
        evaluation, changes = _persist_evaluation_and_update_mastery(
            cursor,
            user_id,
            quiz["course_id"],
            quiz,
            evaluation,
            initial=True,
        )
        result = {"evaluation": evaluation, "mastery_changes": changes}
        repository.finish_evaluation_attempt(
            cursor,
            attempt["id"],
            evaluation["id"],
            result,
            _utc_now(),
        )
        record_audit(
            user_id,
            "COURSE_DIAGNOSTIC_SUBMITTED",
            "quiz_set",
            quiz_set_id,
            {"course_id": quiz["course_id"], "score": evaluation["score"]},
            cursor=cursor,
        )
    plan = generate_study_plan(user_id, quiz["course_id"], quiz)
    result["plan"] = plan
    with get_cursor() as cursor:
        repository.update_evaluation_attempt_result(cursor, attempt["id"], result)
    return result


def _hydrate_session_questions(cursor, session: dict, user_id: int) -> dict:
    question_ids = [
        item["content_ref"].get("question_id")
        for item in session.get("items", [])
        if item["content_ref"].get("question_id")
    ]
    questions = repository.get_questions_by_ids(cursor, question_ids, user_id)
    question_map = {item["id"]: item for item in questions}
    for item in session.get("items", []):
        question_id = item["content_ref"].get("question_id")
        if question_id in question_map:
            question = question_map[question_id]
            item["question"] = {
                key: question[key]
                for key in ["id", "knowledge_point_id", "question_type", "question", "difficulty"]
            }
    return session


def get_today_learning(user_id: int, course_id: int) -> dict | None:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        session = repository.get_today_session(cursor, user_id, course_id, date.today())
        hydrated = _hydrate_session_questions(cursor, session, user_id) if session else None
        record_audit(
            user_id,
            "COURSE_TODAY_VIEWED",
            "course",
            course_id,
            {"session_id": session["id"] if session else None},
            cursor=cursor,
        )
        return hydrated


def start_learning_session(user_id: int, session_id: int) -> dict:
    with get_cursor() as cursor:
        session = repository.get_session(cursor, session_id, user_id)
        if session is None:
            raise AppError("学习单元不存在或无访问权限", 404, "SESSION_NOT_FOUND")
        repository.update_session_status(cursor, session_id, user_id, "in_progress")
        refreshed = repository.get_session(cursor, session_id, user_id)
        if refreshed is None:
            raise AppError("Learning session no longer exists", 404, "SESSION_NOT_FOUND")
        hydrated = _hydrate_session_questions(
            cursor,
            refreshed,
            user_id,
        )
        record_audit(
            user_id,
            "COURSE_SESSION_STARTED",
            "study_session",
            session_id,
            {"course_id": session["course_id"]},
            cursor=cursor,
        )
        return hydrated


def _adapt_next_session(cursor, user_id: int, course: dict, change: dict, point_name: str) -> dict:
    tomorrow = date.today() + timedelta(days=1)
    session_id = repository.get_or_create_session_for_date(
        cursor,
        user_id,
        course["id"],
        tomorrow,
        course["daily_minutes"],
    )
    after = change["after"]
    question = repository.get_latest_question_for_point(
        cursor,
        user_id,
        course["id"],
        change["knowledge_point_id"],
    )
    question_ref = (
        {"quiz_set_id": question["quiz_set_id"], "question_id": question["id"]}
        if question
        else {}
    )
    if after < 60:
        reason = f"{point_name}掌握度为 {after:.1f}，次日增加复习、基础讲解和基础题"
        item_specs = [
            ("review", f"重点复习：{point_name}", {"mode": "review"}, -40),
            ("explanation", f"基础讲解：{point_name}", {"mode": "basic"}, -30),
            (
                "practice",
                f"基础练习：{point_name}",
                {**question_ref, "difficulty": "basic"},
                -10,
            ),
        ]
        if change["low_score_streak"] >= 2:
            reason += "；已连续两次低于 60，增加例题并降低新知识内容占比"
            item_specs.insert(
                2,
                (
                    "worked_example",
                    f"例题拆解：{point_name}",
                    {**question_ref, "mode": "worked_example"},
                    -20,
                ),
            )
    elif after <= 80:
        reason = f"{point_name}掌握度为 {after:.1f}，保持难度继续练习"
        item_specs = [
            (
                "practice",
                f"继续巩固：{point_name}",
                {**question_ref, "difficulty": "medium"},
                -10,
            )
        ]
    else:
        reason = f"{point_name}掌握度为 {after:.1f}，进入进阶应用"
        item_specs = [
            (
                "advanced",
                f"进阶应用：{point_name}",
                {**question_ref, "difficulty": "advanced"},
                -10,
            )
        ]

    item_ids = []
    for item_type, title, content_ref, sort_order in item_specs:
        item_ids.append(
            repository.add_session_item(
                cursor,
                session_id,
                change["knowledge_point_id"],
                item_type,
                title,
                {
                    **content_ref,
                    "mastery_change_id": change["id"],
                    "reason": reason,
                },
                sort_order,
                (
                    f"adapt:{change['evaluation_id']}:"
                    f"{change['knowledge_point_id']}:{item_type}"
                ),
            )
        )
    repository.set_session_adaptation_reason(cursor, session_id, reason)
    return {
        "session_id": session_id,
        "knowledge_point_id": change["knowledge_point_id"],
        "item_id": item_ids[0],
        "item_ids": item_ids,
        "reason": reason,
        "item_types": [spec[0] for spec in item_specs],
    }


def submit_learning_session(
    user_id: int,
    session_id: int,
    answers: list[dict],
    actual_minutes: int | None = None,
    evaluator: Callable = evaluate_quiz_answers,
) -> dict:
    with get_cursor() as cursor:
        session = repository.get_session(cursor, session_id, user_id)
        if session is None:
            raise AppError("学习单元不存在或无访问权限", 404, "SESSION_NOT_FOUND")
        if session["status"] in {"completed", "evaluated"}:
            raise AppError("学习单元已经提交，请勿重复提交", 409, "SESSION_ALREADY_SUBMITTED")
        question_ids = [
            item["content_ref"].get("question_id")
            for item in session["items"]
            if item["content_ref"].get("question_id")
        ]
        questions = repository.get_questions_by_ids(cursor, question_ids, user_id)
        if not questions:
            raise AppError("当前学习单元没有可提交的练习", 409, "SESSION_HAS_NO_PRACTICE")
        allowed_ids = {question["id"] for question in questions}
        answers = [item for item in answers if item["question_id"] in allowed_ids]
        if not answers:
            raise AppError("至少填写一道当前学习单元的答案", 400, "ANSWERS_REQUIRED")
        quiz = {
            "id": questions[0]["quiz_set_id"],
            "title": questions[0]["quiz_title"],
            "questions": questions,
        }

    attempt, cached = _claim_evaluation(
        user_id,
        session["course_id"],
        quiz["id"],
        answers,
        study_session_id=session_id,
    )
    if cached is not None:
        return cached
    evaluation = _run_evaluator(attempt, quiz, answers, evaluator)

    with get_cursor() as cursor:
        current_session = repository.get_session(cursor, session_id, user_id)
        if current_session is None:
            raise AppError("学习单元不存在或无访问权限", 404, "SESSION_NOT_FOUND")
        if current_session["status"] in {"completed", "evaluated"}:
            raise AppError("学习单元已经提交，请勿重复提交", 409, "SESSION_ALREADY_SUBMITTED")
        evaluation, changes = _persist_evaluation_and_update_mastery(
            cursor,
            user_id,
            session["course_id"],
            quiz,
            evaluation,
            initial=False,
        )
        repository.update_session_status(
            cursor,
            session_id,
            user_id,
            "evaluated",
            actual_minutes,
        )
        course = course_repository.get_course(cursor, session["course_id"], user_id)
        if course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        points = repository.list_points_with_mastery(cursor, user_id, session["course_id"])
        point_names = {point["id"]: point["name"] for point in points}
        adaptations = [
            _adapt_next_session(
                cursor,
                user_id,
                course,
                change,
                point_names.get(change["knowledge_point_id"], "知识点"),
            )
            for change in changes
        ]
        record_audit(
            user_id,
            "COURSE_SESSION_SUBMITTED",
            "study_session",
            session_id,
            {
                "course_id": session["course_id"],
                "score": evaluation["score"],
                "mastery_change_count": len(changes),
                "adaptation_count": len(adaptations),
            },
            cursor=cursor,
        )
        result = {
            "evaluation": evaluation,
            "mastery_changes": changes,
            "adaptations": adaptations,
        }
        repository.finish_evaluation_attempt(
            cursor,
            attempt["id"],
            evaluation["id"],
            result,
            _utc_now(),
        )
    return result


def get_course_progress(user_id: int, course_id: int) -> dict:
    course = get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        progress = repository.progress_summary(cursor, user_id, course_id)
        record_audit(user_id, "COURSE_PROGRESS_VIEWED", "course", course_id, cursor=cursor)
    progress["course"] = course
    total = progress["session_total"]
    progress["completion_rate"] = (
        round(progress["session_completed"] / total * 100, 2) if total else 0
    )
    return progress


def get_practice(user_id: int, quiz_set_id: int) -> dict:
    with get_cursor() as cursor:
        quiz = repository.get_quiz_set(cursor, quiz_set_id, user_id)
        if quiz is None or quiz.get("purpose") != "practice":
            raise AppError("练习不存在或无访问权限", 404, "PRACTICE_NOT_FOUND")
        record_audit(
            user_id,
            "COURSE_PRACTICE_VIEWED",
            "quiz_set",
            quiz_set_id,
            {"course_id": quiz["course_id"]},
            cursor=cursor,
        )
    return _public_quiz(quiz)


def generate_practice(
    user_id: int,
    course_id: int,
    question_count: int = 3,
    knowledge_point_id: int | None = None,
    difficulty: str = "medium",
    question_provider: Callable = generate_practice_questions,
) -> dict:
    course = get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        points = repository.list_points_with_mastery(cursor, user_id, course_id)
    if not points:
        raise AppError("课程尚未建立知识点", 409, "KNOWLEDGE_POINTS_NOT_READY")
    if knowledge_point_id is not None:
        points = [point for point in points if point["id"] == knowledge_point_id]
        if not points:
            raise AppError("知识点不存在或无访问权限", 404, "KNOWLEDGE_POINT_NOT_FOUND")
    questions = question_provider(course, points, question_count, difficulty)
    if len(questions) != question_count:
        raise AppError("练习题生成结果无效", 502, "PRACTICE_GENERATION_INVALID")
    point_names = ", ".join(point["name"] for point in points[:2])
    with get_cursor() as cursor:
        quiz = repository.create_quiz_set(
            cursor,
            user_id,
            course,
            f"{point_names or course['name']}针对性练习",
            "practice",
            questions,
        )
        record_audit(
            user_id,
            "COURSE_PRACTICE_GENERATED",
            "quiz_set",
            quiz["id"],
            {
                "course_id": course_id,
                "knowledge_point_id": knowledge_point_id,
                "question_count": question_count,
                "difficulty": difficulty,
            },
            cursor=cursor,
        )
    return _public_quiz(quiz)


def submit_practice(
    user_id: int,
    quiz_set_id: int,
    answers: list[dict],
    evaluator: Callable = evaluate_quiz_answers,
) -> dict:
    with get_cursor() as cursor:
        preview = repository.get_quiz_set(cursor, quiz_set_id, user_id)
        if preview is None or preview.get("purpose") != "practice":
            raise AppError("练习不存在或无访问权限", 404, "PRACTICE_NOT_FOUND")
        if preview.get("submitted"):
            attempt = repository.get_evaluation_attempt(
                cursor, user_id, _evaluation_attempt_key(quiz_set_id)
            )
            if attempt and attempt["status"] == "completed" and attempt.get("result"):
                return attempt["result"]
            raise AppError("练习已经提交，请重新生成一组题目", 409, "PRACTICE_ALREADY_SUBMITTED")
        active_plan = repository.get_course_plan(cursor, user_id, preview["course_id"])
        allowed_ids = {question["id"] for question in preview["questions"]}
        submitted = [item for item in answers if item["question_id"] in allowed_ids]
        if not submitted:
            raise AppError("至少填写一道当前练习的答案", 400, "ANSWERS_REQUIRED")

    attempt, cached = _claim_evaluation(
        user_id,
        preview["course_id"],
        quiz_set_id,
        submitted,
    )
    if cached is not None:
        return cached
    if active_plan is None:
        try:
            generate_study_plan(user_id, preview["course_id"])
        except Exception as exc:
            with get_cursor() as cursor:
                repository.fail_evaluation_attempt(cursor, attempt["id"], str(exc), _utc_now())
            raise
    evaluation = _run_evaluator(attempt, preview, submitted, evaluator)

    with get_cursor() as cursor:
        quiz = repository.get_quiz_set(cursor, quiz_set_id, user_id)
        if quiz is None or quiz.get("purpose") != "practice":
            raise AppError("练习不存在或无访问权限", 404, "PRACTICE_NOT_FOUND")
        if quiz.get("submitted"):
            raise AppError("练习已经提交，请重新生成一组题目", 409, "PRACTICE_ALREADY_SUBMITTED")
        evaluation, changes = _persist_evaluation_and_update_mastery(
            cursor,
            user_id,
            quiz["course_id"],
            quiz,
            evaluation,
            initial=False,
        )
        course = course_repository.get_course(cursor, quiz["course_id"], user_id)
        if course is None:
            raise AppError("Course no longer exists", 404, "COURSE_NOT_FOUND")
        points = repository.list_points_with_mastery(cursor, user_id, quiz["course_id"])
        point_names = {point["id"]: point["name"] for point in points}
        adaptations = [
            _adapt_next_session(
                cursor,
                user_id,
                course,
                change,
                point_names.get(change["knowledge_point_id"], "知识点"),
            )
            for change in changes
        ]
        result = {
            "evaluation": evaluation,
            "mastery_changes": changes,
            "adaptations": adaptations,
        }
        repository.persist_practice_result_in_agent_message(
            cursor,
            user_id,
            quiz["course_id"],
            quiz_set_id,
            {
                "evaluation": {
                    "id": evaluation["id"],
                    "score": evaluation["score"],
                    "summary": evaluation.get("summary"),
                },
                "mastery_changes": changes,
                "adaptations": adaptations,
            },
        )
        record_audit(
            user_id,
            "COURSE_PRACTICE_SUBMITTED",
            "quiz_set",
            quiz_set_id,
            {
                "course_id": quiz["course_id"],
                "score": evaluation["score"],
                "mastery_change_count": len(changes),
                "adaptation_count": len(adaptations),
            },
            cursor=cursor,
        )
        repository.finish_evaluation_attempt(
            cursor,
            attempt["id"],
            evaluation["id"],
            result,
            _utc_now(),
        )
    return result


def get_practice_statistics(user_id: int, course_id: int) -> dict:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        data = repository.practice_statistics(cursor, user_id, course_id)
        record_audit(user_id, "COURSE_PRACTICE_STATS_VIEWED", "course", course_id, cursor=cursor)
    return data


def get_wrong_answers(user_id: int, course_id: int) -> dict:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        items = repository.list_wrong_answers(cursor, user_id, course_id)
        record_audit(
            user_id,
            "COURSE_WRONG_ANSWERS_VIEWED",
            "course",
            course_id,
            {"count": len(items)},
            cursor=cursor,
        )
    return {"items": items, "total": len(items)}


def get_study_plan(user_id: int, course_id: int) -> dict | None:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        plan = repository.get_course_plan(cursor, user_id, course_id)
        record_audit(
            user_id,
            "COURSE_PLAN_VIEWED",
            "course",
            course_id,
            {"plan_id": plan["id"] if plan else None},
            cursor=cursor,
        )
    return plan


def reschedule_learning_session(
    user_id: int,
    session_id: int,
    scheduled_date: date,
    estimated_minutes: int | None = None,
) -> dict:
    with get_cursor() as cursor:
        current = repository.get_session(cursor, session_id, user_id)
        if current is None:
            raise AppError("学习单元不存在或无访问权限", 404, "SESSION_NOT_FOUND")
        session = repository.reschedule_session(
            cursor,
            session_id,
            user_id,
            scheduled_date,
            estimated_minutes,
        )
        if session is None:
            raise AppError("已完成的学习单元不能调整", 409, "SESSION_NOT_RESCHEDULABLE")
        record_audit(
            user_id,
            "COURSE_SESSION_RESCHEDULED",
            "study_session",
            session_id,
            {
                "course_id": session["course_id"],
                "scheduled_date": scheduled_date,
                "estimated_minutes": estimated_minutes,
            },
            cursor=cursor,
        )
    return session
