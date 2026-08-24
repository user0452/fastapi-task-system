from app.core.database import get_cursor
from app.modules.adaptive.service import (
    add_question_bank,
    get_overview,
    get_progress,
    start_action,
    submit_action,
)
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course


def _seed_objectives(user_id: int, course_id: int) -> tuple[int, int]:
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO learning_objectives
                (user_id, course_id, title, description, required_ability, importance, difficulty)
            VALUES
                (%s, %s, '解释基础协议的核心机制', '能够解释基础协议的关键机制并指出适用条件。', '给定场景，说明机制和适用条件。', 0.70, 'medium'),
                (%s, %s, '判断高级场景中的窗口变化', '能够根据状态变量判断高级场景中的窗口变化。', '给定状态和 ACK，判断窗口变化。', 0.95, 'hard')
            """,
            (user_id, course_id, user_id, course_id),
        )
        cursor.execute(
            "SELECT id FROM learning_objectives WHERE user_id = %s AND course_id = %s ORDER BY id",
            (user_id, course_id),
        )
        ids = [int(row["id"]) for row in cursor.fetchall()]
        cursor.execute(
            """
            INSERT INTO objective_relations
                (user_id, course_id, source_objective_id, target_objective_id,
                 relation_type, confidence, rationale)
            VALUES (%s, %s, %s, %s, 'prerequisite', 0.95, '基础机制是高级场景判断的前置能力')
            """,
            (user_id, course_id, ids[0], ids[1]),
        )
        cursor.execute(
            """
            INSERT INTO student_objective_states
                (user_id, course_id, objective_id, mastery, confidence, attempt_count, state)
            VALUES (%s, %s, %s, 0.40, 0.40, 2, 'learning')
            """,
            (user_id, course_id, ids[0]),
        )
    return ids[0], ids[1]


def test_adaptive_loop_retrieves_question_records_evidence_and_changes_action(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="Adaptive 网络课"))
    first_objective, second_objective = _seed_objectives(user["id"], course["id"])
    added = add_question_bank(
        user["id"],
        course["id"],
        [
            {
                "content": "给定基础协议的状态，请说明核心机制和适用条件。",
                "answer": "核心机制 适用条件 状态",
                "explanation": "先识别状态，再说明机制。",
                "difficulty": "medium",
                "source_type": "user_upload",
                "objective_ids": [first_objective],
                "coverage_type": "scenario",
            },
            {
                "content": "给定窗口和 ACK 状态，请判断高级场景中的窗口变化。",
                "answer": "窗口 ACK 状态变化",
                "difficulty": "hard",
                "source_type": "textbook",
                "objective_ids": [second_objective],
                "coverage_type": "scenario",
            },
        ],
    )

    assert added["created_count"] == 2
    overview = get_overview(user["id"], course["id"])
    action = overview["next_action"]
    assert action["objective_id"] == first_objective
    assert action["action_type"] == "practice"
    assert action["question"]["id"] == added["created"][0]["id"]

    started = start_action(user["id"], action["id"])
    assert started["status"] == "in_progress"
    result = submit_action(
        user["id"],
        action["id"],
        {"response": "核心机制和适用条件取决于状态，先识别状态。"},
    )

    assert result["evidence_id"] > 0
    assert result["attempt_id"] > 0
    assert result["state"]["attempt_count"] == 3
    assert result["next_action"]["objective_id"] == second_objective
    assert result["next_action"]["action_type"] == "explain"

    progress = get_progress(user["id"], course["id"])
    first = next(item for item in progress["objectives"] if item["id"] == first_objective)
    assert first["confidence"] > 0.40
    assert first["evidence"]
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT source_type, grader_type, mastery_before, mastery_after FROM learning_evidence WHERE id = %s",
            (result["evidence_id"],),
        )
        evidence = cursor.fetchone()
    assert evidence["source_type"] == "practice"
    assert evidence["grader_type"] == "deterministic-keyword"
    assert evidence["mastery_after"] > evidence["mastery_before"]
