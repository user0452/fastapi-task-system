from __future__ import annotations

import pytest

from app.core.database import get_cursor
from app.jobs import learning_memory_job
from app.modules.agent import repository
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course


@pytest.fixture
def summary_scope(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="摘要测试课程", goal="验证异步摘要"))
    with get_cursor() as cursor:
        agent = repository.ensure_course_agent(cursor, user["id"], course)
    return user, course, agent["primary_session"], agent


def _add_rounds(user_id: int, course_id: int, session_id: int, count: int) -> None:
    with get_cursor() as cursor:
        for index in range(count):
            repository.add_message(cursor, user_id, session_id, course_id, "user", f"问题 {index}: TCP 状态")
            repository.add_message(cursor, user_id, session_id, course_id, "assistant", f"回答 {index}: 已确认状态结论")


def test_incremental_summary_job_is_idempotent_and_advances_watermark(summary_scope):
    user, course, session, agent = summary_scope
    _add_rounds(user["id"], course["id"], session["id"], 9)
    with get_cursor() as cursor:
        first = learning_memory_job.enqueue_conversation_summary_if_needed(
            cursor, user_id=user["id"], course_id=course["id"], agent_id=agent["id"], session_id=session["id"]
        )
        second = learning_memory_job.enqueue_conversation_summary_if_needed(
            cursor, user_id=user["id"], course_id=course["id"], agent_id=agent["id"], session_id=session["id"]
        )
    assert first and second and first["id"] == second["id"]
    assert learning_memory_job.run_learning_memory_job(first["id"]) is True
    with get_cursor() as cursor:
        state = repository.get_session_context_state(
            cursor, user_id=user["id"], course_id=course["id"], session_id=session["id"]
        )
        blocks = repository.list_active_conversation_summary_blocks(
            cursor, user_id=user["id"], course_id=course["id"], session_id=session["id"]
        )
    assert len(blocks) == 1
    assert state["covered_until_message_id"] == blocks[0]["end_message_id"]
    assert blocks[0]["end_message_id"] - blocks[0]["start_message_id"] == 7


def test_summary_commit_failure_never_advances_watermark_or_removes_messages(summary_scope, monkeypatch):
    user, course, session, agent = summary_scope
    _add_rounds(user["id"], course["id"], session["id"], 9)
    with get_cursor() as cursor:
        job = learning_memory_job.enqueue_conversation_summary_if_needed(
            cursor, user_id=user["id"], course_id=course["id"], agent_id=agent["id"], session_id=session["id"]
        )
    monkeypatch.setattr(learning_memory_job.repository, "commit_conversation_summary_block", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db failure")))
    for _ in range(3):
        with get_cursor() as cursor:
            cursor.execute("UPDATE learning_memory_jobs SET available_at = CURRENT_TIMESTAMP(6) WHERE id = %s", (job["id"],))
        learning_memory_job.run_learning_memory_job(job["id"])
    with get_cursor() as cursor:
        state = repository.get_session_context_state(
            cursor, user_id=user["id"], course_id=course["id"], session_id=session["id"]
        )
        messages = repository.list_session_messages_for_context(cursor, user_id=user["id"], session_id=session["id"])
        stored = repository.get_learning_memory_job(cursor, job["id"])
    assert state["covered_until_message_id"] is None
    assert len(messages) == 18
    assert stored["status"] == "failed"


def test_compaction_only_replaces_oldest_selected_blocks(summary_scope):
    user, course, session, agent = summary_scope
    with get_cursor() as cursor:
        for index in range(5):
            cursor.execute(
                """
                INSERT INTO conversation_summary_blocks
                    (user_id, course_id, session_id, start_message_id, end_message_id,
                     summary_text, token_count, status, summary_version, level)
                VALUES (%s, %s, %s, %s, %s, %s, 10, 'active', 1, 0)
                """,
                (user["id"], course["id"], session["id"], index * 8 + 1, index * 8 + 8, f"块 {index}"),
            )
        blocks = repository.list_active_conversation_summary_blocks(
            cursor, user_id=user["id"], course_id=course["id"], session_id=session["id"]
        )
        job = repository.enqueue_learning_memory_job(
            cursor, job_type="conversation_summary_compact", user_id=user["id"], course_id=course["id"],
            agent_id=agent["id"], session_id=session["id"], source_message_id=None,
            idempotency_key=f"test-compact:{session['id']}", payload={"source_block_ids": [item["id"] for item in blocks[:4]]},
        )
    assert learning_memory_job.run_learning_memory_job(job["id"]) is True
    with get_cursor() as cursor:
        active = repository.list_active_conversation_summary_blocks(
            cursor, user_id=user["id"], course_id=course["id"], session_id=session["id"]
        )
    assert len(active) == 2
    assert any(item["start_message_id"] == 1 and item["end_message_id"] == 32 for item in active)
    assert any(item["start_message_id"] == 33 and item["end_message_id"] == 40 for item in active)
