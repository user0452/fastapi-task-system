import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.time_utils import local_date, utc_naive_to_local
from app.integrations.llm.diagnostic_generator import generate_diagnostic_questions
from app.integrations.llm.evaluation import evaluate_quiz_answers
from app.integrations.llm.practice_generator import generate_practice_questions
from app.modules.account.service import get_user_local_date, get_user_timezone
from app.modules.audit.service import record_audit
from app.modules.courses import repository as course_repository
from app.modules.courses.service import get_user_course
from app.modules.learning import repository
from app.modules.learning.today_planner import (
    DEFAULT_AVAILABLE_MINUTES,
    plan_today_rows,
)
from app.modules.roadmaps import service as roadmap_service


def _public_quiz(quiz: dict) -> dict:
    return {
        key: quiz[key]
        for key in ("id", "course_id", "title", "course_name", "purpose", "submitted")
        if key in quiz
    } | {
        "questions": [
            {
                key: question[key]
                for key in (
                    "id",
                    "quiz_set_id",
                    "knowledge_point_id",
                    "question_type",
                    "question",
                    "difficulty",
                )
                if key in question
            }
            for question in quiz.get("questions", [])
        ]
    }


def _public_evaluation(evaluation: dict | None) -> dict | None:
    if evaluation is None:
        return None
    return {
        key: evaluation[key]
        for key in (
            "id",
            "quiz_set_id",
            "score",
            "level",
            "summary",
            "weak_points",
            "suggestions",
        )
        if key in evaluation
    } | {
        "question_reviews": [
            {
                key: review[key]
                for key in ("question_id", "score", "feedback", "weak_point")
                if key in review
            }
            for review in evaluation.get("question_reviews", [])
        ]
    }


def _public_submission_result(result: dict) -> dict:
    public = dict(result)
    if "evaluation" in public:
        public["evaluation"] = _public_evaluation(public["evaluation"])
    return json.loads(json.dumps(public, ensure_ascii=False, default=str))


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
    if question_provider is generate_diagnostic_questions:
        questions = question_provider(course, points, question_count, user_id=user_id)
    else:
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


def _validate_complete_answers(
    questions: list[dict],
    answers: list[dict],
    *,
    subject: str,
) -> list[dict]:
    expected_ids = [int(question["id"]) for question in questions]
    if not expected_ids:
        raise AppError(f"{subject}没有可提交的题目", 409, "QUIZ_HAS_NO_QUESTIONS")
    if not answers:
        raise AppError(f"请填写全部{subject}答案", 400, "ANSWERS_REQUIRED")

    submitted_ids = [int(item["question_id"]) for item in answers]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise AppError(f"{subject}答案包含重复题号", 400, "DUPLICATE_QUESTION_IDS")

    expected_set = set(expected_ids)
    submitted_set = set(submitted_ids)
    invalid_ids = sorted(submitted_set - expected_set)
    if invalid_ids:
        raise AppError(
            f"{subject}答案包含不属于当前题集的题号",
            400,
            "INVALID_QUESTION_IDS",
            {"question_ids": invalid_ids},
        )

    missing_ids = [question_id for question_id in expected_ids if question_id not in submitted_set]
    if missing_ids:
        raise AppError(
            f"请完成全部{subject}题目后再提交",
            400,
            "INCOMPLETE_ANSWERS",
            {"question_ids": missing_ids},
        )

    answer_map: dict[int, str] = {}
    for item in answers:
        question_id = int(item["question_id"])
        user_answer = str(item.get("user_answer") or "").strip()
        if not user_answer:
            raise AppError(
                f"{subject}答案不能为空",
                400,
                "BLANK_ANSWER",
                {"question_id": question_id},
            )
        answer_map[question_id] = user_answer
    return [
        {"question_id": question_id, "user_answer": answer_map[question_id]}
        for question_id in expected_ids
    ]


def _normalize_evaluation(quiz: dict, answers: list[dict], raw_evaluation: Any) -> dict:
    if hasattr(raw_evaluation, "model_dump"):
        raw_evaluation = raw_evaluation.model_dump()
    if not isinstance(raw_evaluation, dict):
        raise AppError("评估结果格式无效", 502, "EVALUATION_RESULT_INVALID")

    reviews = raw_evaluation.get("question_reviews")
    if not isinstance(reviews, list):
        raise AppError("评估结果缺少逐题明细", 502, "EVALUATION_RESULT_INVALID")

    review_ids: list[int] = []
    review_map: dict[int, dict] = {}
    try:
        for review in reviews:
            if not isinstance(review, dict):
                raise TypeError
            question_id = int(review["question_id"])
            review_ids.append(question_id)
            review_map[question_id] = review
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("评估明细题号无效", 502, "EVALUATION_RESULT_INVALID") from exc

    if len(review_ids) != len(set(review_ids)):
        raise AppError("评估明细包含重复题号", 502, "EVALUATION_RESULT_INVALID")

    expected_ids = [int(question["id"]) for question in quiz["questions"]]
    if set(review_ids) != set(expected_ids) or len(review_ids) != len(expected_ids):
        raise AppError(
            "评估明细与当前题集不一致",
            502,
            "EVALUATION_RESULT_INVALID",
        )

    question_map = {int(question["id"]): question for question in quiz["questions"]}
    answer_map = {int(item["question_id"]): item["user_answer"] for item in answers}
    normalized_reviews: list[dict] = []
    weak_points: list[str] = []
    for question_id in expected_ids:
        raw_review = review_map[question_id]
        try:
            score = int(raw_review["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError("评估分数无效", 502, "EVALUATION_RESULT_INVALID") from exc
        if not 0 <= score <= 100:
            raise AppError("评估分数超出范围", 502, "EVALUATION_RESULT_INVALID")
        feedback = str(raw_review.get("feedback") or "").strip()
        if not feedback:
            raise AppError("评估反馈不能为空", 502, "EVALUATION_RESULT_INVALID")
        weak_point = str(raw_review.get("weak_point") or "").strip() or None
        if weak_point and weak_point not in weak_points:
            weak_points.append(weak_point)
        question = question_map[question_id]
        normalized_reviews.append(
            {
                "question_id": question_id,
                "question": question["question"],
                "reference_answer": question["answer"],
                "user_answer": answer_map[question_id],
                "score": score,
                "feedback": feedback,
                "weak_point": weak_point,
            }
        )

    score = round(sum(item["score"] for item in normalized_reviews) / len(normalized_reviews))
    if score < 60:
        level = "需要复习"
        suggestions = ["优先复习低分知识点后再进行针对性练习"]
    elif score < 80:
        level = "基本掌握"
        suggestions = ["根据逐题反馈补齐薄弱环节并继续练习"]
    else:
        level = "掌握良好"
        suggestions = ["继续完成进阶练习并定期复习"]
    return {
        "quiz_set_id": quiz["id"],
        "score": score,
        "level": level,
        "summary": f"共评估 {len(normalized_reviews)} 道题，平均得分 {score} 分。",
        "weak_points": weak_points,
        "suggestions": suggestions,
        "question_reviews": normalized_reviews,
    }


def _claim_evaluation(
    user_id: int,
    course_id: int,
    quiz_set_id: int,
    answers: list[dict],
    study_session_id: int | None = None,
) -> tuple[dict, str]:
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
    if attempt["request_hash"] != request_hash:
        raise AppError("该题集已经使用另一份答案提交", 409, "EVALUATION_ALREADY_SUBMITTED")
    if claimed:
        return attempt, "evaluate"
    if attempt["status"] == "completed":
        if attempt.get("result") is None:
            raise AppError("评估结果状态异常", 500, "EVALUATION_STATE_INVALID")
        return attempt, "completed"
    if attempt["status"] in {"evaluated", "planning_failed"}:
        return attempt, "planning"
    if attempt["status"] == "planning":
        raise AppError("学习计划正在生成，请稍后重试", 409, "PLANNING_IN_PROGRESS")
    raise AppError("答案正在评分，请勿重复提交", 409, "EVALUATION_IN_PROGRESS")


def _assert_evaluation_claim_current(cursor, attempt: dict) -> None:
    current = repository.get_evaluation_attempt(
        cursor,
        attempt["user_id"],
        attempt["attempt_key"],
        for_update=True,
    )
    if (
        current is None
        or current["id"] != attempt["id"]
        or current["status"] != "evaluating"
        or current["started_at"] != attempt["started_at"]
    ):
        raise AppError("评估任务已由其他请求接管", 409, "EVALUATION_CLAIM_LOST")


def _claim_planning(attempt: dict) -> tuple[dict, str]:
    now = _utc_now()
    with get_cursor() as cursor:
        claimed_attempt, claimed = repository.claim_evaluation_planning(
            cursor,
            user_id=attempt["user_id"],
            attempt_key=attempt["attempt_key"],
            request_hash=attempt["request_hash"],
            started_at=now,
            stale_before=now - timedelta(minutes=3),
        )
    if claimed_attempt["request_hash"] != attempt["request_hash"]:
        raise AppError("该题集已经使用另一份答案提交", 409, "EVALUATION_ALREADY_SUBMITTED")
    if claimed:
        return claimed_attempt, "planning"
    if claimed_attempt["status"] == "completed" and claimed_attempt.get("result") is not None:
        return claimed_attempt, "completed"
    raise AppError("学习计划正在生成，请稍后重试", 409, "PLANNING_IN_PROGRESS")


def _run_evaluator(
    user_id: int,
    attempt: dict,
    quiz: dict,
    answers: list[dict],
    evaluator: Callable,
) -> dict:
    try:
        evaluator_kwargs = {
            "quiz_set_id": quiz["id"],
            "quiz_title": quiz["title"],
            "questions": quiz["questions"],
            "user_answers": answers,
            "profile": None,
        }
        if evaluator is evaluate_quiz_answers:
            evaluator_kwargs["user_id"] = user_id
        raw_evaluation = evaluator(
            **evaluator_kwargs,
        )
        return _normalize_evaluation(quiz, answers, raw_evaluation)
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
    expected_ids = [int(question["id"]) for question in quiz["questions"]]
    review_ids = [
        int(review["question_id"])
        for review in evaluation.get("question_reviews", [])
    ]
    if len(review_ids) != len(set(review_ids)) or set(review_ids) != set(expected_ids):
        raise AppError(
            "评估明细与当前题集不一致，未更新掌握度",
            502,
            "EVALUATION_RESULT_INVALID",
        )

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
        # Short-interval repeats contribute less so a single weak point can't be
        # farmed for mastery. Initial/diagnostic still takes the raw score.
        weight = 0.3
        if not initial and existing is not None:
            # recent_count includes prior updates (e.g. diagnostic). Attenuate only
            # when the same point is scored repeatedly within the window.
            recent_count = repository.count_recent_mastery_changes(
                cursor,
                user_id,
                course_id,
                point_id,
                hours=6,
            )
            if recent_count >= 3:
                weight = 0.15
            elif recent_count >= 2:
                weight = 0.22
        if initial or existing is None:
            after = assessment_score
            formula = "initial"
            reason = f"诊断得分 {assessment_score:.1f}，建立初始掌握度"
        else:
            after = before * (1.0 - weight) + assessment_score * weight
            formula = f"before×{1.0 - weight:.2f}+score×{weight:.2f}"
            reason = (
                f"原掌握度 {before:.1f} × {1.0 - weight:.2f} + "
                f"本次得分 {assessment_score:.1f} × {weight:.2f}"
            )
            if weight < 0.3:
                reason += "（短时间内重复练习，更新权重已衰减）"
        after = round(max(0.0, min(100.0, after)), 2)
        old_streak = int(existing["low_score_streak"]) if existing else 0
        low_score_streak = old_streak + 1 if assessment_score < 60 else 0
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
                "formula": formula,
                "weight": weight,
                "evaluation_id": evaluation_id,
                "low_score_streak": low_score_streak,
            }
        )
    return evaluation, changes


def _plan_length(course: dict, today: date, timezone_name: str) -> int:
    exam_at = course.get("exam_at")
    if not exam_at:
        return 7
    exam_date = utc_naive_to_local(exam_at, timezone_name).date()
    remaining = (exam_date - today).days + 1
    return max(3, min(14, remaining)) if remaining > 0 else 3


def generate_study_plan(user_id: int, course_id: int, diagnostic_quiz: dict | None = None) -> dict:
    course = get_user_course(user_id, course_id)
    diagnostic_quiz_id = diagnostic_quiz.get("id") if diagnostic_quiz else None
    if diagnostic_quiz_id is not None:
        with get_cursor() as cursor:
            existing_plan = repository.get_plan_for_diagnostic(
                cursor,
                user_id,
                course_id,
                diagnostic_quiz_id,
            )
        if existing_plan is not None:
            existing_plan["days"] = (
                existing_plan["end_date"] - existing_plan["start_date"]
            ).days + 1
            return existing_plan

    with get_cursor() as cursor:
        points = repository.list_points_with_mastery(cursor, user_id, course_id)
    if not points:
        raise AppError("课程尚未建立知识点", 409, "KNOWLEDGE_POINTS_NOT_READY")

    question_by_point: dict[int, dict] = {}
    if diagnostic_quiz:
        for question in diagnostic_quiz.get("questions", []):
            question_by_point.setdefault(question.get("knowledge_point_id"), question)
        covered_points = [point for point in points if point["id"] in question_by_point]
        if covered_points:
            points = covered_points

    timezone_name = get_user_timezone(user_id)
    start = get_user_local_date(user_id)
    days = _plan_length(course, start, timezone_name)
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
    plan_provider: Callable = generate_study_plan,
) -> dict:
    with get_cursor() as cursor:
        quiz = repository.get_quiz_set(cursor, quiz_set_id, user_id)
        if quiz is None or quiz.get("purpose") != "diagnostic":
            raise AppError("诊断题不存在或无访问权限", 404, "DIAGNOSTIC_NOT_FOUND")
        if quiz.get("submitted"):
            attempt = repository.get_evaluation_attempt(
                cursor, user_id, _evaluation_attempt_key(quiz_set_id)
            )
            if attempt is None:
                raise AppError("诊断已经提交，请直接进入今日学习", 409, "DIAGNOSTIC_ALREADY_SUBMITTED")
        submitted = _validate_complete_answers(
            quiz["questions"],
            answers,
            subject="诊断",
        )

    attempt, action = _claim_evaluation(
        user_id,
        quiz["course_id"],
        quiz_set_id,
        submitted,
    )
    if action == "completed":
        return attempt["result"]

    if action == "evaluate":
        evaluation = _run_evaluator(user_id, attempt, quiz, submitted, evaluator)
        with get_cursor() as cursor:
            _assert_evaluation_claim_current(cursor, attempt)
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
            roadmap_adjusted = roadmap_service.adjust_roadmap_for_evaluation(
                cursor,
                user_id=user_id,
                course_id=quiz["course_id"],
                trigger_type="diagnostic",
                trigger_id=evaluation["id"],
                evaluation=evaluation,
                mastery_changes=changes,
            )
            result = {
                "evaluation": evaluation,
                "mastery_changes": changes,
                "roadmap_adjusted": roadmap_adjusted,
            }
            public_result = _public_submission_result(result)
            repository.mark_evaluation_attempt_evaluated(
                cursor,
                attempt["id"],
                evaluation["id"],
                public_result,
            )
            record_audit(
                user_id,
                "COURSE_DIAGNOSTIC_SUBMITTED",
                "quiz_set",
                quiz_set_id,
                {"course_id": quiz["course_id"], "score": evaluation["score"]},
                cursor=cursor,
            )
        attempt = {
            **attempt,
            "status": "evaluated",
            "evaluation_id": evaluation["id"],
            "result": public_result,
        }
    else:
        resumed_result = attempt.get("result")
        if attempt.get("evaluation_id") is None or not isinstance(resumed_result, dict):
            raise AppError("诊断恢复状态不完整", 500, "EVALUATION_STATE_INVALID")
        public_result = resumed_result

    planning_attempt, planning_action = _claim_planning(attempt)
    if planning_action == "completed":
        return planning_attempt["result"]
    try:
        plan = plan_provider(user_id, quiz["course_id"], quiz)
        roadmap_service.sync_course_links(user_id, quiz["course_id"])
    except Exception as exc:
        with get_cursor() as cursor:
            repository.fail_evaluation_attempt(
                cursor,
                planning_attempt["id"],
                str(exc),
                _utc_now(),
                phase="planning",
            )
        raise

    public_result = _public_submission_result({**public_result, "plan": plan})
    with get_cursor() as cursor:
        repository.finish_evaluation_attempt(
            cursor,
            planning_attempt["id"],
            planning_attempt["evaluation_id"],
            public_result,
            _utc_now(),
            expected_status="planning",
        )
    return public_result


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
    today = get_user_local_date(user_id)
    with get_cursor() as cursor:
        session = repository.get_today_session(cursor, user_id, course_id, today)
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


def get_today_overview(
    user_id: int,
    available_minutes: int = DEFAULT_AVAILABLE_MINUTES,
) -> dict:
    """Aggregate and prioritise today's sessions for all active courses."""
    timezone_name = get_user_timezone(user_id)
    today = local_date(timezone_name)
    with get_cursor() as cursor:
        courses = course_repository.list_courses(cursor, user_id, include_archived=False)
        roadmap_service.attach_summaries(cursor, user_id, courses)
        mastery_by_course = repository.mastery_summaries_for_courses(
            cursor,
            user_id,
            [int(course["id"]) for course in courses],
        )
        for course in courses:
            course["learning_priority"] = mastery_by_course.get(
                int(course["id"]),
                {"total_points": 0, "weak_points": 0, "average_mastery": 0.0},
            )
        sessions_by_course = repository.list_today_sessions_for_user(cursor, user_id, today)
        # Batch-load question payloads for every today session item.
        question_ids: list[int] = []
        for loaded_session in sessions_by_course.values():
            for item in loaded_session.get("items", []):
                question_id = item.get("content_ref", {}).get("question_id")
                if question_id:
                    question_ids.append(int(question_id))
        questions = repository.get_questions_by_ids(cursor, question_ids, user_id)
        question_map = {item["id"]: item for item in questions}
        rows: list[dict] = []
        total_minutes = 0
        total_items = 0
        completed = 0
        for course in courses:
            course_session = sessions_by_course.get(int(course["id"]))
            if course_session is not None:
                for item in course_session.get("items", []):
                    question_id = item.get("content_ref", {}).get("question_id")
                    if question_id in question_map:
                        question = question_map[question_id]
                        item["question"] = {
                            key: question[key]
                            for key in [
                                "id",
                                "knowledge_point_id",
                                "question_type",
                                "question",
                                "difficulty",
                            ]
                        }
                total_minutes += int(course_session.get("estimated_minutes") or 0)
                total_items += len(course_session.get("items") or [])
                if course_session.get("status") in {"completed", "evaluated"}:
                    completed += 1
            rows.append({"course": course, "session": course_session})
        planned = plan_today_rows(
            rows,
            today=today,
            available_minutes=available_minutes,
            timezone_name=timezone_name,
        )
        record_audit(
            user_id,
            "COURSE_TODAY_OVERVIEW_VIEWED",
            "course",
            detail={
                "count": len(rows),
                "completed": completed,
                "available_minutes": planned["budget"]["available_minutes"],
                "recommended_minutes": planned["budget"]["recommended_minutes"],
            },
            cursor=cursor,
        )
    return {
        "date": today.isoformat(),
        "items": planned["items"],
        "budget": planned["budget"],
        "summary": {
            "course_count": len(rows),
            "total_minutes": total_minutes,
            "recommended_minutes": planned["budget"]["recommended_minutes"],
            "total_items": total_items,
            "completed": completed,
            "with_session": sum(1 for row in rows if row["session"]),
        },
    }


def get_course_workspace_overview(user_id: int, course_id: int) -> dict:
    """Single payload for the course inspector overview panel."""
    course = get_user_course(user_id, course_id)
    today = get_user_local_date(user_id)
    with get_cursor() as cursor:
        progress = repository.progress_summary(cursor, user_id, course_id)
        practice = repository.practice_statistics(cursor, user_id, course_id)
        plan = repository.get_course_plan(cursor, user_id, course_id)
        session = repository.get_today_session(cursor, user_id, course_id, today)
        today_data = _hydrate_session_questions(cursor, session, user_id) if session else None
        record_audit(
            user_id,
            "COURSE_WORKSPACE_OVERVIEW_VIEWED",
            "course",
            course_id,
            {
                "has_plan": plan is not None,
                "has_today": today_data is not None,
            },
            cursor=cursor,
        )
    progress["course"] = course
    total = progress["session_total"]
    progress["completion_rate"] = (
        round(progress["session_completed"] / total * 100, 2) if total else 0
    )
    roadmap = roadmap_service.get_learning_roadmap(user_id, course_id)
    return {
        "course": course,
        "progress": progress,
        "practice": practice,
        "plan": plan,
        "roadmap": roadmap,
        "today": today_data,
    }


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


def _adapt_next_session(
    cursor,
    user_id: int,
    course: dict,
    change: dict,
    point_name: str,
    tomorrow: date,
) -> dict:
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
    item_specs: list[tuple[str, str, dict[str, object], int]]
    if after < 60:
        reason = f"{point_name}掌握度为 {after:.1f}，次日增加复习、基础讲解和基础题"
        item_specs = [
            ("review", f"重点复习：{point_name}", {"mode": "review", "spaced_review": True}, -40),
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
            repository.update_session_status(
                cursor,
                session_id,
                user_id,
                "completed",
                actual_minutes,
            )
            record_audit(
                user_id,
                "COURSE_SESSION_SUBMITTED",
                "study_session",
                session_id,
                {
                    "course_id": session["course_id"],
                    "score": None,
                    "mastery_change_count": 0,
                    "adaptation_count": 0,
                    "completion_only": True,
                },
                cursor=cursor,
            )
            return {"evaluation": None, "mastery_changes": [], "adaptations": []}
        answers = _validate_complete_answers(
            questions,
            answers,
            subject="当前学习单元",
        )
        quiz = {
            "id": questions[0]["quiz_set_id"],
            "title": questions[0]["quiz_title"],
            "questions": questions,
        }

    attempt, action = _claim_evaluation(
        user_id,
        session["course_id"],
        quiz["id"],
        answers,
        study_session_id=session_id,
    )
    if action == "completed":
        return attempt["result"]
    if action != "evaluate":
        raise AppError("当前学习单元评估状态异常", 409, "EVALUATION_IN_PROGRESS")
    evaluation = _run_evaluator(user_id, attempt, quiz, answers, evaluator)
    tomorrow = get_user_local_date(user_id) + timedelta(days=1)

    with get_cursor() as cursor:
        _assert_evaluation_claim_current(cursor, attempt)
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
                tomorrow,
            )
            for change in changes
        ]
        roadmap_adjusted = roadmap_service.adjust_roadmap_for_evaluation(
            cursor,
            user_id=user_id,
            course_id=session["course_id"],
            trigger_type="study_session",
            trigger_id=evaluation["id"],
            evaluation=evaluation,
            mastery_changes=changes,
        )
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
            "roadmap_adjusted": roadmap_adjusted,
        }
        public_result = _public_submission_result(result)
        repository.finish_evaluation_attempt(
            cursor,
            attempt["id"],
            evaluation["id"],
            public_result,
            _utc_now(),
        )
    return public_result


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
    if question_provider is generate_practice_questions:
        questions = question_provider(
            course,
            points,
            question_count,
            difficulty,
            user_id=user_id,
        )
    else:
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
        submitted = _validate_complete_answers(
            preview["questions"],
            answers,
            subject="练习",
        )

    attempt, action = _claim_evaluation(
        user_id,
        preview["course_id"],
        quiz_set_id,
        submitted,
    )
    if action == "completed":
        return attempt["result"]
    if action != "evaluate":
        raise AppError("练习评估状态异常", 409, "EVALUATION_IN_PROGRESS")
    if active_plan is None:
        try:
            generate_study_plan(user_id, preview["course_id"])
        except Exception as exc:
            with get_cursor() as cursor:
                repository.fail_evaluation_attempt(cursor, attempt["id"], str(exc), _utc_now())
            raise
    evaluation = _run_evaluator(user_id, attempt, preview, submitted, evaluator)
    tomorrow = get_user_local_date(user_id) + timedelta(days=1)

    with get_cursor() as cursor:
        _assert_evaluation_claim_current(cursor, attempt)
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
                tomorrow,
            )
            for change in changes
        ]
        roadmap_adjusted = roadmap_service.adjust_roadmap_for_evaluation(
            cursor,
            user_id=user_id,
            course_id=quiz["course_id"],
            trigger_type="practice",
            trigger_id=evaluation["id"],
            evaluation=evaluation,
            mastery_changes=changes,
        )
        result = {
            "evaluation": evaluation,
            "mastery_changes": changes,
            "adaptations": adaptations,
            "roadmap_adjusted": roadmap_adjusted,
        }
        public_result = _public_submission_result(result)
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
            public_result,
            _utc_now(),
        )
    return public_result


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
