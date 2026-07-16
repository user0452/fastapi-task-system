import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.llm.mysql_checkpointer import get_mysql_checkpointer
from app.modules.account import service as account_service
from app.modules.account.service import update_user_timezone
from app.modules.agent import repository
from app.modules.agent import service as agent_service
from app.modules.agent.schemas import AgentChatRequest, ChatSessionCreate
from app.modules.agent.service import (
    _execute_tool,
    archive_chat_session,
    create_chat_session,
    decide_action,
    gc_agent_checkpoints,
    get_chat_session,
    list_chat_sessions,
    run_agent_chat,
    run_native_tool_agent_chat_async,
)
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course


def _reply_provider(
    message,
    course,
    profile,
    mastery,
    recent_messages,
    citations,
    current_time,
):
    del message, profile, mastery, recent_messages, current_time
    return f"这是《{course['name']}》的资料内回答，共引用 {len(citations)} 条资料。"


def _search_provider(_user_id, _course_id, _query, _top_k):
    return {
        "citations": [
            {
                "chunk_id": 9001,
                "material_id": 8001,
                "material_title": "课程讲义",
                "filename": "lesson.txt",
                "page_number": 2,
                "chunk_index": 3,
                "score": 0.94,
                "snippet": "边界值分析需要覆盖边界本身以及边界附近的输入。",
            }
        ]
    }


@pytest.fixture
def agent_course(two_users):
    user, other_user = two_users
    course = create_user_course(
        user["id"],
        CourseCreate(name="Agent 测试课程", goal="验证会话和受控工具"),
    )
    return user, other_user, course


def test_course_qa_binds_current_course_and_persists_citations(agent_course):
    user, _, course = agent_course
    result = run_agent_chat(
        user["id"],
        AgentChatRequest(
            message="边界值分析怎么用？",
            current_time="2026-07-11 14:30 UTC+08:00",
        ),
        reply_provider=_reply_provider,
        search_provider=_search_provider,
    )

    assert result["course"]["id"] == course["id"]
    assert result["intent"] == "course_qa"
    assert len(result["citations"]) == 1
    assert result["citations"][0]["chunk_id"] == 9001

    restored = get_chat_session(user["id"], result["session"]["id"])
    assert [message["role"] for message in restored["messages"]] == ["user", "assistant"]
    assert restored["messages"][0]["client_time_hint"] == "2026-07-11 14:30 UTC+08:00"
    assert restored["messages"][1]["sources"][0]["material_id"] == 8001


def test_client_time_hint_does_not_override_server_clock(agent_course, monkeypatch):
    user, _, _ = agent_course
    update_user_timezone(user["id"], "Asia/Shanghai")
    fixed_utc = datetime(2026, 7, 16, 16, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(account_service, "utc_now", lambda: fixed_utc)
    provider_times = []

    def capture_time(
        message,
        course,
        profile,
        mastery,
        recent_messages,
        citations,
        current_time,
    ):
        del message, course, profile, mastery, recent_messages, citations
        provider_times.append(current_time)
        return "服务端时间已使用"

    result = run_agent_chat(
        user["id"],
        AgentChatRequest(
            message="解释边界值分析",
            current_time="2099-01-01 00:00 UTC",
        ),
        reply_provider=capture_time,
        search_provider=_search_provider,
    )

    assert provider_times == ["2026-07-17T00:30:00+08:00"]
    assert result["current_time"] == "2026-07-17T00:30:00+08:00"
    restored = get_chat_session(user["id"], result["session"]["id"])
    assert restored["messages"][0]["client_time_hint"] == "2099-01-01 00:00 UTC"


def test_current_user_message_is_not_duplicated_in_prompt_history(agent_course):
    user, _, _ = agent_course
    current_message = "本轮唯一输入标记"
    captured_history = []

    def capture_history(
        message,
        course,
        profile,
        mastery,
        recent_messages,
        citations,
        current_time,
    ):
        del course, profile, mastery, citations, current_time
        assert message == current_message
        captured_history.extend(item["content"] for item in recent_messages)
        return "已处理"

    run_agent_chat(
        user["id"],
        AgentChatRequest(message=current_message),
        reply_provider=capture_history,
        search_provider=_search_provider,
    )

    assert current_message not in captured_history


def test_chat_history_restores_through_backend_api(api_client, agent_course):
    user, _, _ = agent_course
    result = run_agent_chat(
        user["id"],
        AgentChatRequest(message="解释一下等价类划分"),
        reply_provider=_reply_provider,
        search_provider=_search_provider,
    )

    response = api_client.get(f"/api/v1/agent/sessions/{result['session']['id']}")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["session"]["id"] == result["session"]["id"]
    assert len(payload["messages"]) == 2
    assert payload["messages"][1]["sources"][0]["score"] == 0.94


def test_client_request_id_reuses_existing_message_and_run(agent_course):
    user, _, _ = agent_course
    client_request_id = uuid4()
    request = AgentChatRequest(
        message="解释一下边界值分析",
        client_request_id=client_request_id,
    )

    first = run_agent_chat(
        user["id"],
        request,
        reply_provider=_reply_provider,
        search_provider=_search_provider,
    )
    repeated = run_agent_chat(
        user["id"],
        request,
        reply_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("duplicate request must not call the model")
        ),
        search_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("duplicate request must not call tools")
        ),
    )

    assert repeated["idempotent"] is True
    assert repeated["run_id"] == first["run_id"]
    assert repeated["message"]["id"] == first["message"]["id"]
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM agent_runs
            WHERE user_id = %s AND id = %s
            """,
            (user["id"], first["run_id"]),
        )
        assert cursor.fetchone()["total"] == 1
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM agent_chat_messages
            WHERE user_id = %s AND session_id = %s AND content = %s
            """,
            (user["id"], first["session"]["id"], request.message),
        )
        assert cursor.fetchone()["total"] == 1


def test_tool_call_idempotency_reuses_completed_result(agent_course):
    user, _, course = agent_course
    chat = run_agent_chat(
        user["id"],
        AgentChatRequest(message="先建立一个运行"),
        reply_provider=_reply_provider,
        search_provider=_search_provider,
    )
    with get_cursor() as cursor:
        run = repository.get_agent_run(cursor, chat["run_id"], user["id"])
    calls = 0

    def callback():
        nonlocal calls
        calls += 1
        return {"value": 7}

    context = {"run": run, "course": course}
    first = _execute_tool(user["id"], context, "stable_tool", "write", {"x": 1}, callback)
    repeated = _execute_tool(user["id"], context, "stable_tool", "write", {"x": 1}, callback)

    assert first == repeated == {"value": 7}
    assert calls == 1
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM agent_tool_calls
            WHERE run_id = %s AND tool_name = 'stable_tool'
            """,
            (chat["run_id"],),
        )
        assert cursor.fetchone()["total"] == 1


def test_async_agent_cancellation_marks_run_cancelled(agent_course, monkeypatch):
    user, _, _ = agent_course
    delta_seen = asyncio.Event()
    artifacts = SimpleNamespace(citations=[], cards=[], resources=[], actions=[])

    class BlockingAgent:
        async def astream(self, *_args, **_kwargs):
            yield AIMessageChunk(content="partial"), {}
            await asyncio.Event().wait()

        async def aget_state(self, _config):
            raise AssertionError("cancelled stream must not request final state")

    monkeypatch.setattr(
        agent_service,
        "_build_native_agent",
        lambda _user_id, _context: (BlockingAgent(), artifacts),
    )
    request = AgentChatRequest(message="需要取消的请求", client_request_id=uuid4())

    async def scenario():
        task = asyncio.create_task(
            run_native_tool_agent_chat_async(
                user["id"],
                request,
                on_delta=lambda _delta: delta_seen.set(),
            )
        )
        await asyncio.wait_for(delta_seen.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT status, error_message
            FROM agent_runs
            WHERE user_id = %s
            ORDER BY id DESC LIMIT 1
            """,
            (user["id"],),
        )
        run = cursor.fetchone()
    assert run["status"] == "cancelled"
    assert "取消" in run["error_message"]


def test_normal_async_agent_completion_removes_checkpoint(agent_course, monkeypatch):
    user, _, _ = agent_course
    artifacts = SimpleNamespace(citations=[], cards=[], resources=[], actions=[])
    deleted_threads = []

    class CompletedAgent:
        async def astream(self, *_args, **_kwargs):
            yield AIMessageChunk(content="完成"), {}

        async def aget_state(self, _config):
            return SimpleNamespace(
                values={"messages": [AIMessage(content="已经完成")]},
                interrupts=[],
            )

    monkeypatch.setattr(
        agent_service,
        "_build_native_agent",
        lambda _user_id, _context: (CompletedAgent(), artifacts),
    )
    monkeypatch.setattr(
        agent_service,
        "get_mysql_checkpointer",
        lambda: SimpleNamespace(delete_thread=deleted_threads.append),
    )

    result = asyncio.run(
        run_native_tool_agent_chat_async(
            user["id"],
            AgentChatRequest(message="正常完成", client_request_id=uuid4()),
        )
    )

    assert result["reply"] == "已经完成"
    assert len(deleted_threads) == 1
    assert deleted_threads[0].startswith("course-agent-")


def test_expired_resuming_action_can_be_reclaimed(agent_course, monkeypatch):
    user, _, course = agent_course
    session = create_chat_session(
        user["id"],
        ChatSessionCreate(course_id=course["id"], title="恢复确认"),
    )
    now = agent_service._utc_now()
    with get_cursor() as cursor:
        action = repository.create_action_request(
            cursor,
            user["id"],
            session["id"],
            course["id"],
            "delete_task",
            {"task_id": 999999},
            uuid4().hex,
            now + timedelta(minutes=10),
            now,
            checkpoint={
                "thread_id": f"resume-{uuid4().hex}",
                "run_id": 123,
                "resume_owner": "dead-worker",
                "resume_started_at": (now - timedelta(minutes=10)).isoformat(),
                "resume_lease_expires_at": (now - timedelta(minutes=5)).isoformat(),
            },
        )
        cursor.execute(
            "UPDATE agent_action_requests SET status = 'resuming' WHERE id = %s",
            (action["id"],),
        )

    monkeypatch.setattr(
        agent_service,
        "_resume_native_action",
        lambda _user_id, _action, _confirmed: {
            "reply": "恢复完成",
            "message": {"id": 1},
            "result": {"task_id": 999999, "deleted": False},
        },
    )
    result = decide_action(user["id"], action["id"], confirmed=True)

    assert result["status"] == "executed"
    with get_cursor() as cursor:
        stored = repository.get_action_request(cursor, action["id"], user["id"])
    assert stored["status"] == "executed"
    assert "resume_owner" not in (stored.get("checkpoint") or {})


def test_checkpoint_gc_keeps_active_actions_and_removes_unreferenced(agent_course):
    user, _, course = agent_course
    session = create_chat_session(
        user["id"],
        ChatSessionCreate(course_id=course["id"], title="Checkpoint GC"),
    )
    stale_thread = f"stale-{uuid4().hex}"
    active_thread = f"active-{uuid4().hex}"
    old = agent_service._utc_now() - timedelta(hours=3)
    with get_cursor() as cursor:
        for thread_id in (stale_thread, active_thread):
            cursor.execute(
                """
                INSERT INTO agent_graph_checkpoints
                    (thread_id, checkpoint_ns, checkpoint_id,
                     checkpoint_type, checkpoint_blob, metadata_type, metadata_blob,
                     created_at)
                VALUES (%s, '', '1', 'json', %s, 'json', %s, %s)
                """,
                (thread_id, b"{}", b"{}", old),
            )
        action = repository.create_action_request(
            cursor,
            user["id"],
            session["id"],
            course["id"],
            "delete_task",
            {"task_id": 123},
            uuid4().hex,
            agent_service._utc_now() + timedelta(minutes=10),
            agent_service._utc_now(),
            checkpoint={"thread_id": active_thread, "run_id": 1},
        )

    removed = gc_agent_checkpoints(retention_minutes=60)

    assert removed >= 1
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT thread_id FROM agent_graph_checkpoints
            WHERE thread_id IN (%s, %s)
            """,
            (stale_thread, active_thread),
        )
        remaining = {row["thread_id"] for row in cursor.fetchall()}
        repository.set_action_status(cursor, action["id"], "cancelled")
    assert stale_thread not in remaining
    assert active_thread in remaining
    get_mysql_checkpointer().delete_thread(active_thread)


def test_agent_sessions_are_isolated_between_users(agent_course):
    user, other_user, _ = agent_course
    result = run_agent_chat(
        user["id"],
        AgentChatRequest(message="课程资料里讲了什么？"),
        reply_provider=_reply_provider,
        search_provider=_search_provider,
    )

    with pytest.raises(AppError) as error:
        get_chat_session(other_user["id"], result["session"]["id"])
    assert error.value.status_code == 404

    own_sessions = list_chat_sessions(user["id"])
    other_sessions = list_chat_sessions(other_user["id"])
    assert own_sessions["total"] == 1
    assert other_sessions["total"] == 0


def test_agent_action_checkpoint_is_invisible_to_other_users(agent_course):
    user, other_user, course = agent_course
    session = create_chat_session(
        user["id"],
        ChatSessionCreate(course_id=course["id"], title="隔离检查点"),
    )
    checkpoint = {
        "thread_id": f"owner-only-{uuid4().hex}",
        "run_id": 987654321,
    }
    now = agent_service._utc_now()
    with get_cursor() as cursor:
        action = repository.create_action_request(
            cursor,
            user["id"],
            session["id"],
            course["id"],
            "delete_task",
            {"task_id": 123456789},
            uuid4().hex,
            now + timedelta(minutes=10),
            now,
            checkpoint=checkpoint,
        )

    with pytest.raises(AppError) as error:
        decide_action(other_user["id"], action["id"], confirmed=True)
    assert error.value.status_code == 404
    assert error.value.error_code == "ACTION_NOT_FOUND"

    with get_cursor() as cursor:
        stored = repository.get_action_request(cursor, action["id"], user["id"])
    assert stored["status"] == "pending"
    assert stored["checkpoint"] == checkpoint


def test_delete_task_requires_confirmation_and_cancel_keeps_data(agent_course):
    user, _, course = agent_course
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO tasks (user_id, course_id, title, description, status, priority)
            VALUES (%s, %s, '不能直接删除的任务', '', 'todo', 'medium')
            """,
            (user["id"], course["id"]),
        )
        task_id = cursor.lastrowid

    result = run_agent_chat(
        user["id"],
        AgentChatRequest(message=f"删除任务 {task_id}"),
        reply_provider=_reply_provider,
        search_provider=_search_provider,
    )
    action_id = result["confirmation"]["id"]

    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE id = %s", (task_id,))
        assert cursor.fetchone()["total"] == 1

    cancelled = decide_action(user["id"], action_id, confirmed=False)
    assert cancelled["status"] == "cancelled"
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE id = %s", (task_id,))
        assert cursor.fetchone()["total"] == 1


def test_confirmed_delete_executes_once_and_is_audited(agent_course):
    user, _, course = agent_course
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO tasks (user_id, course_id, title, description, status, priority)
            VALUES (%s, %s, '确认后删除的任务', '', 'todo', 'medium')
            """,
            (user["id"], course["id"]),
        )
        task_id = cursor.lastrowid

    chat = run_agent_chat(
        user["id"],
        AgentChatRequest(message=f"请删除任务 {task_id}"),
        reply_provider=_reply_provider,
        search_provider=_search_provider,
    )
    action_id = chat["confirmation"]["id"]
    executed = decide_action(user["id"], action_id, confirmed=True)
    repeated = decide_action(user["id"], action_id, confirmed=True)

    assert executed["result"] == {"task_id": task_id, "deleted": True}
    assert repeated["idempotent"] is True
    assert repeated["result"] == executed["result"]
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE id = %s", (task_id,))
        assert cursor.fetchone()["total"] == 0
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM operation_logs
            WHERE user_id = %s AND action = 'AGENT_ACTION_EXECUTED'
              AND target_type = 'task' AND target_id = %s
            """,
            (user["id"], task_id),
        )
        assert cursor.fetchone()["total"] == 1


def test_delete_request_without_task_id_never_creates_action(agent_course):
    user, _, _ = agent_course
    result = run_agent_chat(
        user["id"],
        AgentChatRequest(message="删除一个任务"),
        reply_provider=_reply_provider,
        search_provider=_search_provider,
    )

    assert result["risk_level"] == "destructive"
    assert result["confirmation"] is None
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM agent_action_requests WHERE user_id = %s",
            (user["id"],),
        )
        assert cursor.fetchone()["total"] == 0


def test_session_page_size_is_capped_by_api(api_client):
    response = api_client.get("/api/v1/agent/sessions?size=101")
    assert response.status_code == 422


def test_chat_session_lifecycle_is_persisted_and_archived(agent_course):
    user, _, course = agent_course
    session = create_chat_session(
        user["id"],
        ChatSessionCreate(course_id=course["id"], title="生命周期会话"),
    )

    detail = get_chat_session(user["id"], session["id"])
    assert detail["session"]["title"] == "生命周期会话"
    assert detail["messages"] == []
    assert list_chat_sessions(user["id"])["total"] == 1

    archive_chat_session(user["id"], session["id"])
    assert list_chat_sessions(user["id"])["total"] == 0
    with pytest.raises(AppError) as error:
        get_chat_session(user["id"], session["id"])
    assert error.value.error_code == "CHAT_SESSION_NOT_FOUND"


def test_agent_read_intents_return_today_and_progress_cards(agent_course):
    user, _, course = agent_course

    today = run_agent_chat(user["id"], AgentChatRequest(message="今天学什么？"))
    progress = run_agent_chat(
        user["id"],
        AgentChatRequest(message="总结我的学习进度和薄弱点"),
    )

    assert today["intent"] == "get_today"
    assert today["cards"] == [{"type": "today", "data": None}]
    assert today["actions"][0]["to"] == "/today"
    assert progress["intent"] == "get_progress"
    assert progress["cards"][0]["type"] == "progress"
    assert progress["cards"][0]["data"]["course"]["id"] == course["id"]


def test_agent_without_course_guides_user_to_course_selection(agent_course):
    _, other_user, _ = agent_course

    result = run_agent_chat(other_user["id"], AgentChatRequest(message="今天学什么？"))

    assert result["course"] is None
    assert result["cards"] == []
    assert result["actions"] == [{"type": "navigate", "label": "选择课程", "to": "/courses"}]


def test_generate_diagnostic_intent_reports_missing_knowledge_points(agent_course):
    user, _, _ = agent_course

    with pytest.raises(AppError) as error:
        run_agent_chat(user["id"], AgentChatRequest(message="生成诊断题"))
    assert error.value.error_code == "KNOWLEDGE_POINTS_NOT_READY"


def test_expired_agent_action_cannot_execute(agent_course):
    user, _, course = agent_course
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO tasks (user_id, course_id, title, description, status, priority)
            VALUES (%s, %s, '过期确认任务', '', 'todo', 'medium')
            """,
            (user["id"], course["id"]),
        )
        task_id = cursor.lastrowid
    chat = run_agent_chat(user["id"], AgentChatRequest(message=f"删除任务 {task_id}"))
    action_id = chat["confirmation"]["id"]
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE agent_action_requests
            SET expires_at = DATE_SUB(server_time_utc, INTERVAL 1 MINUTE)
            WHERE id = %s
            """,
            (action_id,),
        )

    with pytest.raises(AppError) as error:
        decide_action(user["id"], action_id, confirmed=True)
    assert error.value.error_code == "ACTION_EXPIRED"
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE id = %s", (task_id,))
        assert cursor.fetchone()["total"] == 1
