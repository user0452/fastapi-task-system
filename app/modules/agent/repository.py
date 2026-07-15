import json
from datetime import datetime
from typing import Any

SESSION_COLUMNS = """
    id, user_id, course_id, title, archived_at, created_at, updated_at
"""

COURSE_AGENT_COLUMNS = """
    id, user_id, course_id, name, status, system_prompt,
    conversation_summary, primary_session_id, last_summarized_message_id, last_active_at,
    created_at, updated_at
"""


def _json_loads(value: Any, default=None):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def get_course_agent(cursor, course_id: int, user_id: int) -> dict | None:
    cursor.execute(
        f"""
        SELECT {COURSE_AGENT_COLUMNS}
        FROM course_agents
        WHERE course_id = %s AND user_id = %s
        """,
        (course_id, user_id),
    )
    return cursor.fetchone()


def ensure_course_agent(cursor, user_id: int, course: dict) -> dict:
    cursor.execute(
        """
        INSERT INTO course_agents (user_id, course_id, name, status)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            status = VALUES(status),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            course["id"],
            f"{course['name']} 学习助手",
            "archived" if course.get("status") == "archived" else "active",
        ),
    )
    agent = get_course_agent(cursor, course["id"], user_id)
    if agent is None:
        raise RuntimeError("course agent upsert succeeded but the row could not be reloaded")
    primary = None
    if agent.get("primary_session_id"):
        primary = get_session(cursor, agent["primary_session_id"], user_id)
        if primary and primary.get("archived_at") is not None:
            primary = None
    if primary is None:
        cursor.execute(
            """
            SELECT id FROM chat_sessions
            WHERE user_id = %s AND course_id = %s AND archived_at IS NULL
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (user_id, course["id"]),
        )
        selected = cursor.fetchone()
        primary = (
            get_session(cursor, selected["id"], user_id)
            if selected
            else create_session(cursor, user_id, course["id"], f"{course['name']} 学习对话")
        )
        if primary is None:
            raise RuntimeError("primary session could not be created or loaded")
        cursor.execute(
            """
            UPDATE course_agents
            SET primary_session_id = %s, last_active_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s
            """,
            (primary["id"], agent["id"], user_id),
        )
        agent = get_course_agent(cursor, course["id"], user_id)
        if agent is None:
            raise RuntimeError("course agent disappeared while assigning its primary session")
    agent["primary_session"] = primary
    return agent


def update_conversation_summary(
    cursor,
    agent_id: int,
    user_id: int,
    summary: str,
    last_summarized_message_id: int,
) -> None:
    cursor.execute(
        """
        UPDATE course_agents
        SET conversation_summary = %s,
            last_summarized_message_id = GREATEST(
                COALESCE(last_summarized_message_id, 0), %s
            ),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s
        """,
        (summary[:3500], last_summarized_message_id, agent_id, user_id),
    )


def touch_course_agent(cursor, agent_id: int, user_id: int) -> None:
    cursor.execute(
        """
        UPDATE course_agents
        SET last_active_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s
        """,
        (agent_id, user_id),
    )


def list_course_memories(cursor, agent_id: int, user_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT id, agent_id, course_id, memory_key, memory_type,
               content_json, source_message_id, status, embedding_json,
               embedding_model, embedding_hash, created_at, updated_at
        FROM course_agent_memories
        WHERE agent_id = %s AND user_id = %s AND status = 'active'
        ORDER BY updated_at DESC, id DESC
        """,
        (agent_id, user_id),
    )
    rows = list(cursor.fetchall())
    for row in rows:
        row["content"] = _json_loads(row.pop("content_json", None), {})
    return rows


def upsert_course_memory(
    cursor,
    agent_id: int,
    user_id: int,
    course_id: int,
    memory_key: str,
    memory_type: str,
    content: dict,
    source_message_id: int | None = None,
    embedding_json: str | None = None,
    embedding_model: str | None = None,
    embedding_hash: str | None = None,
) -> dict:
    cursor.execute(
        """
        INSERT INTO course_agent_memories
            (agent_id, user_id, course_id, memory_key, memory_type,
             content_json, source_message_id, embedding_json, embedding_model,
             embedding_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            memory_type = VALUES(memory_type),
            content_json = VALUES(content_json),
            source_message_id = VALUES(source_message_id),
            embedding_json = VALUES(embedding_json),
            embedding_model = VALUES(embedding_model),
            embedding_hash = VALUES(embedding_hash),
            status = 'active',
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            agent_id,
            user_id,
            course_id,
            memory_key,
            memory_type,
            _json_dumps(content),
            source_message_id,
            embedding_json,
            embedding_model,
            embedding_hash,
        ),
    )
    cursor.execute(
        """
        SELECT id, agent_id, course_id, memory_key, memory_type,
               content_json, source_message_id, status, embedding_json,
               embedding_model, embedding_hash, created_at, updated_at
        FROM course_agent_memories
        WHERE agent_id = %s AND memory_key = %s AND user_id = %s
        """,
        (agent_id, memory_key, user_id),
    )
    row = cursor.fetchone()
    row["content"] = _json_loads(row.pop("content_json", None), {})
    return row


def create_agent_run(
    cursor,
    *,
    request_id: str,
    agent_id: int,
    user_id: int,
    course_id: int,
    session_id: int,
    user_message_id: int,
    intent: str,
    risk_level: str,
    input_summary: str,
    started_at: datetime,
) -> dict:
    cursor.execute(
        """
        INSERT INTO agent_runs
            (request_id, agent_id, user_id, course_id, session_id,
             user_message_id, intent, risk_level, status, input_summary, started_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'running', %s, %s)
        """,
        (
            request_id,
            agent_id,
            user_id,
            course_id,
            session_id,
            user_message_id,
            intent,
            risk_level,
            input_summary[:500],
            started_at,
        ),
    )
    return {"id": cursor.lastrowid, "request_id": request_id, "status": "running"}


def finish_agent_run(
    cursor,
    run_id: int,
    user_id: int,
    *,
    status: str,
    assistant_message_id: int | None = None,
    output_summary: str | None = None,
    error_message: str | None = None,
    completed_at: datetime,
) -> None:
    cursor.execute(
        """
        UPDATE agent_runs
        SET status = %s,
            assistant_message_id = %s,
            output_summary = %s,
            error_message = %s,
            completed_at = %s
        WHERE id = %s AND user_id = %s
        """,
        (
            status,
            assistant_message_id,
            output_summary[:500] if output_summary else None,
            error_message[:2000] if error_message else None,
            completed_at,
            run_id,
            user_id,
        ),
    )


def pause_agent_run(
    cursor,
    run_id: int,
    user_id: int,
    *,
    assistant_message_id: int,
    output_summary: str,
) -> None:
    cursor.execute(
        """
        UPDATE agent_runs
        SET status = 'waiting_confirmation',
            assistant_message_id = %s,
            output_summary = %s,
            completed_at = NULL
        WHERE id = %s AND user_id = %s
        """,
        (assistant_message_id, output_summary[:500], run_id, user_id),
    )


def get_agent_run(cursor, run_id: int, user_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, request_id, agent_id, user_id, course_id, session_id,
               user_message_id, assistant_message_id, intent, risk_level,
               status, input_summary, output_summary, error_message,
               started_at, completed_at, created_at
        FROM agent_runs
        WHERE id = %s AND user_id = %s
        """,
        (run_id, user_id),
    )
    return cursor.fetchone()


def create_tool_call(
    cursor,
    *,
    run_id: int,
    user_id: int,
    course_id: int,
    tool_name: str,
    risk_level: str,
    arguments: dict,
    idempotency_key: str,
    started_at: datetime,
) -> int:
    cursor.execute(
        """
        INSERT INTO agent_tool_calls
            (run_id, user_id, course_id, tool_name, risk_level,
             arguments_json, status, idempotency_key, started_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'running', %s, %s)
        """,
        (
            run_id,
            user_id,
            course_id,
            tool_name,
            risk_level,
            _json_dumps(arguments),
            idempotency_key,
            started_at,
        ),
    )
    return cursor.lastrowid


def finish_tool_call(
    cursor,
    tool_call_id: int,
    user_id: int,
    *,
    status: str,
    result: dict | list | None = None,
    error_message: str | None = None,
    completed_at: datetime,
) -> None:
    cursor.execute(
        """
        UPDATE agent_tool_calls
        SET status = %s, result_json = %s, error_message = %s, completed_at = %s
        WHERE id = %s AND user_id = %s
        """,
        (
            status,
            _json_dumps(result) if result is not None else None,
            error_message[:2000] if error_message else None,
            completed_at,
            tool_call_id,
            user_id,
        ),
    )


def create_session(cursor, user_id: int, course_id: int | None, title: str) -> dict:
    cursor.execute(
        """
        INSERT INTO chat_sessions (user_id, course_id, title)
        VALUES (%s, %s, %s)
        """,
        (user_id, course_id, title),
    )
    session = get_session(cursor, cursor.lastrowid, user_id)
    if session is None:
        raise RuntimeError("session insert succeeded but the row could not be reloaded")
    return session


def get_session(cursor, session_id: int, user_id: int) -> dict | None:
    cursor.execute(
        f"SELECT {SESSION_COLUMNS} FROM chat_sessions WHERE id = %s AND user_id = %s",
        (session_id, user_id),
    )
    return cursor.fetchone()


def list_sessions(cursor, user_id: int, page: int, size: int) -> dict:
    offset = (page - 1) * size
    cursor.execute(
        "SELECT COUNT(*) AS total FROM chat_sessions WHERE user_id = %s AND archived_at IS NULL",
        (user_id,),
    )
    total = cursor.fetchone()["total"]
    cursor.execute(
        """
        SELECT session.id, session.user_id, session.course_id, session.title,
               session.archived_at, session.created_at, session.updated_at,
               course.name AS course_name,
               latest.content AS last_message
        FROM chat_sessions session
        LEFT JOIN courses course ON course.id = session.course_id
        LEFT JOIN agent_chat_messages latest ON latest.id = (
            SELECT MAX(message.id)
            FROM agent_chat_messages message
            WHERE message.session_id = session.id
        )
        WHERE session.user_id = %s AND session.archived_at IS NULL
        ORDER BY session.updated_at DESC, session.id DESC
        LIMIT %s OFFSET %s
        """,
        (user_id, size, offset),
    )
    return {"items": list(cursor.fetchall()), "total": total, "page": page, "size": size}


def update_session_course(cursor, session_id: int, user_id: int, course_id: int | None) -> None:
    cursor.execute(
        "UPDATE chat_sessions SET course_id = %s WHERE id = %s AND user_id = %s",
        (course_id, session_id, user_id),
    )


def update_session_title_if_default(cursor, session_id: int, user_id: int, title: str) -> None:
    cursor.execute(
        """
        UPDATE chat_sessions
        SET title = %s
        WHERE id = %s AND user_id = %s AND title = '新对话'
        """,
        (title[:255], session_id, user_id),
    )


def update_session_title(cursor, session_id: int, user_id: int, title: str) -> None:
    cursor.execute(
        "UPDATE chat_sessions SET title = %s WHERE id = %s AND user_id = %s",
        (title[:255], session_id, user_id),
    )


def touch_session(cursor, session_id: int, user_id: int) -> None:
    cursor.execute(
        "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s",
        (session_id, user_id),
    )


def archive_session(cursor, session_id: int, user_id: int) -> bool:
    cursor.execute(
        """
        UPDATE chat_sessions SET archived_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s AND archived_at IS NULL
        """,
        (session_id, user_id),
    )
    return cursor.rowcount > 0


def add_message(
    cursor,
    user_id: int,
    session_id: int,
    course_id: int | None,
    role: str,
    content: str,
    tool_calls: dict | None = None,
    sources: list[dict] | None = None,
    client_time_hint: str | None = None,
) -> dict:
    cursor.execute(
        """
        INSERT INTO agent_chat_messages
            (user_id, session_id, course_id, role, content, tool_calls,
             sources_json, client_time_hint)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            session_id,
            course_id,
            role,
            content,
            _json_dumps(tool_calls) if tool_calls is not None else None,
            _json_dumps(sources) if sources is not None else None,
            client_time_hint,
        ),
    )
    message_id = cursor.lastrowid
    touch_session(cursor, session_id, user_id)
    message = get_message(cursor, message_id, user_id)
    if message is None:
        raise RuntimeError("message insert succeeded but the row could not be reloaded")
    return message


def get_message(cursor, message_id: int, user_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, user_id, session_id, course_id, role, content,
               tool_calls, sources_json, client_time_hint, created_at
        FROM agent_chat_messages
        WHERE id = %s AND user_id = %s
        """,
        (message_id, user_id),
    )
    row = cursor.fetchone()
    if row:
        row["tool_calls"] = _json_loads(row.get("tool_calls"), None)
        row["sources"] = _json_loads(row.pop("sources_json", None), [])
    return row


def list_messages(
    cursor,
    user_id: int,
    session_id: int,
    before_id: int | None,
    size: int,
) -> list[dict]:
    params: list[Any] = [user_id, session_id]
    before_clause = ""
    if before_id is not None:
        before_clause = "AND id < %s"
        params.append(before_id)
    params.append(size)
    cursor.execute(
        f"""
        SELECT id, user_id, session_id, course_id, role, content,
               tool_calls, sources_json, client_time_hint, created_at
        FROM agent_chat_messages
        WHERE user_id = %s AND session_id = %s {before_clause}
        ORDER BY id DESC
        LIMIT %s
        """,
        params,
    )
    rows = list(cursor.fetchall())
    rows.reverse()
    for row in rows:
        row["tool_calls"] = _json_loads(row.get("tool_calls"), None)
        row["sources"] = _json_loads(row.pop("sources_json", None), [])
    return rows


def list_messages_after(
    cursor,
    user_id: int,
    session_id: int,
    after_id: int | None,
    limit: int = 200,
) -> list[dict]:
    cursor.execute(
        """
        SELECT id, user_id, session_id, course_id, role, content,
               tool_calls, sources_json, client_time_hint, created_at
        FROM agent_chat_messages
        WHERE user_id = %s AND session_id = %s AND id > %s
        ORDER BY id
        LIMIT %s
        """,
        (user_id, session_id, int(after_id or 0), max(1, min(int(limit), 500))),
    )
    rows = list(cursor.fetchall())
    for row in rows:
        row["tool_calls"] = _json_loads(row.get("tool_calls"), None)
        row["sources"] = _json_loads(row.pop("sources_json", None), [])
    return rows


def get_action_statuses(cursor, user_id: int, action_ids: list[int]) -> dict[int, str]:
    if not action_ids:
        return {}
    placeholders = ",".join(["%s"] * len(action_ids))
    cursor.execute(
        f"""
        SELECT id, status FROM agent_action_requests
        WHERE user_id = %s AND id IN ({placeholders})
        """,
        (user_id, *action_ids),
    )
    return {row["id"]: row["status"] for row in cursor.fetchall()}


def load_profile(cursor, user_id: int) -> dict | None:
    cursor.execute("SELECT profile_json FROM student_profiles WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    return _json_loads(row["profile_json"], None) if row else None


def create_action_request(
    cursor,
    user_id: int,
    session_id: int,
    course_id: int | None,
    tool_name: str,
    payload: dict,
    idempotency_key: str,
    expires_at: datetime,
    server_time_utc: datetime,
    checkpoint: dict | None = None,
) -> dict:
    cursor.execute(
        """
        INSERT INTO agent_action_requests
            (user_id, session_id, course_id, tool_name, risk_level,
             payload_json, idempotency_key, expires_at, server_time_utc,
             checkpoint_json)
        VALUES (%s, %s, %s, %s, 'destructive', %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            session_id,
            course_id,
            tool_name,
            _json_dumps(payload),
            idempotency_key,
            expires_at,
            server_time_utc,
            _json_dumps(checkpoint) if checkpoint is not None else None,
        ),
    )
    action = get_action_request(cursor, cursor.lastrowid, user_id)
    if action is None:
        raise RuntimeError("action insert succeeded but the row could not be reloaded")
    return action


def get_action_request(
    cursor,
    action_id: int,
    user_id: int,
    for_update: bool = False,
) -> dict | None:
    lock = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT id, user_id, session_id, course_id, tool_name, risk_level,
               payload_json, idempotency_key, status, result_json,
               checkpoint_json, expires_at, confirmed_at, executed_at,
               server_time_utc, created_at, updated_at
        FROM agent_action_requests
        WHERE id = %s AND user_id = %s{lock}
        """,
        (action_id, user_id),
    )
    row = cursor.fetchone()
    if row:
        row["payload"] = _json_loads(row.pop("payload_json"), {})
        row["result"] = _json_loads(row.pop("result_json"), None)
        row["checkpoint"] = _json_loads(row.pop("checkpoint_json"), None)
    return row


def set_action_status(
    cursor,
    action_id: int,
    status: str,
    result: dict | None = None,
) -> None:
    cursor.execute(
        """
        UPDATE agent_action_requests
        SET status = %s,
            result_json = %s,
            confirmed_at = CASE WHEN %s = 'executed' THEN CURRENT_TIMESTAMP ELSE confirmed_at END,
            executed_at = CASE WHEN %s = 'executed' THEN CURRENT_TIMESTAMP ELSE executed_at END
        WHERE id = %s
        """,
        (
            status,
            _json_dumps(result) if result is not None else None,
            status,
            status,
            action_id,
        ),
    )


def claim_action_resume(cursor, action_id: int) -> None:
    cursor.execute(
        """
        UPDATE agent_action_requests
        SET status = 'resuming', confirmed_at = CURRENT_TIMESTAMP
        WHERE id = %s AND status = 'pending'
        """,
        (action_id,),
    )


def reset_action_pending(cursor, action_id: int) -> None:
    cursor.execute(
        """
        UPDATE agent_action_requests
        SET status = 'pending', confirmed_at = NULL
        WHERE id = %s AND status = 'resuming'
        """,
        (action_id,),
    )


def get_task(cursor, task_id: int, user_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, user_id, course_id, title, description, status, priority,
               created_at, updated_at
        FROM tasks WHERE id = %s AND user_id = %s
        """,
        (task_id, user_id),
    )
    return cursor.fetchone()


def delete_task(cursor, task_id: int, user_id: int) -> bool:
    cursor.execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, user_id))
    return cursor.rowcount > 0


def add_audit_log(
    cursor,
    user_id: int,
    action: str,
    target_type: str,
    target_id: int | None,
    detail: dict,
) -> None:
    cursor.execute(
        """
        INSERT INTO operation_logs (user_id, action, target_type, target_id, detail)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, action, target_type, target_id, _json_dumps(detail)),
    )


def get_latest_diagnostic_id(cursor, user_id: int, course_id: int) -> int | None:
    cursor.execute(
        """
        SELECT id FROM quiz_sets
        WHERE user_id = %s AND course_id = %s AND purpose = 'diagnostic'
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, course_id),
    )
    row = cursor.fetchone()
    return row["id"] if row else None
