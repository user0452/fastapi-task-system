"""Chat session and course Agent workspace lifecycle operations."""

from app.core.database import get_cursor
from app.core.errors import AppError
from app.modules.agent import repository
from app.modules.agent.memory_service import public_memory
from app.modules.agent.schemas import ChatSessionCreate
from app.modules.audit.service import record_audit
from app.modules.courses import repository as course_repository


def _page(page: int, size: int) -> tuple[int, int]:
    return max(1, page), max(1, min(size, 100))


def list_chat_sessions(
    user_id: int,
    page: int = 1,
    size: int = 20,
    course_id: int | None = None,
) -> dict:
    page, size = _page(page, size)
    with get_cursor() as cursor:
        if course_id is not None:
            course = course_repository.get_course(cursor, course_id, user_id)
            if course is None or course.get("status") == "archived":
                raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        result = repository.list_sessions(cursor, user_id, page, size, course_id)
        record_audit(
            user_id,
            "COURSE_AGENT_SESSIONS_VIEWED",
            "chat_session",
            detail={"count": len(result["items"]), "course_id": course_id},
            cursor=cursor,
        )
        return result


def create_chat_session(user_id: int, request: ChatSessionCreate) -> dict:
    with get_cursor() as cursor:
        course_id = request.course_id
        course = None
        if course_id is not None:
            course = course_repository.get_course(cursor, course_id, user_id)
            if course is None or course.get("status") == "archived":
                raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        if course_id is None:
            course = course_repository.get_current_course(cursor, user_id)
            course_id = course["id"] if course else None
        if course is not None:
            session = repository.create_session(cursor, user_id, course_id, request.title)
            repository.ensure_course_agent(cursor, user_id, course)
            record_audit(
                user_id,
                "COURSE_AGENT_SESSION_CREATED",
                "chat_session",
                session["id"],
                {"course_id": course_id, "session_id": session["id"]},
                cursor=cursor,
            )
            return session
        session = repository.create_session(cursor, user_id, None, request.title)
        record_audit(
            user_id,
            "GENERAL_AGENT_SESSION_CREATED",
            "chat_session",
            session["id"],
            cursor=cursor,
        )
        return session


def get_course_agent_workspace(
    user_id: int,
    course_id: int,
    message_limit: int = 100,
    session_id: int | None = None,
) -> dict:
    _, message_limit = _page(1, message_limit)
    with get_cursor() as cursor:
        course = course_repository.get_course(cursor, course_id, user_id)
        if course is None or course.get("status") == "archived":
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        agent = repository.ensure_course_agent(cursor, user_id, course)
        primary_session = agent.pop("primary_session")
        session = primary_session
        if session_id is not None:
            selected_session = repository.get_session(cursor, session_id, user_id)
            if selected_session is None or selected_session.get("archived_at") is not None:
                raise AppError("会话不存在或无访问权限", 404, "CHAT_SESSION_NOT_FOUND")
            if selected_session.get("course_id") != course_id:
                raise AppError(
                    "该会话属于另一门课程，不能跨课程复用上下文",
                    409,
                    "SESSION_COURSE_MISMATCH",
                )
            session = selected_session
        messages = repository.list_messages(cursor, user_id, session["id"], None, message_limit)
        memories = repository.list_course_memories(cursor, agent["id"], user_id)
        confirmation_ids = [
            confirmation["id"]
            for message in messages
            if isinstance(
                (confirmation := (message.get("tool_calls") or {}).get("confirmation")),
                dict,
            )
            and confirmation.get("id")
        ]
        statuses = repository.get_action_statuses(cursor, user_id, confirmation_ids)
        for message in messages:
            confirmation = (message.get("tool_calls") or {}).get("confirmation")
            if isinstance(confirmation, dict) and confirmation.get("id") in statuses:
                confirmation["status"] = statuses[confirmation["id"]]
        record_audit(
            user_id,
            "COURSE_AGENT_WORKSPACE_VIEWED",
            "course_agent",
            agent["id"],
            {
                "course_id": course_id,
                "session_id": session["id"],
                "message_count": len(messages),
            },
            cursor=cursor,
        )
    return {
        "course": course,
        "agent": agent,
        "session": session,
        "messages": messages,
        "memories": [public_memory(memory) for memory in memories],
        "capabilities": [
            "course_qa",
            "external_video_search",
            "today_learning",
            "progress",
            "study_plan",
            "practice",
            "wrong_answers",
            "diagnostic",
        ],
    }


def get_chat_session(
    user_id: int,
    session_id: int,
    before_id: int | None = None,
    size: int = 100,
) -> dict:
    _, size = _page(1, size)
    with get_cursor() as cursor:
        session = repository.get_session(cursor, session_id, user_id)
        if session is None or session.get("archived_at") is not None:
            raise AppError("会话不存在或无访问权限", 404, "CHAT_SESSION_NOT_FOUND")
        messages = repository.list_messages(cursor, user_id, session_id, before_id, size)
        confirmation_ids = []
        for message in messages:
            tool_calls = message.get("tool_calls") or {}
            confirmation = tool_calls.get("confirmation")
            if isinstance(confirmation, dict) and confirmation.get("id"):
                confirmation_ids.append(confirmation["id"])
        action_statuses = repository.get_action_statuses(cursor, user_id, confirmation_ids)
        for message in messages:
            confirmation = (message.get("tool_calls") or {}).get("confirmation")
            if isinstance(confirmation, dict) and confirmation.get("id") in action_statuses:
                confirmation["status"] = action_statuses[confirmation["id"]]
        record_audit(
            user_id,
            "COURSE_AGENT_SESSION_VIEWED",
            "chat_session",
            session_id,
            {"course_id": session.get("course_id"), "message_count": len(messages)},
            cursor=cursor,
        )
    return {"session": session, "messages": messages}


def archive_chat_session(user_id: int, session_id: int) -> None:
    with get_cursor() as cursor:
        if not repository.archive_session(cursor, session_id, user_id):
            raise AppError("会话不存在或无访问权限", 404, "CHAT_SESSION_NOT_FOUND")
        record_audit(
            user_id,
            "COURSE_AGENT_SESSION_ARCHIVED",
            "chat_session",
            session_id,
            cursor=cursor,
        )
