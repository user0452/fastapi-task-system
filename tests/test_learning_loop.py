from datetime import date, timedelta

import pytest

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.llm import diagnostic_generator
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course
from app.modules.learning import repository
from app.modules.learning.service import (
    generate_diagnostic,
    get_course_progress,
    get_diagnostic,
    get_today_learning,
    start_learning_session,
    submit_diagnostic,
    submit_learning_session,
)


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


def test_diagnostic_has_measurable_coverage_and_hides_answers(learning_course):
    user, _, _, _, diagnostic = learning_course

    assert len(diagnostic["questions"]) == 6
    assert len({item["knowledge_point_id"] for item in diagnostic["questions"]}) == 3
    assert all("answer" not in item for item in diagnostic["questions"])

    restored = get_diagnostic(user["id"], diagnostic["id"])
    assert restored["id"] == diagnostic["id"]
    assert all("answer" not in item for item in restored["questions"])


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
    assert result["plan"]["sessions"][0]["scheduled_date"] == date.today()
    assert result["plan"]["sessions"][-1]["scheduled_date"] == date.today() + timedelta(days=6)
    assert all(item["estimated_minutes"] == course["daily_minutes"] for item in result["plan"]["sessions"])

    with get_cursor() as cursor:
        rows = repository.list_points_with_mastery(cursor, user["id"], course["id"])
    assert len(rows) == 3
    assert all(row["last_evaluation_id"] == result["evaluation"]["id"] for row in rows)


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
        and item["content_ref"].get("mastery_change_id") == change["id"]
    ]
    assert {item["item_type"] for item in adapted_items} == {
        "review",
        "explanation",
        "worked_example",
        "practice",
    }
    assert next(item for item in adapted_items if item["item_type"] == "practice")[
        "content_ref"
    ]["question_id"]


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
