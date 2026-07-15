from datetime import timedelta

import pytest

from app.core.database import get_cursor
from app.core.errors import AppError
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course
from app.modules.learning.service import (
    generate_practice,
    get_practice_statistics,
    get_study_plan,
    get_wrong_answers,
    reschedule_learning_session,
    submit_practice,
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
                (user_id, course_id, name, f"{name}的核心方法", index),
            )
            points.append({"id": cursor.lastrowid, "name": name, "description": f"{name}的核心方法"})
    return points


def _question_provider(_course, points, count, difficulty):
    return [
        {
            "knowledge_point_id": points[index % len(points)]["id"],
            "question": f"请说明{points[index % len(points)]['name']}的应用步骤。",
            "answer": points[index % len(points)]["description"],
            "question_type": "short_answer",
            "difficulty": difficulty,
        }
        for index in range(count)
    ]


def _evaluator(quiz_set_id, quiz_title, questions, user_answers, profile=None):
    del quiz_title, profile
    answer_map = {item["question_id"]: item["user_answer"] for item in user_answers}
    scores = [35, 75, 90]
    reviews = []
    for index, question in enumerate(questions):
        if question["id"] not in answer_map:
            continue
        score = scores[index % len(scores)]
        reviews.append(
            {
                "question_id": question["id"],
                "question": question["question"],
                "reference_answer": question["answer"],
                "user_answer": answer_map[question["id"]],
                "score": score,
                "feedback": "保留具体评分依据",
                "weak_point": "步骤不完整" if score < 60 else None,
            }
        )
    return {
        "quiz_set_id": quiz_set_id,
        "score": round(sum(item["score"] for item in reviews) / len(reviews)),
        "level": "针对性练习",
        "summary": "已根据答案完成批改",
        "weak_points": ["步骤不完整"],
        "suggestions": ["完成错题重练"],
        "question_reviews": reviews,
    }


def test_chat_practice_submission_updates_mastery_stats_wrong_answers_and_plan(two_users):
    user, other_user = two_users
    course = create_user_course(user["id"], CourseCreate(name="聊天练习闭环"))
    points = _insert_points(user["id"], course["id"])
    practice = generate_practice(
        user["id"],
        course["id"],
        question_count=3,
        question_provider=_question_provider,
    )
    answers = [
        {"question_id": question["id"], "user_answer": "我的作答"}
        for question in practice["questions"]
    ]

    result = submit_practice(user["id"], practice["id"], answers, evaluator=_evaluator)

    assert result["evaluation"]["score"] == 67
    assert len(result["mastery_changes"]) == 3
    assert {item["knowledge_point_id"] for item in result["mastery_changes"]} == {
        point["id"] for point in points
    }
    low_change = next(item for item in result["mastery_changes"] if item["assessment_score"] < 60)
    low_adaptation = next(
        item for item in result["adaptations"] if item["knowledge_point_id"] == low_change["knowledge_point_id"]
    )
    assert set(low_adaptation["item_types"]) == {"review", "explanation", "practice"}

    stats = get_practice_statistics(user["id"], course["id"])
    wrong = get_wrong_answers(user["id"], course["id"])
    assert stats["attempts"] == 1
    assert stats["answered"] == 3
    assert stats["wrong"] == 1
    assert wrong["total"] == 1
    assert wrong["items"][0]["reference_answer"]

    plan = get_study_plan(user["id"], course["id"])
    session = next(item for item in plan["sessions"] if item["status"] == "planned")
    new_date = session["scheduled_date"] + timedelta(days=2)
    adjusted = reschedule_learning_session(user["id"], session["id"], new_date, 45)
    assert adjusted["scheduled_date"] == new_date
    assert adjusted["estimated_minutes"] == 45
    with pytest.raises(AppError) as denied:
        reschedule_learning_session(other_user["id"], session["id"], new_date, 50)
    assert denied.value.status_code == 404

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM operation_logs
            WHERE user_id = %s AND action = 'COURSE_PRACTICE_SUBMITTED'
              AND target_id = %s
            """,
            (user["id"], practice["id"]),
        )
        assert cursor.fetchone()["total"] == 1
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM operation_logs
            WHERE user_id = %s AND action = 'COURSE_SESSION_RESCHEDULED'
              AND target_id = %s
            """,
            (user["id"], session["id"]),
        )
        assert cursor.fetchone()["total"] == 1
