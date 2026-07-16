"""Agent persistence implemented with SQLAlchemy ORM entities."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.models import model_as_dict, reflected_model


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


def _row(entity: Any | None) -> dict | None:
    return model_as_dict(entity) if entity is not None else None


def _memory_row(entity: Any | None) -> dict | None:
    row = _row(entity)
    if row is not None:
        row["content"] = _json_loads(row.pop("content_json", None), {})
    return row


def _message_row(entity: Any | None) -> dict | None:
    row = _row(entity)
    if row is not None:
        row["tool_calls"] = _json_loads(row.get("tool_calls"), None)
        row["sources"] = _json_loads(row.pop("sources_json", None), [])
    return row


def _action_row(entity: Any | None) -> dict | None:
    row = _row(entity)
    if row is not None:
        row["payload"] = _json_loads(row.pop("payload_json"), {})
        row["result"] = _json_loads(row.pop("result_json"), None)
        row["checkpoint"] = _json_loads(row.pop("checkpoint_json"), None)
    return row


def get_course_agent(cursor, course_id: int, user_id: int) -> dict | None:
    CourseAgent = reflected_model("course_agents")
    agent = cursor.session.scalar(
        select(CourseAgent).where(CourseAgent.course_id == course_id, CourseAgent.user_id == user_id)
    )
    return _row(agent)


def ensure_course_agent(cursor, user_id: int, course: dict) -> dict:
    CourseAgent = reflected_model("course_agents")
    ChatSession = reflected_model("chat_sessions")
    session = cursor.session
    agent = session.scalar(
        select(CourseAgent)
        .where(CourseAgent.course_id == course["id"], CourseAgent.user_id == user_id)
        .with_for_update()
    )
    name = f"{course['name']} 学习助手"
    status = "archived" if course.get("status") == "archived" else "active"
    if agent is None:
        agent = CourseAgent(user_id=user_id, course_id=course["id"], name=name, status=status)
        session.add(agent)
    else:
        agent.name = name
        agent.status = status
    session.flush()

    primary = None
    if agent.primary_session_id:
        primary_model = session.scalar(
            select(ChatSession).where(
                ChatSession.id == agent.primary_session_id,
                ChatSession.user_id == user_id,
            )
        )
        if primary_model is not None and primary_model.archived_at is None:
            primary = _row(primary_model)
    if primary is None:
        primary_model = session.scalar(
            select(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.course_id == course["id"],
                ChatSession.archived_at.is_(None),
            )
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(1)
        )
        if primary_model is None:
            primary = create_session(cursor, user_id, course["id"], f"{course['name']} 学习对话")
        else:
            primary = _row(primary_model)
        if primary is None:
            raise RuntimeError("primary session could not be created or loaded")
        agent.primary_session_id = primary["id"]
        agent.last_active_at = datetime.now()
        session.flush()
    agent_row = _row(agent)
    if agent_row is None:
        raise RuntimeError("course agent could not be reloaded")
    agent_row["primary_session"] = primary
    return agent_row


def update_conversation_summary(
    cursor,
    agent_id: int,
    user_id: int,
    summary: str,
    last_summarized_message_id: int,
) -> None:
    CourseAgent = reflected_model("course_agents")
    agent = cursor.session.scalar(
        select(CourseAgent).where(CourseAgent.id == agent_id, CourseAgent.user_id == user_id)
    )
    if agent is not None:
        agent.conversation_summary = summary[:3500]
        agent.last_summarized_message_id = max(agent.last_summarized_message_id or 0, last_summarized_message_id)


def touch_course_agent(cursor, agent_id: int, user_id: int) -> None:
    CourseAgent = reflected_model("course_agents")
    agent = cursor.session.scalar(
        select(CourseAgent).where(CourseAgent.id == agent_id, CourseAgent.user_id == user_id)
    )
    if agent is not None:
        agent.last_active_at = datetime.now()


def list_course_memories(cursor, agent_id: int, user_id: int) -> list[dict]:
    CourseMemory = reflected_model("course_agent_memories")
    memories = cursor.session.scalars(
        select(CourseMemory)
        .where(
            CourseMemory.agent_id == agent_id,
            CourseMemory.user_id == user_id,
            CourseMemory.status == "active",
        )
        .order_by(CourseMemory.updated_at.desc(), CourseMemory.id.desc())
    )
    return [row for memory in memories if (row := _memory_row(memory)) is not None]


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
    CourseMemory = reflected_model("course_agent_memories")
    session = cursor.session
    memory = session.scalar(
        select(CourseMemory)
        .where(
            CourseMemory.agent_id == agent_id,
            CourseMemory.memory_key == memory_key,
            CourseMemory.user_id == user_id,
        )
        .with_for_update()
    )
    values = {
        "memory_type": memory_type,
        "content_json": _json_dumps(content),
        "source_message_id": source_message_id,
        "embedding_json": embedding_json,
        "embedding_model": embedding_model,
        "embedding_hash": embedding_hash,
        "status": "active",
    }
    if memory is None:
        memory = CourseMemory(
            agent_id=agent_id,
            user_id=user_id,
            course_id=course_id,
            memory_key=memory_key,
            **values,
        )
        session.add(memory)
    else:
        for field, value in values.items():
            setattr(memory, field, value)
    session.flush()
    return _memory_row(memory) or {}


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
    AgentRun = reflected_model("agent_runs")
    run = AgentRun(
        request_id=request_id,
        agent_id=agent_id,
        user_id=user_id,
        course_id=course_id,
        session_id=session_id,
        user_message_id=user_message_id,
        intent=intent,
        risk_level=risk_level,
        status="running",
        input_summary=input_summary[:500],
        started_at=started_at,
    )
    cursor.session.add(run)
    cursor.session.flush()
    return {"id": run.id, "request_id": request_id, "status": "running"}


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
    AgentRun = reflected_model("agent_runs")
    run = cursor.session.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id))
    if run is not None:
        run.status = status
        run.assistant_message_id = assistant_message_id
        run.output_summary = output_summary[:500] if output_summary else None
        run.error_message = error_message[:2000] if error_message else None
        run.completed_at = completed_at


def pause_agent_run(
    cursor,
    run_id: int,
    user_id: int,
    *,
    assistant_message_id: int,
    output_summary: str,
) -> None:
    AgentRun = reflected_model("agent_runs")
    run = cursor.session.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id))
    if run is not None:
        run.status = "waiting_confirmation"
        run.assistant_message_id = assistant_message_id
        run.output_summary = output_summary[:500]
        run.completed_at = None


def get_agent_run(cursor, run_id: int, user_id: int) -> dict | None:
    AgentRun = reflected_model("agent_runs")
    run = cursor.session.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id))
    return _row(run)


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
    ToolCall = reflected_model("agent_tool_calls")
    tool_call = ToolCall(
        run_id=run_id,
        user_id=user_id,
        course_id=course_id,
        tool_name=tool_name,
        risk_level=risk_level,
        arguments_json=_json_dumps(arguments),
        status="running",
        idempotency_key=idempotency_key,
        started_at=started_at,
    )
    cursor.session.add(tool_call)
    cursor.session.flush()
    return tool_call.id


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
    ToolCall = reflected_model("agent_tool_calls")
    tool_call = cursor.session.scalar(
        select(ToolCall).where(ToolCall.id == tool_call_id, ToolCall.user_id == user_id)
    )
    if tool_call is not None:
        tool_call.status = status
        tool_call.result_json = _json_dumps(result) if result is not None else None
        tool_call.error_message = error_message[:2000] if error_message else None
        tool_call.completed_at = completed_at


def create_session(cursor, user_id: int, course_id: int | None, title: str) -> dict:
    ChatSession = reflected_model("chat_sessions")
    session_model = ChatSession(user_id=user_id, course_id=course_id, title=title)
    cursor.session.add(session_model)
    cursor.session.flush()
    return _row(session_model) or {}


def get_session(cursor, session_id: int, user_id: int) -> dict | None:
    ChatSession = reflected_model("chat_sessions")
    session_model = cursor.session.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    return _row(session_model)


def list_sessions(cursor, user_id: int, page: int, size: int) -> dict:
    ChatSession = reflected_model("chat_sessions")
    Course = reflected_model("courses")
    Message = reflected_model("agent_chat_messages")
    session = cursor.session
    total = session.scalar(
        select(func.count()).select_from(ChatSession).where(
            ChatSession.user_id == user_id,
            ChatSession.archived_at.is_(None),
        )
    ) or 0
    session_models = session.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == user_id, ChatSession.archived_at.is_(None))
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).all()
    course_ids = {item.course_id for item in session_models if item.course_id is not None}
    course_names = {
        course.id: course.name
        for course in session.scalars(select(Course).where(Course.id.in_(course_ids)))
    } if course_ids else {}
    session_ids = [item.id for item in session_models]
    latest_ids = session.scalars(
        select(func.max(Message.id)).where(Message.session_id.in_(session_ids)).group_by(Message.session_id)
    ).all() if session_ids else []
    latest_messages = {
        message.session_id: message.content
        for message in session.scalars(select(Message).where(Message.id.in_(latest_ids)))
    } if latest_ids else {}
    items = []
    for session_model in session_models:
        row = _row(session_model) or {}
        row["course_name"] = course_names.get(session_model.course_id)
        row["last_message"] = latest_messages.get(session_model.id)
        items.append(row)
    return {"items": items, "total": total, "page": page, "size": size}


def update_session_course(cursor, session_id: int, user_id: int, course_id: int | None) -> None:
    ChatSession = reflected_model("chat_sessions")
    session_model = cursor.session.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if session_model is not None:
        session_model.course_id = course_id


def update_session_title_if_default(cursor, session_id: int, user_id: int, title: str) -> None:
    ChatSession = reflected_model("chat_sessions")
    session_model = cursor.session.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if session_model is not None and session_model.title == "新对话":
        session_model.title = title[:255]


def update_session_title(cursor, session_id: int, user_id: int, title: str) -> None:
    ChatSession = reflected_model("chat_sessions")
    session_model = cursor.session.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if session_model is not None:
        session_model.title = title[:255]


def touch_session(cursor, session_id: int, user_id: int) -> None:
    ChatSession = reflected_model("chat_sessions")
    session_model = cursor.session.scalar(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if session_model is not None:
        session_model.updated_at = datetime.now()


def archive_session(cursor, session_id: int, user_id: int) -> bool:
    ChatSession = reflected_model("chat_sessions")
    session_model = cursor.session.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.archived_at.is_(None),
        )
    )
    if session_model is None:
        return False
    session_model.archived_at = datetime.now()
    cursor.session.flush()
    return True


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
    Message = reflected_model("agent_chat_messages")
    message = Message(
        user_id=user_id,
        session_id=session_id,
        course_id=course_id,
        role=role,
        content=content,
        tool_calls=_json_dumps(tool_calls) if tool_calls is not None else None,
        sources_json=_json_dumps(sources) if sources is not None else None,
        client_time_hint=client_time_hint,
    )
    cursor.session.add(message)
    cursor.session.flush()
    touch_session(cursor, session_id, user_id)
    return _message_row(message) or {}


def get_message(cursor, message_id: int, user_id: int) -> dict | None:
    Message = reflected_model("agent_chat_messages")
    message = cursor.session.scalar(select(Message).where(Message.id == message_id, Message.user_id == user_id))
    return _message_row(message)


def list_messages(
    cursor,
    user_id: int,
    session_id: int,
    before_id: int | None,
    size: int,
) -> list[dict]:
    Message = reflected_model("agent_chat_messages")
    statement = select(Message).where(Message.user_id == user_id, Message.session_id == session_id)
    if before_id is not None:
        statement = statement.where(Message.id < before_id)
    messages = cursor.session.scalars(statement.order_by(Message.id.desc()).limit(size)).all()
    messages.reverse()
    return [row for message in messages if (row := _message_row(message)) is not None]


def list_messages_after(
    cursor,
    user_id: int,
    session_id: int,
    after_id: int | None,
    limit: int = 200,
) -> list[dict]:
    Message = reflected_model("agent_chat_messages")
    messages = cursor.session.scalars(
        select(Message)
        .where(
            Message.user_id == user_id,
            Message.session_id == session_id,
            Message.id > int(after_id or 0),
        )
        .order_by(Message.id)
        .limit(max(1, min(int(limit), 500)))
    )
    return [row for message in messages if (row := _message_row(message)) is not None]


def get_action_statuses(cursor, user_id: int, action_ids: list[int]) -> dict[int, str]:
    if not action_ids:
        return {}
    ActionRequest = reflected_model("agent_action_requests")
    actions = cursor.session.scalars(
        select(ActionRequest).where(ActionRequest.user_id == user_id, ActionRequest.id.in_(action_ids))
    )
    return {action.id: action.status for action in actions}


def load_profile(cursor, user_id: int) -> dict | None:
    StudentProfile = reflected_model("student_profiles")
    profile = cursor.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))
    return _json_loads(profile.profile_json, None) if profile is not None else None


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
    ActionRequest = reflected_model("agent_action_requests")
    action = ActionRequest(
        user_id=user_id,
        session_id=session_id,
        course_id=course_id,
        tool_name=tool_name,
        risk_level="destructive",
        payload_json=_json_dumps(payload),
        idempotency_key=idempotency_key,
        expires_at=expires_at,
        server_time_utc=server_time_utc,
        checkpoint_json=_json_dumps(checkpoint) if checkpoint is not None else None,
    )
    cursor.session.add(action)
    cursor.session.flush()
    return _action_row(action) or {}


def get_action_request(
    cursor,
    action_id: int,
    user_id: int,
    for_update: bool = False,
) -> dict | None:
    ActionRequest = reflected_model("agent_action_requests")
    statement = select(ActionRequest).where(ActionRequest.id == action_id, ActionRequest.user_id == user_id)
    if for_update:
        statement = statement.with_for_update()
    return _action_row(cursor.session.scalar(statement))


def set_action_status(
    cursor,
    action_id: int,
    status: str,
    result: dict | None = None,
) -> None:
    ActionRequest = reflected_model("agent_action_requests")
    action = cursor.session.get(ActionRequest, action_id)
    if action is not None:
        action.status = status
        action.result_json = _json_dumps(result) if result is not None else None
        if status == "executed":
            now = datetime.now()
            action.confirmed_at = now
            action.executed_at = now


def claim_action_resume(cursor, action_id: int) -> None:
    ActionRequest = reflected_model("agent_action_requests")
    action = cursor.session.get(ActionRequest, action_id)
    if action is not None and action.status == "pending":
        action.status = "resuming"
        action.confirmed_at = datetime.now()


def reset_action_pending(cursor, action_id: int) -> None:
    ActionRequest = reflected_model("agent_action_requests")
    action = cursor.session.get(ActionRequest, action_id)
    if action is not None and action.status == "resuming":
        action.status = "pending"
        action.confirmed_at = None


def get_task(cursor, task_id: int, user_id: int) -> dict | None:
    Task = reflected_model("tasks")
    task = cursor.session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    return _row(task)


def delete_task(cursor, task_id: int, user_id: int) -> bool:
    Task = reflected_model("tasks")
    task = cursor.session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    if task is None:
        return False
    cursor.session.delete(task)
    cursor.session.flush()
    return True


def add_audit_log(
    cursor,
    user_id: int,
    action: str,
    target_type: str,
    target_id: int | None,
    detail: dict,
) -> None:
    OperationLog = reflected_model("operation_logs")
    cursor.session.add(
        OperationLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=_json_dumps(detail),
        )
    )


def get_latest_diagnostic_id(cursor, user_id: int, course_id: int) -> int | None:
    QuizSet = reflected_model("quiz_sets")
    return cursor.session.scalar(
        select(QuizSet.id)
        .where(
            QuizSet.user_id == user_id,
            QuizSet.course_id == course_id,
            QuizSet.purpose == "diagnostic",
        )
        .order_by(QuizSet.id.desc())
        .limit(1)
    )
