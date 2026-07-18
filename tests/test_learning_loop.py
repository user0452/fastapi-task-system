import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Event

import pytest

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.llm import diagnostic_generator
from app.modules.account import service as account_service
from app.modules.account.service import update_user_timezone
from app.modules.courses.schemas import CourseCreate, CourseUpdate
from app.modules.courses.service import create_user_course, update_user_course
from app.modules.learning import repository
from app.modules.learning.service import (
    generate_diagnostic,
    generate_practice,
    generate_study_plan,
    get_course_progress,
    get_course_workspace_overview,
    get_diagnostic,
    get_today_learning,
    get_today_overview,
    start_learning_session,
    submit_diagnostic,
    submit_learning_session,
)
from app.modules.resources.service import _resolve_knowledge_point


def _insert_points(user_id: int, course_id: int) -> list[dict]:
    points = []
    with get_cursor() as cursor:
        for index, name in enumerate(["边界值分析", "等价类划分", "判定表测试"]):
            cursor.execute(
                """
                INSERT INTO knowledge_points
                    (user_id, course_id, name, description, source_chunk_ids, sort_order)
                VALUES (%s, %s, %s, %s, JSON_ARRAY(), %s)
                """,
                (user_id, course_id, name, f"{name}的核心方法与适用场景", index),
            )
            points.append(
                {
                    "id": cursor.lastrowid,
                    "name": name,
                    "description": f"{name}的核心方法与适用场景",
                }
            )
    return points


def _question_provider(_course: dict, points: list[dict], count: int) -> list[dict]:
    return [
        {
            "knowledge_point_id": points[index % 3]["id"],
            "question": f"请说明{points[index % 3]['name']}的要点（{index + 1}）。",
            "answer": points[index % 3]["description"],
            "question_type": "short_answer",
            "difficulty": "medium",
        }
        for index in range(count)
    ]


def _evaluator(point_scores: dict[int, float]):
    def evaluate(
        quiz_set_id: int,
        quiz_title: str,
        questions: list[dict],
        user_answers: list[dict],
        profile: dict | None = None,
    ) -> dict:
        del quiz_title, profile
        answer_map = {item["question_id"]: item["user_answer"] for item in user_answers}
        reviews = []
        for question in questions:
            if question["id"] not in answer_map:
                continue
            score = point_scores[question["knowledge_point_id"]]
            reviews.append(
                {
                    "question_id": question["id"],
                    "question": question["question"],
                    "reference_answer": question["answer"],
                    "user_answer": answer_map[question["id"]],
                    "score": score,
                    "feedback": f"本题得分 {score}",
                    "weak_point": None if score >= 60 else "核心概念不完整",
                }
            )
        total = sum(item["score"] for item in reviews) / len(reviews)
        return {
            "quiz_set_id": quiz_set_id,
            "score": round(total),
            "level": "测试评估",
            "summary": "确定性测试评估",
            "weak_points": [],
            "suggestions": [],
            "question_reviews": reviews,
        }

    return evaluate


@pytest.fixture
def learning_course(two_users):
    user, other_user = two_users
    course = create_user_course(
        user["id"],
        CourseCreate(name="软件测试冲刺", goal="七天完成核心方法复习", daily_minutes=25),
    )
    points = _insert_points(user["id"], course["id"])
    diagnostic = generate_diagnostic(
        user["id"],
        course["id"],
        question_count=6,
        question_provider=_question_provider,
    )
    return user, other_user, course, points, diagnostic


def _all_answers(quiz: dict) -> list[dict]:
    return [
        {"question_id": question["id"], "user_answer": "测试答案"}
        for question in quiz["questions"]
    ]


def _assert_no_answer_leak(value) -> None:
    if isinstance(value, dict):
        assert not ({"answer", "reference_answer", "quiz_json"} & set(value))
        for nested in value.values():
            _assert_no_answer_leak(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_answer_leak(nested)


def test_diagnostic_has_measurable_coverage_and_hides_answers(learning_course, api_client):
    user, _, _, _, diagnostic = learning_course

    assert len(diagnostic["questions"]) == 6
    assert len({item["knowledge_point_id"] for item in diagnostic["questions"]}) == 3
    _assert_no_answer_leak(diagnostic)

    restored = get_diagnostic(user["id"], diagnostic["id"])
    assert restored["id"] == diagnostic["id"]
    _assert_no_answer_leak(restored)

    response = api_client.get(f"/api/v1/diagnostics/{diagnostic['id']}")
    assert response.status_code == 200
    _assert_no_answer_leak(response.json())


def test_diagnostic_rejects_duplicate_invalid_and_partial_submissions(learning_course):
    user, _, _, _, diagnostic = learning_course
    complete = _all_answers(diagnostic)

    duplicate = complete + [dict(complete[0])]
    with pytest.raises(AppError) as duplicate_error:
        submit_diagnostic(user["id"], diagnostic["id"], duplicate)
    assert duplicate_error.value.error_code == "DUPLICATE_QUESTION_IDS"

    invalid = [dict(item) for item in complete]
    invalid[-1]["question_id"] = max(item["question_id"] for item in complete) + 1000
    with pytest.raises(AppError) as invalid_error:
        submit_diagnostic(user["id"], diagnostic["id"], invalid)
    assert invalid_error.value.error_code == "INVALID_QUESTION_IDS"

    with pytest.raises(AppError) as partial_error:
        submit_diagnostic(user["id"], diagnostic["id"], complete[:1])
    assert partial_error.value.error_code == "INCOMPLETE_ANSWERS"

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM learning_evaluations WHERE quiz_set_id = %s",
            (diagnostic["id"],),
        )
        assert cursor.fetchone()["total"] == 0


@pytest.mark.parametrize("invalid_case", ["missing", "duplicate", "illegal"])
def test_invalid_evaluation_details_do_not_update_mastery(learning_course, invalid_case):
    user, _, course, _, diagnostic = learning_course

    def invalid_evaluator(
        quiz_set_id: int,
        quiz_title: str,
        questions: list[dict],
        user_answers: list[dict],
        profile: dict | None = None,
    ) -> dict:
        del quiz_set_id, quiz_title, user_answers, profile
        reviews = [
            {
                "question_id": question["id"],
                "score": 70,
                "feedback": "测试反馈",
                "weak_point": None,
            }
            for question in questions
        ]
        if invalid_case == "missing":
            reviews.pop()
        elif invalid_case == "duplicate":
            reviews[-1] = dict(reviews[0])
        else:
            reviews[-1]["question_id"] = max(item["id"] for item in questions) + 1000
        return {"question_reviews": reviews}

    with pytest.raises(AppError) as error:
        submit_diagnostic(
            user["id"],
            diagnostic["id"],
            _all_answers(diagnostic),
            evaluator=invalid_evaluator,
        )
    assert error.value.error_code == "EVALUATION_RESULT_INVALID"

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM learning_evaluations WHERE quiz_set_id = %s",
            (diagnostic["id"],),
        )
        assert cursor.fetchone()["total"] == 0
        cursor.execute(
            "SELECT COUNT(*) AS total FROM mastery_records WHERE user_id = %s AND course_id = %s",
            (user["id"], course["id"]),
        )
        assert cursor.fetchone()["total"] == 0
        cursor.execute(
            """
            SELECT status FROM evaluation_attempts
            WHERE user_id = %s AND quiz_set_id = %s
            """,
            (user["id"], diagnostic["id"]),
        )
        assert cursor.fetchone()["status"] == "evaluation_failed"


def test_server_reassembles_evaluation_and_recomputes_total(learning_course):
    user, _, _, _, diagnostic = learning_course
    submitted = _all_answers(diagnostic)
    expected_scores = [10, 20, 30, 40, 50, 60]

    def forged_evaluator(
        quiz_set_id: int,
        quiz_title: str,
        questions: list[dict],
        user_answers: list[dict],
        profile: dict | None = None,
    ) -> dict:
        del quiz_set_id, quiz_title, user_answers, profile
        return {
            "score": 100,
            "level": "伪造等级",
            "summary": "伪造总结",
            "question_reviews": [
                {
                    "question_id": question["id"],
                    "question": "伪造题目",
                    "reference_answer": "伪造参考答案",
                    "user_answer": "伪造用户答案",
                    "score": expected_scores[index],
                    "feedback": "真实评分反馈",
                    "weak_point": "待加强" if index == 0 else None,
                }
                for index, question in enumerate(questions)
            ],
        }

    result = submit_diagnostic(
        user["id"],
        diagnostic["id"],
        submitted,
        evaluator=forged_evaluator,
    )

    assert result["evaluation"]["score"] == round(sum(expected_scores) / len(expected_scores))
    assert result["evaluation"]["level"] != "伪造等级"
    assert result["evaluation"]["summary"] != "伪造总结"
    _assert_no_answer_leak(result)

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT evaluation_json FROM learning_evaluations WHERE id = %s",
            (result["evaluation"]["id"],),
        )
        stored = json.loads(cursor.fetchone()["evaluation_json"])
    assert stored["question_reviews"][0]["question"] == diagnostic["questions"][0]["question"]
    assert stored["question_reviews"][0]["reference_answer"] != "伪造参考答案"
    assert stored["question_reviews"][0]["user_answer"] == submitted[0]["user_answer"]


def test_diagnostic_plan_failure_retries_without_duplicate_side_effects(learning_course):
    user, _, course, points, diagnostic = learning_course
    answers = _all_answers(diagnostic)
    evaluation_calls = 0
    persisted_plan_id = None
    base_evaluator = _evaluator({point["id"]: 75 for point in points})

    def counting_evaluator(*args, **kwargs):
        nonlocal evaluation_calls
        evaluation_calls += 1
        return base_evaluator(*args, **kwargs)

    def persist_plan_then_fail(user_id, course_id, diagnostic_quiz):
        nonlocal persisted_plan_id
        plan = generate_study_plan(user_id, course_id, diagnostic_quiz)
        persisted_plan_id = plan["id"]
        raise RuntimeError("fault after plan commit")

    with pytest.raises(RuntimeError, match="fault after plan commit"):
        submit_diagnostic(
            user["id"],
            diagnostic["id"],
            answers,
            evaluator=counting_evaluator,
            plan_provider=persist_plan_then_fail,
        )

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT status, evaluation_id FROM evaluation_attempts
            WHERE user_id = %s AND attempt_key = %s
            """,
            (user["id"], f"quiz:{diagnostic['id']}"),
        )
        failed_attempt = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) AS total FROM learning_evaluations WHERE quiz_set_id = %s",
            (diagnostic["id"],),
        )
        evaluation_count = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT COUNT(*) AS total FROM study_plans WHERE user_id = %s AND course_id = %s",
            (user["id"], course["id"]),
        )
        plan_count = cursor.fetchone()["total"]
    assert failed_attempt["status"] == "planning_failed"
    assert failed_attempt["evaluation_id"] is not None
    assert evaluation_count == 1
    assert plan_count == 1
    assert evaluation_calls == 1

    def evaluator_must_not_run(*args, **kwargs):
        raise AssertionError("retry must not evaluate or update mastery again")

    result = submit_diagnostic(
        user["id"],
        diagnostic["id"],
        answers,
        evaluator=evaluator_must_not_run,
        plan_provider=generate_study_plan,
    )

    assert result["plan"]["id"] == persisted_plan_id
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT status FROM evaluation_attempts
            WHERE user_id = %s AND attempt_key = %s
            """,
            (user["id"], f"quiz:{diagnostic['id']}"),
        )
        assert cursor.fetchone()["status"] == "completed"
        cursor.execute(
            "SELECT COUNT(*) AS total FROM learning_evaluations WHERE quiz_set_id = %s",
            (diagnostic["id"],),
        )
        assert cursor.fetchone()["total"] == 1
        cursor.execute(
            "SELECT COUNT(*) AS total FROM study_plans WHERE user_id = %s AND course_id = %s",
            (user["id"], course["id"]),
        )
        assert cursor.fetchone()["total"] == 1
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM mastery_changes change_row
            JOIN mastery_records record ON record.id = change_row.mastery_record_id
            WHERE record.user_id = %s AND record.course_id = %s
            """,
            (user["id"], course["id"]),
        )
        mastery_change_count = cursor.fetchone()["total"]
    assert mastery_change_count == len(points)

    def plan_must_not_run(*args, **kwargs):
        raise AssertionError("completed retry must return the persisted result")

    repeated = submit_diagnostic(
        user["id"],
        diagnostic["id"],
        answers,
        evaluator=evaluator_must_not_run,
        plan_provider=plan_must_not_run,
    )
    assert repeated == result


def test_concurrent_diagnostic_submission_has_single_evaluation_and_plan(learning_course):
    user, _, course, points, diagnostic = learning_course
    answers = _all_answers(diagnostic)
    evaluator_started = Event()
    release_evaluator = Event()
    base_evaluator = _evaluator({point["id"]: 80 for point in points})

    def slow_evaluator(*args, **kwargs):
        evaluator_started.set()
        assert release_evaluator.wait(timeout=10)
        return base_evaluator(*args, **kwargs)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            submit_diagnostic,
            user["id"],
            diagnostic["id"],
            answers,
            slow_evaluator,
        )
        assert evaluator_started.wait(timeout=10)
        with pytest.raises(AppError) as concurrent_error:
            submit_diagnostic(
                user["id"],
                diagnostic["id"],
                answers,
                evaluator=lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("concurrent request must not run the evaluator")
                ),
            )
        assert concurrent_error.value.error_code == "EVALUATION_IN_PROGRESS"
        release_evaluator.set()
        result = first.result(timeout=20)

    repeated = submit_diagnostic(
        user["id"],
        diagnostic["id"],
        answers,
        evaluator=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("completed retry must not run the evaluator")
        ),
    )
    assert repeated == result

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM learning_evaluations WHERE quiz_set_id = %s",
            (diagnostic["id"],),
        )
        assert cursor.fetchone()["total"] == 1
        cursor.execute(
            "SELECT COUNT(*) AS total FROM study_plans WHERE user_id = %s AND course_id = %s",
            (user["id"], course["id"]),
        )
        assert cursor.fetchone()["total"] == 1


def test_diagnostic_submission_persists_mastery_and_seven_day_plan(learning_course):
    user, _, course, points, diagnostic = learning_course
    point_scores = {points[0]["id"]: 40, points[1]["id"]: 70, points[2]["id"]: 90}

    result = submit_diagnostic(
        user["id"],
        diagnostic["id"],
        _all_answers(diagnostic),
        evaluator=_evaluator(point_scores),
    )

    changes = {item["knowledge_point_id"]: item for item in result["mastery_changes"]}
    assert {point_id: item["after"] for point_id, item in changes.items()} == point_scores
    assert all(item["evaluation_id"] == result["evaluation"]["id"] for item in changes.values())
    assert result["plan"]["days"] == 7
    assert len(result["plan"]["sessions"]) == 7
    user_today = account_service.get_user_local_date(user["id"])
    assert result["plan"]["sessions"][0]["scheduled_date"] == user_today.isoformat()
    assert result["plan"]["sessions"][-1]["scheduled_date"] == (
        user_today + timedelta(days=6)
    ).isoformat()
    assert all(item["estimated_minutes"] == course["daily_minutes"] for item in result["plan"]["sessions"])

    with get_cursor() as cursor:
        rows = repository.list_points_with_mastery(cursor, user["id"], course["id"])
    assert len(rows) == 3
    assert all(row["last_evaluation_id"] == result["evaluation"]["id"] for row in rows)


def test_plan_dates_and_exam_days_use_user_timezone(learning_course, monkeypatch):
    user, _, course, points, diagnostic = learning_course
    update_user_timezone(user["id"], "America/Los_Angeles")
    updated = update_user_course(
        user["id"],
        course["id"],
        CourseUpdate(exam_at=datetime(2026, 7, 20, 0, 30)),
    )
    assert updated["exam_at"] == datetime(2026, 7, 20, 7, 30)

    fixed_utc = datetime(2026, 7, 17, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(account_service, "utc_now", lambda: fixed_utc)
    result = submit_diagnostic(
        user["id"],
        diagnostic["id"],
        _all_answers(diagnostic),
        evaluator=_evaluator({point["id"]: 80 for point in points}),
    )

    assert result["plan"]["days"] == 5
    assert result["plan"]["sessions"][0]["scheduled_date"] == "2026-07-16"
    assert result["plan"]["sessions"][-1]["scheduled_date"] == "2026-07-20"


def test_orphaned_points_are_excluded_from_learning_and_resources(learning_course):
    user, _, course, _, _ = learning_course
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO knowledge_points
                (user_id, course_id, name, description, source_chunk_ids, sort_order, status)
            VALUES (%s, %s, '孤立知识点', '不应参与新内容', JSON_ARRAY(), 99, 'orphaned')
            """,
            (user["id"], course["id"]),
        )
        orphaned_id = cursor.lastrowid

    diagnostic_point_ids = []

    def diagnostic_provider(current_course, points, count):
        diagnostic_point_ids.extend(point["id"] for point in points)
        return _question_provider(current_course, points, count)

    generate_diagnostic(
        user["id"],
        course["id"],
        question_count=6,
        question_provider=diagnostic_provider,
    )
    plan = generate_study_plan(user["id"], course["id"])
    planned_point_ids = {
        item["knowledge_point_id"]
        for session in plan["sessions"]
        for item in session["items"]
        if item.get("knowledge_point_id") is not None
    }

    practice_point_ids = []

    def practice_provider(_course, points, count, difficulty):
        del difficulty
        practice_point_ids.extend(point["id"] for point in points)
        return [
            {
                "knowledge_point_id": points[index % len(points)]["id"],
                "question": f"练习题 {index + 1}",
                "answer": "参考答案",
                "question_type": "short_answer",
                "difficulty": "medium",
            }
            for index in range(count)
        ]

    generate_practice(
        user["id"],
        course["id"],
        question_count=3,
        question_provider=practice_provider,
    )

    assert orphaned_id not in diagnostic_point_ids
    assert orphaned_id not in planned_point_ids
    assert orphaned_id not in practice_point_ids
    with pytest.raises(AppError) as error:
        _resolve_knowledge_point(
            user["id"],
            course["id"],
            "孤立知识点",
            orphaned_id,
        )
    assert error.value.error_code == "KNOWLEDGE_POINT_NOT_FOUND"


def test_low_score_updates_mastery_and_changes_tomorrow_plan(learning_course):
    user, _, course, points, diagnostic = learning_course
    initial_scores = {points[0]["id"]: 40, points[1]["id"]: 70, points[2]["id"]: 90}
    diagnostic_result = submit_diagnostic(
        user["id"],
        diagnostic["id"],
        _all_answers(diagnostic),
        evaluator=_evaluator(initial_scores),
    )
    today = get_today_learning(user["id"], course["id"])
    practice = next(item for item in today["items"] if item.get("question"))
    point_id = practice["question"]["knowledge_point_id"]
    assert point_id == points[0]["id"]

    start_learning_session(user["id"], today["id"])
    result = submit_learning_session(
        user["id"],
        today["id"],
        [{"question_id": practice["question"]["id"], "user_answer": "故意答错"}],
        actual_minutes=21,
        evaluator=_evaluator({point_id: 20}),
    )

    change = result["mastery_changes"][0]
    assert change["before"] == initial_scores[point_id]
    assert change["after"] == pytest.approx(initial_scores[point_id] * 0.7 + 20 * 0.3)
    assert change["low_score_streak"] == 2
    assert change["evaluation_id"] == result["evaluation"]["id"]

    adaptation = result["adaptations"][0]
    assert adaptation["session_id"] == diagnostic_result["plan"]["sessions"][1]["id"]
    assert adaptation["item_types"] == ["review", "explanation", "worked_example", "practice"]
    assert "连续两次低于 60" in adaptation["reason"]
    with get_cursor() as cursor:
        tomorrow = repository.get_session(cursor, adaptation["session_id"], user["id"])
    adapted_items = [
        item
        for item in tomorrow["items"]
        if item["knowledge_point_id"] == point_id
    ]
    assert {item["item_type"] for item in adapted_items} >= {
        "review",
        "explanation",
        "worked_example",
        "practice",
    }
    assert any(
        item.get("content_ref", {}).get("spaced_review") for item in adapted_items if item["item_type"] == "review"
    )
    assert next(item for item in adapted_items if item["item_type"] == "practice")[
        "content_ref"
    ]["question_id"]


def test_today_overview_aggregates_courses_without_n_plus_one(learning_course):
    user, _, course, points, diagnostic = learning_course
    submit_diagnostic(
        user["id"],
        diagnostic["id"],
        _all_answers(diagnostic),
        evaluator=_evaluator({point["id"]: 70 for point in points}),
    )
    second = create_user_course(
        user["id"],
        CourseCreate(name="第二门课", goal="补充总览覆盖", daily_minutes=25),
    )
    overview = get_today_overview(user["id"])
    assert overview["summary"]["course_count"] >= 2
    course_ids = {item["course"]["id"] for item in overview["items"]}
    assert course["id"] in course_ids
    assert second["id"] in course_ids
    primary = next(item for item in overview["items"] if item["course"]["id"] == course["id"])
    assert primary["session"] is not None
    assert overview["summary"]["with_session"] >= 1


def test_course_workspace_overview_returns_single_payload(learning_course):
    user, _, course, points, diagnostic = learning_course
    submit_diagnostic(
        user["id"],
        diagnostic["id"],
        _all_answers(diagnostic),
        evaluator=_evaluator({point["id"]: 72 for point in points}),
    )
    overview = get_course_workspace_overview(user["id"], course["id"])
    assert overview["course"]["id"] == course["id"]
    assert overview["progress"]["course"]["id"] == course["id"]
    assert overview["today"] is not None
    assert overview["plan"] is not None
    assert overview["roadmap"] is not None
    assert "attempts" in overview["practice"]


def test_completed_session_restores_as_today_and_cannot_be_submitted_twice(learning_course):
    user, _, course, points, diagnostic = learning_course
    submit_diagnostic(
        user["id"],
        diagnostic["id"],
        _all_answers(diagnostic),
        evaluator=_evaluator({point["id"]: 70 for point in points}),
    )
    today = get_today_learning(user["id"], course["id"])
    practice = next(item for item in today["items"] if item.get("question"))
    payload = [{"question_id": practice["question"]["id"], "user_answer": "已完成"}]
    submit_learning_session(
        user["id"],
        today["id"],
        payload,
        evaluator=_evaluator({practice["knowledge_point_id"]: 75}),
    )

    restored_today = get_today_learning(user["id"], course["id"])
    assert restored_today["id"] == today["id"]
    assert restored_today["status"] == "evaluated"
    progress = get_course_progress(user["id"], course["id"])
    assert progress["session_completed"] == 1
    assert progress["session_total"] == 7
    assert progress["completion_rate"] == pytest.approx(14.29)

    with pytest.raises(AppError) as error:
        submit_learning_session(
            user["id"],
            today["id"],
            payload,
            evaluator=_evaluator({practice["knowledge_point_id"]: 75}),
        )
    assert error.value.status_code == 409
    assert error.value.error_code == "SESSION_ALREADY_SUBMITTED"


def test_session_without_practice_can_be_completed(learning_course):
    user, _, course, points, _ = learning_course
    with get_cursor() as cursor:
        session_id = repository.create_session(
            cursor,
            user["id"],
            course["id"],
            None,
            date.today(),
            course["daily_minutes"],
        )
        repository.add_session_item(
            cursor,
            session_id,
            points[0]["id"],
            "explanation",
            "只读学习内容",
            {},
            0,
            "test:completion-only",
        )

    result = submit_learning_session(user["id"], session_id, [], actual_minutes=12)

    assert result == {"evaluation": None, "mastery_changes": [], "adaptations": []}
    with get_cursor() as cursor:
        completed = repository.get_session(cursor, session_id, user["id"])
    assert completed["status"] == "completed"
    assert completed["actual_minutes"] == 12


def test_learning_loop_is_isolated_between_users(learning_course):
    user, other_user, course, _, diagnostic = learning_course

    with pytest.raises(AppError) as diagnostic_error:
        get_diagnostic(other_user["id"], diagnostic["id"])
    assert diagnostic_error.value.status_code == 404

    with pytest.raises(AppError) as progress_error:
        get_course_progress(other_user["id"], course["id"])
    assert progress_error.value.status_code == 404

    own_diagnostic = get_diagnostic(user["id"], diagnostic["id"])
    assert own_diagnostic["id"] == diagnostic["id"]


def test_diagnostic_fallback_returns_requested_count_and_coverage(monkeypatch):
    monkeypatch.setattr(
        diagnostic_generator,
        "get_llm",
        lambda: (_ for _ in ()).throw(RuntimeError("LLM unavailable")),
    )
    points = [
        {"id": index, "name": f"知识点 {index}", "description": "测试描述"}
        for index in range(1, 4)
    ]

    questions = diagnostic_generator.generate_diagnostic_questions(
        {"name": "测试课程"},
        points,
        8,
    )

    assert len(questions) == 8
    assert {item["knowledge_point_id"] for item in questions} == {1, 2, 3}


def test_mock_llm_skips_external_diagnostic_generation(monkeypatch):
    monkeypatch.setattr(
        diagnostic_generator,
        "get_settings",
        lambda: type("Settings", (), {"mock_llm": True})(),
    )
    monkeypatch.setattr(
        diagnostic_generator,
        "get_llm",
        lambda: (_ for _ in ()).throw(AssertionError("LLM must not be called")),
    )
    points = [
        {"id": index, "name": f"知识点 {index}", "description": "测试描述"}
        for index in range(1, 4)
    ]

    questions = diagnostic_generator.generate_diagnostic_questions(
        {"name": "测试课程"},
        points,
        6,
    )

    assert len(questions) == 6
    assert {item["knowledge_point_id"] for item in questions} == {1, 2, 3}


def test_diagnostic_question_count_is_validated_by_api(api_client, two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="参数校验课程"))

    too_few = api_client.post(
        f"/api/v1/courses/{course['id']}/diagnostic",
        json={"question_count": 4},
    )
    too_many = api_client.post(
        f"/api/v1/courses/{course['id']}/diagnostic",
        json={"question_count": 9},
    )

    assert too_few.status_code == 422
    assert too_many.status_code == 422
