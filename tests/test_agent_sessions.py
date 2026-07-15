import pytest

from app.core.database import get_cursor
from app.core.errors import AppError
from app.modules.agent.schemas import AgentChatRequest, ChatSessionCreate
from app.modules.agent.service import (
    archive_chat_session,
    create_chat_session,
    decide_action,
    get_chat_session,
    list_chat_sessions,
    run_agent_chat,
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
