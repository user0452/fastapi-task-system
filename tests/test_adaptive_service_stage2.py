import asyncio
import json

from app.core.database import get_cursor
from app.modules.adaptive import service as adaptive_service
from app.modules.adaptive.service import (
    add_question_bank,
    commit_question_import,
    get_overview,
    get_sources,
    preview_question_bank_upload,
    start_action,
    submit_action,
    submit_tutor_check,
    tutor_chat,
)
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course
from tests.test_adaptive_learning import _seed_objectives


def _question_bank_bytes():
    return json.dumps(
        {
            "questions": [
                {
                    "content": "给定基础协议状态，请说明核心机制和适用条件。",
                    "question_type": "scenario",
                    "answer": "核心机制和适用条件取决于状态。",
                    "difficulty": "medium",
                },
                {
                    "content": "给定窗口和 ACK 状态，请判断高级场景中的窗口变化。",
                    "question_type": "short_answer",
                    "answer": "根据窗口和 ACK 状态判断变化。",
                    "difficulty": "hard",
                },
            ]
        },
        ensure_ascii=False,
    ).encode()


def test_question_bank_import_is_previewed_committed_and_idempotent(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="题库导入测试"))
    first_objective, _ = _seed_objectives(user["id"], course["id"])

    first_preview = asyncio.run(
        preview_question_bank_upload(
            user["id"],
            course["id"],
            "questions.json",
            _question_bank_bytes(),
            "import-test-key-001",
        )
    )
    second_preview = asyncio.run(
        preview_question_bank_upload(
            user["id"],
            course["id"],
            "questions.json",
            _question_bank_bytes(),
            "import-test-key-001",
        )
    )
    assert first_preview["batch"]["id"] == second_preview["batch"]["id"]
    assert first_preview["batch"]["matched_count"] == 2
    assert all(item["objective_ids"] for item in first_preview["items"])
    assert first_objective in first_preview["items"][0]["objective_ids"]

    committed = commit_question_import(user["id"], course["id"], first_preview["batch"]["id"])
    repeated = commit_question_import(user["id"], course["id"], first_preview["batch"]["id"])
    assert len(committed["created"]) == 2
    assert repeated["idempotent"] is True
    assert len(repeated["created"]) == 0
    sources = get_sources(user["id"], course["id"])
    assert sources["counts"]["question_count"] == 2
    assert sources["import_batches"][0]["status"] == "imported"


def test_retrieval_first_does_not_call_generator_when_real_question_exists(two_users, monkeypatch):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="题库优先测试"))
    first_objective, _ = _seed_objectives(user["id"], course["id"])
    add_question_bank(
        user["id"],
        course["id"],
        [
            {
                "content": "给定基础协议的状态，请说明核心机制和适用条件。",
                "question_type": "scenario",
                "answer": "核心机制和适用条件取决于状态。",
                "difficulty": "medium",
                "source_type": "textbook",
                "objective_ids": [first_objective],
                "coverage_type": "scenario",
                "quality_score": 0.95,
            }
        ],
    )

    def generator_must_not_run(**_kwargs):
        raise AssertionError("真实高质量题目存在时不应调用生成器")

    monkeypatch.setattr(adaptive_service, "generate_grounded_question", generator_must_not_run)
    action = get_overview(user["id"], course["id"])["next_action"]
    assert action["question"]["source_type"] == "textbook"


def test_tutor_chat_never_writes_evidence_but_tutor_check_does(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="Tutor Check 测试"))
    first_objective, _ = _seed_objectives(user["id"], course["id"])
    add_question_bank(
        user["id"],
        course["id"],
        [
            {
                "content": "给定基础协议的状态，请说明核心机制和适用条件。",
                "answer": "核心机制和适用条件取决于状态。",
                "question_type": "scenario",
                "objective_ids": [first_objective],
                "coverage_type": "scenario",
            }
        ],
    )
    action = get_overview(user["id"], course["id"])["next_action"]

    before = _evidence_count(user["id"], course["id"])
    chat = tutor_chat(
        user["id"],
        course["id"],
        message="给个例子",
        intent="example",
        action_id=action["id"],
    )
    assert chat["citations"] == []
    assert chat["evidence_written"] is False
    assert _evidence_count(user["id"], course["id"]) == before

    check_chat = tutor_chat(
        user["id"],
        course["id"],
        message="检查我是否理解",
        intent="check_understanding",
        action_id=action["id"],
    )
    check_id = check_chat["tutor_check"]["id"]
    result = submit_tutor_check(
        user["id"],
        course["id"],
        check_id,
        "我会先识别状态，再说明核心机制和适用条件。",
        "tutor-check-test-key-001",
    )
    repeated = submit_tutor_check(
        user["id"],
        course["id"],
        check_id,
        "我会先识别状态，再说明核心机制和适用条件。",
        "tutor-check-test-key-001",
    )
    assert result["evidence_id"] > 0
    assert repeated["idempotent"] is True
    assert _evidence_count(user["id"], course["id"]) == before + 1
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT source_type, action_id FROM learning_evidence WHERE id = %s",
            (result["evidence_id"],),
        )
        evidence = cursor.fetchone()
    assert evidence["source_type"] == "tutor_check"
    assert evidence["action_id"] == action["id"]


def test_practice_submission_is_idempotent_and_creates_one_evidence(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="Evidence 幂等测试"))
    first_objective, _ = _seed_objectives(user["id"], course["id"])
    add_question_bank(
        user["id"],
        course["id"],
        [
            {
                "content": "给定基础协议的状态，请说明核心机制和适用条件。",
                "answer": "核心机制和适用条件取决于状态。",
                "question_type": "scenario",
                "objective_ids": [first_objective],
            }
        ],
    )
    action = get_overview(user["id"], course["id"])["next_action"]
    start_action(user["id"], action["id"])
    payload = {
        "response": "核心机制和适用条件取决于状态，先识别状态。",
        "idempotency_key": "practice-test-key-001",
    }
    first = submit_action(user["id"], action["id"], payload)
    repeated = submit_action(user["id"], action["id"], payload)
    assert first["evidence_id"] == repeated["evidence_id"]
    assert repeated["idempotent"] is True
    assert _evidence_count(user["id"], course["id"]) == 1


def _evidence_count(user_id: int, course_id: int) -> int:
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM learning_evidence WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        )
        return int(cursor.fetchone()["total"])
