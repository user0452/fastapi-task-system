import asyncio
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from time import perf_counter, sleep
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Command
from pymysql.err import OperationalError

from app.core.config import get_settings
from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.metrics import inc_counter, observe
from app.integrations.embedding.service import (
    EMBEDDING_MODEL_NAME,
    embed_texts,
    serialize_embedding,
)
from app.integrations.llm.agent_responder import generate_agent_reply
from app.integrations.llm.agent_runtime import RiskConfirmationMiddleware
from app.integrations.llm.mysql_checkpointer import get_mysql_checkpointer
from app.modules.account.service import get_user_server_time
from app.modules.agent import repository
from app.modules.agent.context_manager import (
    RECENT_TURNS,
    build_agent_context,
    build_rolling_summary,
    select_relevant_memories,
)
from app.modules.agent.native_tool_agent import build_course_tool_agent
from app.modules.agent.schemas import (
    AgentChatRequest,
    ChatSessionCreate,
    CourseAgentMemoryPatch,
    CourseAgentMemoryUpsert,
)
from app.modules.agent.tools import (
    SandboxExecutor,
    ToolExecutionContext,
    ToolExecutor,
    build_default_tool_registry,
    calculate_expression,
    integration_status,
)
from app.modules.audit.service import record_audit
from app.modules.courses import repository as course_repository
from app.modules.learning import repository as learning_repository
from app.modules.learning.service import (
    generate_diagnostic,
    generate_practice,
    get_course_progress,
    get_diagnostic,
    get_study_plan,
    get_today_learning,
    get_wrong_answers,
)
from app.modules.materials.service import (
    get_course_evidence_context,
    list_course_material_outline,
    read_course_material_section,
    search_course_materials,
)
from app.modules.resources.schemas import ExternalResourceSearchRequest
from app.modules.resources.service import search_external_resources

TOOL_REGISTRY = build_default_tool_registry()
TOOL_EXECUTOR = ToolExecutor(TOOL_REGISTRY)
PYTHON_SANDBOX = SandboxExecutor()


# Memory CRUD lives in memory_service; re-export for existing imports.
from app.modules.agent.memory_service import (  # noqa: E402
    delete_chat_memory,
    delete_course_agent_memory,
    list_course_agent_memories,
    public_memory as _public_memory,
    require_course_agent as _require_course_agent,
    save_course_agent_memory,
    set_course_agent_memory_type_enabled,
    update_chat_memory,
    update_course_agent_memory,
    write_chat_memory,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgentRunCancelled(RuntimeError):
    pass


def _raise_if_cancelled(context: dict) -> None:
    cancel_event = context.get("cancel_event")
    if cancel_event is not None and cancel_event.is_set():
        raise AgentRunCancelled("客户端已取消生成")


def _stable_idempotency_key(request_id: str, tool_name: str, arguments: dict) -> str:
    payload = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{request_id}\0{tool_name}\0{payload}".encode("utf-8")).hexdigest()


def _agent_input_hash(
    user_id: int,
    session_id: int,
    course_id: int | None,
    message: str,
    intent: str,
    risk_level: str,
) -> str:
    normalized_message = unicodedata.normalize(
        "NFKC",
        message.replace("\r\n", "\n").replace("\r", "\n"),
    ).strip()
    payload = json.dumps(
        {
            "version": 1,
            "user_id": user_id,
            "session_id": session_id,
            "course_id": course_id,
            "message": normalized_message,
            "intent": intent,
            "risk_level": risk_level,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _agent_lease_config() -> tuple[float, float, float]:
    settings = get_settings()
    return (
        settings.agent_tool_lease_seconds,
        settings.agent_action_lease_seconds,
        settings.agent_lease_heartbeat_seconds,
    )


class _LeaseHeartbeat:
    """Run durable lease renewal off the request's execution thread."""

    def __init__(self, interval_seconds: float, renew: Callable[[], bool], name: str):
        self._interval_seconds = interval_seconds
        self._renew = renew
        self._stop_event = Event()
        self.lost = Event()
        self._thread = Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            try:
                if self._renew():
                    continue
            except Exception:
                pass
            self.lost.set()
            self._stop_event.set()
            return


def _tool_lease_lost() -> AppError:
    return AppError(
        "工具调用租约已由其他进程接管",
        409,
        "TOOL_CALL_LEASE_LOST",
    )


def _action_lease_lost() -> AppError:
    return AppError(
        "确认请求租约已由其他进程接管",
        409,
        "ACTION_LEASE_LOST",
    )


def _normalize_native_agent_reply(reply: str) -> str:
    """Keep internal evidence identifiers and ornamental symbols out of chat prose."""
    cleaned = re.sub(r"[ \t]*\[chunk_id\s*=\s*\d+\]", "", str(reply or ""), flags=re.IGNORECASE)
    for symbol in ("⭐", "🌟", "✨", "✅", "⚠️", "⚠", "📌", "😊", "🙂"):
        cleaned = cleaned.replace(symbol, "")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or "处理完成。"


def _retry_transaction(callback: Callable, attempts: int = 3):
    for attempt in range(attempts):
        try:
            return callback()
        except OperationalError as exc:
            retryable = exc.args and exc.args[0] in {1205, 1213}
            if not retryable or attempt == attempts - 1:
                raise
            sleep(0.02 * (attempt + 1))


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
            if isinstance((confirmation := (message.get("tool_calls") or {}).get("confirmation")), dict)
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
        "memories": [_public_memory(memory) for memory in memories],
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
        record_audit(user_id, "COURSE_AGENT_SESSION_ARCHIVED", "chat_session", session_id, cursor=cursor)


def _classify_intent(message: str) -> tuple[str, str]:
    compact = re.sub(r"\s+", "", message.lower())
    if "删除" in compact and "任务" in compact:
        return "delete_task", "destructive"
    if any(
        keyword in compact
        for keyword in ["给我出", "请出", "出几道题", "考考我", "测试一下", "做几道题"]
    ):
        return "generate_practice", "generate"
    if any(
        keyword in compact
        for keyword in ["网上学", "网上找", "视频", "b站", "bilibili", "youtube", "外部资源", "网课"]
    ):
        return "search_external_resources", "read"
    if any(keyword in compact for keyword in ["错题", "做错", "错误记录"]):
        return "get_wrong_answers", "read"
    if any(keyword in compact for keyword in ["出题", "道题", "练习题", "考考我", "测试一下", "做几道题"]):
        return "generate_practice", "generate"
    if any(keyword in compact for keyword in ["今日学习", "今天学什么", "今日任务"]):
        return "get_today", "read"
    if any(keyword in compact for keyword in ["学习进度", "掌握度", "薄弱点"]):
        return "get_progress", "read"
    if any(keyword in compact for keyword in ["学习计划", "后续计划", "接下来学", "课程计划"]):
        return "get_plan", "read"
    if any(keyword in compact for keyword in ["生成诊断", "诊断题", "入门测试"]):
        return "generate_diagnostic", "generate"
    return "course_qa", "read"


def _prepare_context(
    user_id: int,
    request: AgentChatRequest,
    intent: str,
    risk_level: str,
) -> dict:
    server_time = get_user_server_time(user_id)
    web_search_mode = str(getattr(request, "web_search_mode", None) or "auto").strip().lower()
    if web_search_mode not in {"off", "on", "auto"}:
        web_search_mode = "auto"
    with get_cursor() as cursor:
        session = None
        if request.session_id is not None:
            session = repository.get_session(cursor, request.session_id, user_id)
            if session is None or session.get("archived_at") is not None:
                raise AppError("会话不存在或无访问权限", 404, "CHAT_SESSION_NOT_FOUND")

        course = None
        requested_course_id = request.course_id or (session.get("course_id") if session else None)
        if requested_course_id is not None:
            course = course_repository.get_course(cursor, requested_course_id, user_id)
            if course is None or course.get("status") == "archived":
                raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        else:
            course = course_repository.get_current_course(cursor, user_id)

        if session and course and session.get("course_id") != course["id"]:
            raise AppError(
                "该会话属于另一门课程，不能跨课程复用上下文",
                409,
                "SESSION_COURSE_MISMATCH",
            )

        agent = None
        memories = []
        if course is not None:
            agent = repository.ensure_course_agent(cursor, user_id, course)
            if session is None:
                session = agent["primary_session"]
            memories = repository.list_course_memories(cursor, agent["id"], user_id)
        elif session is None:
            session = repository.create_session(cursor, user_id, None, request.message[:28])

        request_id = (
            str(
                uuid5(
                    NAMESPACE_URL,
                    f"a3-agent:{user_id}:{session['id']}:{request.client_request_id}",
                )
            )
            if request.client_request_id is not None
            else str(uuid4())
        )
        run = None
        if agent is not None or request.client_request_id is not None:
            client_request_id = (
                str(request.client_request_id)
                if request.client_request_id is not None
                else None
            )
            input_hash = _agent_input_hash(
                user_id,
                session["id"],
                course["id"] if course else None,
                request.message,
                intent,
                risk_level,
            )
            run, run_created = repository.claim_agent_run(
                cursor,
                request_id=request_id,
                client_request_id=client_request_id,
                input_hash=input_hash,
                agent_id=agent["id"] if agent else None,
                user_id=user_id,
                course_id=course["id"] if course else None,
                session_id=session["id"],
                intent=intent,
                risk_level=risk_level,
                input_summary=request.message,
                started_at=_utc_now(),
            )
            if not run_created:
                if (
                    run.get("input_hash") != input_hash
                    or run["session_id"] != session["id"]
                    or run["course_id"] != (course["id"] if course else None)
                ):
                    raise AppError(
                        "客户端请求 ID 已用于不同输入",
                        409,
                        "CLIENT_REQUEST_ID_CONFLICT",
                    )
                user_message = (
                    repository.get_message(cursor, run["user_message_id"], user_id)
                    if run.get("user_message_id")
                    else None
                )
                assistant_message = (
                    repository.get_message(cursor, run["assistant_message_id"], user_id)
                    if run.get("assistant_message_id")
                    else None
                )
                return {
                    "session": session,
                    "course": course,
                    "user_message": user_message,
                    "agent": agent,
                    "run": run,
                    "existing_assistant_message": assistant_message,
                    "server_time": server_time,
                    "duplicate_request": True,
                }

        user_message = repository.add_message(
            cursor,
            user_id,
            session["id"],
            course["id"] if course else None,
            "user",
            request.message,
            client_time_hint=request.current_time,
        )
        if run is not None:
            repository.set_agent_run_user_message(
                cursor,
                run["id"],
                user_id,
                user_message["id"],
            )
            run["user_message_id"] = user_message["id"]
        repository.update_session_title_if_default(
            cursor,
            session["id"],
            user_id,
            request.message[:28],
        )
        profile = repository.load_profile(cursor, user_id)
        if memories:
            profile = {
                "profile": profile or {},
                "course_memories": [
                    {
                        "key": memory["memory_key"],
                        "type": memory["memory_type"],
                        "content": memory["content"],
                    }
                    for memory in memories
                ],
            }
        mastery = (
            learning_repository.list_points_with_mastery(cursor, user_id, course["id"])
            if course
            else []
        )
        recent_messages = repository.list_messages(
            cursor,
            user_id,
            session["id"],
            user_message["id"],
            12,
        )
        if agent is not None:
            repository.touch_course_agent(cursor, agent["id"], user_id)

    if memories:
        selected_memories = select_relevant_memories(request.message, memories)
        base_profile = profile.get("profile", {}) if isinstance(profile, dict) and "profile" in profile else (profile or {})
        profile = {
            "profile": base_profile,
            "course_memories": [
                {
                    "key": memory["memory_key"],
                    "type": memory["memory_type"],
                    "content": memory["content"],
                }
                for memory in selected_memories
            ],
        }
        memories = selected_memories
    prompt_context, context_report = build_agent_context(
        course=course,
        profile=profile,
        mastery=mastery,
        memories=memories,
        messages=recent_messages,
        conversation_summary=agent.get("conversation_summary") if agent else None,
        server_time=server_time,
    )
    return {
        "session": session,
        "course": course,
        "profile": profile,
        "mastery": mastery,
        "recent_messages": recent_messages,
        "user_message": user_message,
        "agent": agent,
        "memories": memories,
        "prompt_context": prompt_context,
        "context_report": context_report,
        "run": run,
        "server_time": server_time,
        "web_search_mode": web_search_mode,
        "duplicate_request": False,
    }


def _execute_tool(
    user_id: int,
    context: dict,
    tool_name: str,
    risk_level: str,
    arguments: dict,
    callback: Callable,
):
    _raise_if_cancelled(context)
    run = context.get("run")
    if run is None:
        started = perf_counter()
        try:
            result = callback()
        except Exception:
            inc_counter("a3_agent_tool_calls_total", tool=tool_name, status="failed")
            raise
        else:
            _raise_if_cancelled(context)
            inc_counter("a3_agent_tool_calls_total", tool=tool_name, status="completed")
            return result
        finally:
            observe("a3_agent_tool_duration_seconds", perf_counter() - started, tool=tool_name)
    started_at = _utc_now()
    started = perf_counter()
    tool_lease_seconds, _, heartbeat_seconds = _agent_lease_config()
    idempotency_key = _stable_idempotency_key(run["request_id"], tool_name, arguments)
    lease_owner = uuid4().hex
    with get_cursor() as cursor:
        tool_call, claimed = repository.claim_tool_call(
            cursor,
            run_id=run["id"],
            user_id=user_id,
            course_id=context["course"]["id"],
            tool_name=tool_name,
            risk_level=risk_level,
            arguments=arguments,
            idempotency_key=idempotency_key,
            lease_owner=lease_owner,
            started_at=started_at,
            lease_expires_at=started_at + timedelta(seconds=tool_lease_seconds),
        )
    tool_call_id = tool_call["id"]
    if not claimed:
        if tool_call["status"] == "completed":
            return tool_call["result"]
        raise AppError("相同工具调用正在执行", 409, "TOOL_CALL_IN_PROGRESS")

    def renew_tool_lease() -> bool:
        heartbeat_at = _utc_now()
        with get_cursor() as cursor:
            return repository.renew_tool_call_lease(
                cursor,
                tool_call_id,
                user_id,
                lease_owner=lease_owner,
                heartbeat_at=heartbeat_at,
                lease_expires_at=heartbeat_at + timedelta(seconds=tool_lease_seconds),
            )

    heartbeat = _LeaseHeartbeat(
        heartbeat_seconds,
        renew_tool_lease,
        f"agent-tool-lease-{tool_call_id}",
    )
    heartbeat.start()
    try:
        _raise_if_cancelled(context)
        result = callback()
        _raise_if_cancelled(context)
    except AgentRunCancelled as exc:
        heartbeat.stop()
        if heartbeat.lost.is_set():
            raise _tool_lease_lost() from exc
        inc_counter("a3_agent_tool_calls_total", tool=tool_name, status="cancelled")
        observe("a3_agent_tool_duration_seconds", perf_counter() - started, tool=tool_name)
        with get_cursor() as cursor:
            finished = repository.finish_tool_call(
                cursor,
                tool_call_id,
                user_id,
                lease_owner=lease_owner,
                status="cancelled",
                error_message=str(exc),
                completed_at=_utc_now(),
            )
        if not finished:
            raise _tool_lease_lost() from exc
        raise
    except Exception as exc:
        heartbeat.stop()
        if heartbeat.lost.is_set():
            raise _tool_lease_lost() from exc
        inc_counter("a3_agent_tool_calls_total", tool=tool_name, status="failed")
        observe("a3_agent_tool_duration_seconds", perf_counter() - started, tool=tool_name)
        with get_cursor() as cursor:
            finished = repository.finish_tool_call(
                cursor,
                tool_call_id,
                user_id,
                lease_owner=lease_owner,
                status="failed",
                error_message=str(exc),
                completed_at=_utc_now(),
            )
        if not finished:
            raise _tool_lease_lost() from exc
        raise
    heartbeat.stop()
    if heartbeat.lost.is_set():
        raise _tool_lease_lost()
    if (
        tool_name == "delete_task"
        and tool_call.get("reclaimed")
        and isinstance(result, dict)
        and result.get("deleted") is False
    ):
        result = {**result, "deleted": True}
    with get_cursor() as cursor:
        finished = repository.finish_tool_call(
            cursor,
            tool_call_id,
            user_id,
            lease_owner=lease_owner,
            status="completed",
            result=result,
            completed_at=_utc_now(),
        )
    if not finished:
        raise _tool_lease_lost()
    inc_counter("a3_agent_tool_calls_total", tool=tool_name, status="completed")
    observe("a3_agent_tool_duration_seconds", perf_counter() - started, tool=tool_name)
    return result


def _tool_activity_label(tool_name: str, arguments: dict | None = None) -> str:
    labels = {
        "get_today_learning": "正在读取今日学习",
        "get_course_progress": "正在读取课程进度",
        "get_study_plan": "正在读取学习计划",
        "get_wrong_answers": "正在读取错题摘要",
        "search_course_knowledge": "正在检索课程资料",
        "read_course_evidence": "正在读取课程证据",
        "list_course_material_outline": "正在整理课程目录",
        "list_course_files": "正在列出课程文件",
        "read_course_section": "正在阅读课程章节",
        "search_external_resources": "正在联网搜索",
        "list_course_memories": "正在读取长期记忆",
        "write_course_memory": "正在写入长期记忆",
        "update_course_memory": "正在修改长期记忆",
        "delete_course_memory": "正在删除长期记忆",
        "generate_practice": "正在生成练习题",
        "get_or_generate_diagnostic": "正在准备课程诊断",
        "calculator": "正在计算",
        "python_sandbox": "正在运行受限 Python",
        "integration_status": "正在检查外部能力状态",
        "delete_task": "正在处理删除确认",
    }
    label = labels.get(tool_name, f"正在调用工具 {tool_name}")
    if tool_name == "search_external_resources" and isinstance(arguments, dict):
        topic = str(arguments.get("topic") or "").strip()
        if topic:
            short = topic if len(topic) <= 24 else f"{topic[:24]}…"
            return f"正在联网搜索：{short}"
    if tool_name == "search_course_knowledge" and isinstance(arguments, dict):
        query = str(arguments.get("query") or "").strip()
        if query:
            short = query if len(query) <= 24 else f"{query[:24]}…"
            return f"正在检索课程资料：{short}"
    return label


def _publish_activity(context: dict, message: str, *, phase: str, tool: str | None = None) -> None:
    callback = context.get("on_status")
    if not callable(callback):
        return
    payload = {"message": message, "phase": phase}
    if tool:
        payload["tool"] = tool
    try:
        callback(payload)
    except Exception:
        # Activity updates must never break the main agent run.
        return


def _unwrap_memory_result(result: Any) -> dict | None:
    """Accept either a public memory row or a tool wrapper {"memory": ...}."""
    if not isinstance(result, dict):
        return None
    memory = result.get("memory")
    if isinstance(memory, dict):
        return memory
    if any(key in result for key in ("id", "memory_key", "memory_type", "content")):
        return result
    return None


def _memory_update_entry(tool_name: str, arguments: dict, result: Any) -> dict | None:
    """Project successful memory tool results into the execution summary."""
    if tool_name == "write_course_memory":
        memory = _unwrap_memory_result(result)
        if memory is None:
            return None
        return {
            "op": "write",
            "id": memory.get("id"),
            "memory_key": memory.get("memory_key"),
            "memory_type": memory.get("memory_type"),
            "content": memory.get("content"),
        }
    if tool_name == "update_course_memory":
        memory = _unwrap_memory_result(result)
        if memory is None:
            return None
        return {
            "op": "update",
            "id": memory.get("id"),
            "memory_key": memory.get("memory_key"),
            "memory_type": memory.get("memory_type"),
            "content": memory.get("content"),
            "enabled": memory.get("enabled"),
        }
    if tool_name == "delete_course_memory":
        payload = result if isinstance(result, dict) else {}
        return {
            "op": "delete",
            "id": payload.get("memory_id") or arguments.get("memory_id"),
            "deleted": bool(payload.get("deleted")),
        }
    return None


def _record_memory_update(context: dict, tool_name: str, arguments: dict, result: Any) -> None:
    entry = _memory_update_entry(tool_name, arguments, result)
    if entry is None:
        return
    updates = context.setdefault("memory_updates", [])
    if len(updates) >= 20:
        return
    updates.append(entry)


def _execute_registered_tool(
    user_id: int,
    context: dict,
    tool_name: str,
    risk_level: str,
    arguments: dict,
    callback: Callable,
):
    executions = context.setdefault("tool_executions", [])
    phase = "web_search" if tool_name == "search_external_resources" else "tool"
    _publish_activity(
        context,
        _tool_activity_label(tool_name, arguments),
        phase=phase,
        tool=tool_name,
    )
    execution = TOOL_EXECUTOR.execute(
        name=tool_name,
        requested_risk=risk_level,
        arguments=arguments,
        execution_context=ToolExecutionContext(
            user_id=user_id,
            course_id=context["course"]["id"] if context.get("course") else None,
            request_id=context.get("run", {}).get("request_id"),
            confirmation_granted=tool_name in context.get("confirmed_tools", set()),
        ),
        callback=callback,
        durable_execute=lambda name, risk, args, execute: _execute_tool(
            user_id,
            context,
            name,
            risk,
            args,
            execute,
        ),
        record_sink=lambda record: executions.append(record) if len(executions) < 30 else None,
    )
    _record_memory_update(context, tool_name, arguments or {}, execution.value)
    _publish_activity(context, "正在整理工具结果", phase="thinking", tool=tool_name)
    return execution.value


def list_agent_tools() -> dict:
    return {
        "items": [definition.public() for definition in TOOL_REGISTRY.list()],
        "integrations": integration_status()["integrations"],
    }


def _execution_summary(
    context: dict,
    citations: list[dict],
    resources: list[dict],
) -> dict:
    internal_sources = []
    seen_chunks = set()
    for item in citations:
        chunk_id = item.get("chunk_id")
        if chunk_id is None or int(chunk_id) in seen_chunks:
            continue
        seen_chunks.add(int(chunk_id))
        internal_sources.append(
            {
                key: item.get(key)
                for key in (
                    "chunk_id",
                    "material_id",
                    "material_title",
                    "filename",
                    "page_number",
                    "heading_path",
                )
                if item.get(key) is not None
            }
        )
    external_sources = [
        {
            key: item.get(key)
            for key in ("id", "title", "url", "resource_type", "provider")
            if item.get(key) is not None
        }
        for item in resources[:12]
    ]
    report = context.get("context_report") or {}
    return {
        "tools": list(context.get("tool_executions") or []),
        "internal_sources": internal_sources[:20],
        "external_sources": external_sources,
        "context_used": {
            "memory_count": int(report.get("memory_count") or 0),
            "weak_point_count": int(report.get("weak_point_count") or 0),
            "recent_turns": int(report.get("recent_turns") or 0),
        },
        "updates": {
            "memory": list(context.get("memory_updates") or []),
            "roadmap": list(context.get("roadmap_updates") or []),
            "mastery": list(context.get("mastery_updates") or []),
        },
        "note": "仅展示可验证的调用与数据依据，不包含模型内部推理过程。",
    }


def _fail_run(user_id: int, context: dict, exc: Exception) -> None:
    run = context.get("run")
    if run is None:
        return
    with get_cursor() as cursor:
        repository.finish_agent_run(
            cursor,
            run["id"],
            user_id,
            status="failed",
            error_message=str(exc),
            completed_at=_utc_now(),
        )


def _cancel_run(user_id: int, context: dict, reason: str = "客户端已取消生成") -> None:
    run = context.get("run")
    if run is None:
        return
    with get_cursor() as cursor:
        repository.finish_agent_run(
            cursor,
            run["id"],
            user_id,
            status="cancelled",
            error_message=reason,
            completed_at=_utc_now(),
        )


def gc_agent_checkpoints(retention_minutes: int = 60) -> int:
    cutoff = _utc_now() - timedelta(minutes=max(1, int(retention_minutes)))
    return get_mysql_checkpointer().gc_stale_threads(cutoff)


def _match_knowledge_point_id(message: str, mastery: list[dict]) -> int | None:
    explicit = re.search(r"知识点\s*[#：:]?\s*(\d+)", message)
    if explicit:
        point_id = int(explicit.group(1))
        if any(point["id"] == point_id for point in mastery):
            return point_id
    compact = re.sub(r"\s+", "", message.lower())
    matches = [
        point
        for point in mastery
        if re.sub(r"\s+", "", point.get("name", "").lower()) in compact
    ]
    if matches:
        return max(matches, key=lambda point: len(point.get("name", "")))["id"]
    return mastery[0]["id"] if mastery else None


def _persist_assistant_in_transaction(
    cursor,
    user_id: int,
    context: dict,
    reply: str,
    intent: str,
    risk_level: str,
    citations: list[dict],
    cards: list[dict],
    resources: list[dict],
    actions: list[dict],
    confirmation: dict | None,
    context_report: dict | None = None,
    complete_run: bool = True,
    message_idempotency_key: str | None = None,
) -> dict:
    course = context["course"]
    tool_calls = {
        "intent": intent,
        "risk_level": risk_level,
        "cards": cards,
        "resources": resources,
        "actions": actions,
        "confirmation": confirmation,
        "context": context_report,
        "execution_summary": _execution_summary(context, citations, resources),
    }
    server_time_utc = _utc_now().isoformat(timespec="milliseconds") + "Z"
    # Keep the same lock order as _prepare_context: agent before session.
    if context.get("agent"):
        repository.touch_course_agent(cursor, context["agent"]["id"], user_id)
    if message_idempotency_key is None:
        message = repository.add_message(
            cursor,
            user_id,
            context["session"]["id"],
            course["id"] if course else None,
            "assistant",
            reply,
            tool_calls=tool_calls,
            sources=citations,
        )
        message_created = True
    else:
        message, message_created = repository.add_message_idempotent(
            cursor,
            user_id,
            context["session"]["id"],
            course["id"] if course else None,
            "assistant",
            reply,
            idempotency_key=message_idempotency_key,
            tool_calls=tool_calls,
            sources=citations,
        )
    if message_created:
        repository.add_audit_log(
            cursor,
            user_id,
            "AGENT_CHAT_V1",
            "chat_session",
            context["session"]["id"],
            {
                "intent": intent,
                "risk_level": risk_level,
                "course_id": course["id"] if course else None,
                "citation_count": len(citations),
                "resource_count": len(resources),
                "tool_execution_count": len(context.get("tool_executions") or []),
                "agent_run_id": context["run"]["id"] if context.get("run") else None,
                "confirmation_id": confirmation.get("id") if confirmation else None,
                "client_time_hint": context["user_message"].get("client_time_hint"),
                "server_time_utc": server_time_utc,
            },
        )
    if context.get("run"):
        if complete_run:
            repository.finish_agent_run(
                cursor,
                context["run"]["id"],
                user_id,
                status="completed",
                assistant_message_id=message["id"],
                output_summary=message["content"],
                completed_at=_utc_now(),
            )
        else:
            repository.pause_agent_run(
                cursor,
                context["run"]["id"],
                user_id,
                assistant_message_id=message["id"],
                output_summary=message["content"],
            )
    if context.get("agent"):
        current_agent = repository.get_course_agent(
            cursor, context["course"]["id"], user_id
        )
        unsummarized = repository.list_messages_after(
            cursor,
            user_id,
            context["session"]["id"],
            current_agent.get("last_summarized_message_id") if current_agent else None,
        )
        summarizable = unsummarized[:-RECENT_TURNS]
        if summarizable:
            repository.update_conversation_summary(
                cursor,
                context["agent"]["id"],
                user_id,
                build_rolling_summary(
                    current_agent.get("conversation_summary") if current_agent else None,
                    summarizable,
                ),
                int(summarizable[-1]["id"]),
            )
    return message


def _persist_assistant(
    user_id: int,
    context: dict,
    reply: str,
    intent: str,
    risk_level: str,
    citations: list[dict],
    cards: list[dict],
    resources: list[dict],
    actions: list[dict],
    confirmation: dict | None,
    context_report: dict | None = None,
    complete_run: bool = True,
    message_idempotency_key: str | None = None,
) -> dict:
    with get_cursor() as cursor:
        return _persist_assistant_in_transaction(
            cursor,
            user_id,
            context,
            reply,
            intent,
            risk_level,
            citations,
            cards,
            resources,
            actions,
            confirmation,
            context_report,
            complete_run,
            message_idempotency_key,
        )


def _request_task_deletion(user_id: int, context: dict, message: str) -> tuple[str, dict | None]:
    matches = re.findall(r"\d+", message)
    if not matches:
        return "请提供要删除的任务 ID。删除操作会在你再次确认后执行。", None
    task_id = int(matches[0])
    now = _utc_now()
    with get_cursor() as cursor:
        task = repository.get_task(cursor, task_id, user_id)
        if task is None:
            return f"没有找到任务 #{task_id}，或该任务不属于你。", None
        blocked = RiskConfirmationMiddleware({"delete_task": "destructive"}).intercept(
            "delete_task",
            {"task_id": task_id, "task_title": task["title"]},
        )
        if blocked is None:
            raise AppError("风险操作未被确认中间件拦截", 500, "RISK_MIDDLEWARE_BYPASSED")
        action = repository.create_action_request(
            cursor,
            user_id,
            context["session"]["id"],
            context["course"]["id"] if context["course"] else None,
            blocked.tool_name,
            blocked.arguments,
            _stable_idempotency_key(
                context["run"]["request_id"] if context.get("run") else str(context["session"]["id"]),
                blocked.tool_name,
                blocked.arguments,
            ),
            now + timedelta(minutes=10),
            now,
        )
    confirmation = {
        "id": action["id"],
        "tool_name": action["tool_name"],
        "risk_level": action["risk_level"],
        "summary": f"删除任务“{task['title']}”",
        "expires_at": action["expires_at"],
        "status": "pending",
    }
    return f"删除任务“{task['title']}”需要二次确认。确认前数据库不会发生删除。", confirmation


def _existing_run_response(context: dict, request: AgentChatRequest) -> dict:
    run = context["run"]
    message = context.get("existing_assistant_message")
    tool_calls = message.get("tool_calls") or {} if message else {}
    course = context.get("course")
    return {
        "session": {
            **context["session"],
            "course_id": course["id"] if course else context["session"].get("course_id"),
        },
        "course": course,
        "agent": context.get("agent"),
        "message": message,
        "reply": message.get("content") if message else run.get("output_summary") or "",
        "intent": tool_calls.get("intent") or run.get("intent"),
        "risk_level": tool_calls.get("risk_level") or run.get("risk_level"),
        "citations": message.get("sources") or [] if message else [],
        "cards": tool_calls.get("cards") or [],
        "resources": tool_calls.get("resources") or [],
        "actions": tool_calls.get("actions") or [],
        "confirmation": tool_calls.get("confirmation"),
        "current_time": context["server_time"],
        "run_id": run["id"],
        "request_status": run["status"],
        "error": run.get("error_message"),
        "idempotent": True,
    }


def run_agent_chat(
    user_id: int,
    request: AgentChatRequest,
    reply_provider: Callable = generate_agent_reply,
    search_provider: Callable = search_course_materials,
    external_search_provider: Callable = search_external_resources,
) -> dict:
    intent, risk_level = _classify_intent(request.message)
    context = _retry_transaction(
        lambda: _prepare_context(user_id, request, intent, risk_level)
    )
    if context.get("duplicate_request"):
        return _existing_run_response(context, request)
    course = context["course"]
    citations: list[dict] = []
    cards: list[dict] = []
    resources: list[dict] = []
    actions: list[dict] = []
    confirmation = None

    try:
        if intent == "delete_task":
            reply, confirmation = _execute_tool(
                user_id,
                context,
                "request_task_deletion",
                "destructive",
                {"message": request.message[:200]},
                lambda: _request_task_deletion(user_id, context, request.message),
            )
        elif intent == "get_today":
            if course is None:
                reply = "请先选择一门课程，再查看今日学习。"
                actions.append({"type": "navigate", "label": "选择课程", "to": "/courses"})
            else:
                today = _execute_tool(
                    user_id,
                    context,
                    "get_today_learning",
                    "read",
                    {"course_id": course["id"]},
                    lambda: get_today_learning(user_id, course["id"]),
                )
                cards.append({"type": "today", "data": today})
                reply = "已在对话中加载今日学习单元。" if today else "今天没有待完成的学习单元。"
                actions.append(
                    {
                        "type": "open_panel",
                        "panel": "plan",
                        "label": "查看课程计划",
                        "to": "/today",
                    }
                )
        elif intent == "get_progress":
            if course is None:
                reply = "请先选择一门课程，再查看学习进度。"
                actions.append({"type": "navigate", "label": "选择课程", "to": "/courses"})
            else:
                progress = _execute_tool(
                    user_id,
                    context,
                    "get_course_progress",
                    "read",
                    {"course_id": course["id"]},
                    lambda: get_course_progress(user_id, course["id"]),
                )
                cards.append({"type": "progress", "data": progress})
                reply = f"《{course['name']}》已完成 {progress['completion_rate']:.1f}% 的计划。"
                actions.append(
                    {
                        "type": "open_panel",
                        "panel": "overview",
                        "label": "查看完整进度",
                        "to": "/progress",
                    }
                )
        elif intent == "get_plan":
            if course is None:
                reply = "请先选择一门课程，再查看学习计划。"
                actions.append({"type": "navigate", "label": "选择课程", "to": "/courses"})
            else:
                plan = _execute_tool(
                    user_id,
                    context,
                    "get_study_plan",
                    "read",
                    {"course_id": course["id"]},
                    lambda: get_study_plan(user_id, course["id"]),
                )
                cards.append({"type": "plan", "data": plan})
                reply = "已加载这门课的完整计划。" if plan else "这门课还没有学习计划，可以先完成诊断。"
                actions.append({"type": "open_panel", "panel": "plan", "label": "打开计划面板"})
        elif intent == "get_wrong_answers":
            if course is None:
                reply = "请先选择一门课程，再查看错题。"
                actions.append({"type": "navigate", "label": "选择课程", "to": "/courses"})
            else:
                wrong = _execute_tool(
                    user_id,
                    context,
                    "get_wrong_answers",
                    "read",
                    {"course_id": course["id"]},
                    lambda: get_wrong_answers(user_id, course["id"]),
                )
                cards.append(
                    {
                        "type": "wrong_answers",
                        "data": {"total": wrong["total"], "items": wrong["items"][:3]},
                    }
                )
                reply = f"当前共记录 {wrong['total']} 道错题。" if wrong["total"] else "目前还没有错题记录。"
                actions.append({"type": "open_panel", "panel": "wrong", "label": "查看全部错题"})
        elif intent == "generate_practice":
            if course is None:
                reply = "请先选择一门课程，再生成针对性练习。"
                actions.append({"type": "navigate", "label": "选择课程", "to": "/courses"})
            else:
                point_id = _match_knowledge_point_id(request.message, context["mastery"])
                practice = _execute_tool(
                    user_id,
                    context,
                    "generate_practice",
                    "generate",
                    {
                        "course_id": course["id"],
                        "knowledge_point_id": point_id,
                        "question_count": 3,
                    },
                    lambda: generate_practice(user_id, course["id"], 3, point_id, "medium"),
                )
                cards.append({"type": "practice", "data": practice})
                reply = "已生成 3 道针对性练习。直接在下方作答，提交后会更新掌握度和后续计划。"
                actions.append({"type": "open_panel", "panel": "practice", "label": "查看做题记录"})
        elif intent == "generate_diagnostic":
            if course is None:
                reply = "请先选择课程并完成资料处理，再生成诊断题。"
                actions.append({"type": "navigate", "label": "选择课程", "to": "/courses"})
            else:
                with get_cursor() as cursor:
                    quiz_id = repository.get_latest_diagnostic_id(cursor, user_id, course["id"])
                diagnostic = _execute_tool(
                    user_id,
                    context,
                    "get_or_generate_diagnostic",
                    "generate",
                    {"course_id": course["id"], "existing_quiz_id": quiz_id},
                    lambda: get_diagnostic(user_id, quiz_id)
                    if quiz_id
                    else generate_diagnostic(user_id, course["id"]),
                )
                cards.append({"type": "diagnostic", "data": diagnostic, "reused": quiz_id is not None})
                if diagnostic.get("submitted"):
                    reply = "这门课程已经完成诊断，可以直接开始今日学习。"
                    actions.append(
                        {
                            "type": "open_panel",
                            "panel": "today",
                            "label": "查看今日学习",
                            "to": f"/learn/{course['id']}?panel=today",
                        }
                    )
                else:
                    reply = "已找到现有诊断题，可以继续作答。" if quiz_id else "已生成课程诊断题。"
                    actions.append(
                        {
                            "type": "open_panel",
                            "panel": "diagnostic",
                            "label": "开始诊断",
                            "to": f"/learn/{course['id']}?panel=diagnostic",
                        }
                    )
        elif intent == "search_external_resources":
            if course is None:
                reply = "请先选择一门课程，我才能根据课程知识点筛选外部视频。"
                actions.append({"type": "navigate", "label": "选择课程", "to": "/courses"})
            else:
                try:
                    search_result = _execute_tool(
                        user_id,
                        context,
                        "search_course_knowledge",
                        "read",
                        {"course_id": course["id"], "query": request.message, "top_k": 5},
                        lambda: search_provider(user_id, course["id"], request.message, 5),
                    )
                    citations = search_result.get("citations", [])
                except Exception:
                    citations = []
                external_result = _execute_tool(
                    user_id,
                    context,
                    "search_external_videos",
                    "read",
                    {"course_id": course["id"], "topic": request.message, "max_results": 4},
                    lambda: external_search_provider(
                        user_id,
                        course["id"],
                        ExternalResourceSearchRequest(topic=request.message, max_results=4),
                    ),
                )
                resources = external_result.get("resources", [])
                reply = reply_provider(
                    request.message,
                    course,
                    context["profile"],
                    context["mastery"],
                    context["recent_messages"],
                    citations,
                    context["server_time"],
                )
                if resources:
                    reply = f"{reply}\n\n我筛选了 {len(resources)} 个与本课知识点相关的外部视频，放在回答下方。"
                else:
                    reply = f"{reply}\n\n{external_result.get('warning') or '外部视频暂时没有返回结果。'}"
                actions.append({"type": "open_panel", "panel": "materials", "label": "查看收藏资源"})
        else:
            if course is not None:
                try:
                    search_result = _execute_tool(
                        user_id,
                        context,
                        "search_course_knowledge",
                        "read",
                        {"course_id": course["id"], "query": request.message, "top_k": 5},
                        lambda: search_provider(user_id, course["id"], request.message, 5),
                    )
                    citations = search_result.get("citations", [])
                except Exception:
                    citations = []
            reply = reply_provider(
                request.message,
                course,
                context["profile"],
                context["mastery"],
                context["recent_messages"],
                citations,
                context["server_time"],
            )
    except Exception as exc:
        _fail_run(user_id, context, exc)
        raise

    assistant_message = _retry_transaction(
        lambda: _persist_assistant(
            user_id,
            context,
            reply,
            intent,
            risk_level,
            citations,
            cards,
            resources,
            actions,
            confirmation,
            context.get("context_report"),
        )
    )
    return {
        "session": {
            **context["session"],
            "course_id": course["id"] if course else None,
        },
        "course": course,
        "agent": context.get("agent"),
        "message": assistant_message,
        "reply": reply,
        "intent": intent,
        "risk_level": risk_level,
        "citations": citations,
        "cards": cards,
        "resources": resources,
        "actions": actions,
        "confirmation": confirmation,
        "current_time": context["server_time"],
        "run_id": context["run"]["id"] if context.get("run") else None,
    }


def decide_action(user_id: int, action_id: int, confirmed: bool) -> dict:
    with get_cursor() as cursor:
        existing = repository.get_action_request(cursor, action_id, user_id)
    if existing and existing.get("checkpoint"):
        return _decide_durable_action(user_id, action_id, confirmed)

    now = _utc_now()
    expired = False
    outcome = None
    with get_cursor() as cursor:
        action = repository.get_action_request(cursor, action_id, user_id, for_update=True)
        if action is None:
            raise AppError("确认请求不存在或无访问权限", 404, "ACTION_NOT_FOUND")
        if action["status"] == "executed":
            return {"action": action, "result": action["result"], "idempotent": True}
        if action["status"] != "pending":
            raise AppError("确认请求已失效", 409, "ACTION_NOT_PENDING")
        if action["expires_at"] < now:
            repository.set_action_status(cursor, action_id, "expired")
            expired = True
        elif not confirmed:
            repository.set_action_status(cursor, action_id, "cancelled")
            repository.add_audit_log(
                cursor,
                user_id,
                "AGENT_ACTION_CANCELLED",
                action["tool_name"],
                action_id,
                {"server_time_utc": now.isoformat() + "Z"},
            )
            repository.add_message(
                cursor,
                user_id,
                action["session_id"],
                action.get("course_id"),
                "assistant",
                "已取消该操作，数据没有发生变化。",
                tool_calls={"intent": action["tool_name"], "action_status": "cancelled"},
            )
            outcome = {"action_id": action_id, "status": "cancelled"}
        else:
            if action["tool_name"] == "delete_task":
                task_id = int(action["payload"]["task_id"])
                deleted = repository.delete_task(cursor, task_id, user_id)
                result = {"task_id": task_id, "deleted": deleted}
                target_type = "task"
                target_id = task_id
                reply = "任务已删除。" if deleted else "任务已经不存在，无需重复删除。"
            else:
                raise AppError("不支持的受控工具", 400, "UNSUPPORTED_AGENT_TOOL")

            repository.set_action_status(cursor, action_id, "executed", result)
            repository.add_audit_log(
                cursor,
                user_id,
                "AGENT_ACTION_EXECUTED",
                target_type,
                target_id,
                {
                    "action_request_id": action_id,
                    "tool_name": action["tool_name"],
                    "result": result,
                    "server_time_utc": now.isoformat() + "Z",
                },
            )
            repository.add_message(
                cursor,
                user_id,
                action["session_id"],
                action.get("course_id"),
                "assistant",
                reply,
                tool_calls={"intent": action["tool_name"], "action_result": result},
            )
            outcome = {"action_id": action_id, "status": "executed", "result": result}

    if expired:
        raise AppError("确认请求已过期", 409, "ACTION_EXPIRED")
    if outcome is None:
        raise RuntimeError("action decision finished without an outcome")
    return outcome


def _native_delete_task(user_id: int, task_id: int) -> bool:
    with get_cursor() as cursor:
        return repository.delete_task(cursor, task_id, user_id)


def _native_latest_diagnostic_id(user_id: int, course_id: int) -> int | None:
    with get_cursor() as cursor:
        return repository.get_latest_diagnostic_id(cursor, user_id, course_id)


def _load_native_resume_context(user_id: int, action: dict) -> dict:
    checkpoint = action.get("checkpoint") or {}
    run_id = checkpoint.get("run_id")
    if not run_id:
        raise AppError("确认请求缺少图运行检查点", 409, "ACTION_CHECKPOINT_MISSING")
    with get_cursor() as cursor:
        run = repository.get_agent_run(cursor, int(run_id), user_id)
        if run is None:
            raise AppError("原 Agent 运行不存在", 404, "AGENT_RUN_NOT_FOUND")
        if run["session_id"] != action["session_id"] or run["course_id"] != action["course_id"]:
            raise AppError("确认请求与原 Agent 运行不匹配", 409, "ACTION_CHECKPOINT_MISMATCH")
        session = repository.get_session(cursor, run["session_id"], user_id)
        course = course_repository.get_course(cursor, run["course_id"], user_id)
        agent = repository.get_course_agent(cursor, run["course_id"], user_id)
        user_message = repository.get_message(cursor, run["user_message_id"], user_id)
        if session is None or course is None or agent is None or user_message is None:
            raise AppError("原 Agent 上下文已不可用", 409, "AGENT_CONTEXT_UNAVAILABLE")
        memories = repository.list_course_memories(cursor, agent["id"], user_id)
        profile = repository.load_profile(cursor, user_id)
        if memories:
            profile = {
                "profile": profile or {},
                "course_memories": [
                    {
                        "key": item["memory_key"],
                        "type": item["memory_type"],
                        "content": item["content"],
                    }
                    for item in memories
                ],
            }
        mastery = learning_repository.list_points_with_mastery(cursor, user_id, course["id"])
        recent_messages = repository.list_messages(cursor, user_id, session["id"], None, 12)
    memories = select_relevant_memories(action["tool_name"], memories)
    if isinstance(profile, dict) and "course_memories" in profile:
        profile["course_memories"] = [
            {
                "key": memory["memory_key"],
                "type": memory["memory_type"],
                "content": memory["content"],
            }
            for memory in memories
        ]
    server_time = get_user_server_time(user_id)
    prompt_context, context_report = build_agent_context(
        course=course,
        profile=profile,
        mastery=mastery,
        memories=memories,
        messages=recent_messages,
        conversation_summary=agent.get("conversation_summary"),
        server_time=server_time,
    )
    return {
        "session": session,
        "course": course,
        "profile": profile,
        "mastery": mastery,
        "recent_messages": recent_messages,
        "user_message": user_message,
        "agent": agent,
        "memories": memories,
        "prompt_context": prompt_context,
        "context_report": context_report,
        "run": run,
        "server_time": server_time,
    }


def _native_confirmation(
    user_id: int,
    context: dict,
    action_request: dict,
    graph_config: dict,
) -> tuple[str, dict | None]:
    """Persist a HumanInTheLoop interruption for the existing confirmation UI."""
    tool_name = str(action_request.get("name") or "")
    arguments = action_request.get("args") or {}
    now = _utc_now()
    if tool_name == "delete_task":
        try:
            task_id = int(arguments["task_id"])
        except (KeyError, TypeError, ValueError):
            return "删除操作缺少有效的任务 ID。", None
        with get_cursor() as cursor:
            task = repository.get_task(cursor, task_id, user_id)
            if task is None:
                return f"没有找到任务 #{task_id}，或该任务不属于你。", None
            action = repository.create_action_request(
                cursor,
                user_id,
                context["session"]["id"],
                context["course"]["id"] if context.get("course") else None,
                "delete_task",
                {
                    "task_id": task_id,
                    "task_title": task["title"],
                    "tool_call_id": action_request.get("id"),
                },
                _stable_idempotency_key(
                    context["run"]["request_id"],
                    "delete_task",
                    {"task_id": task_id},
                ),
                now + timedelta(minutes=10),
                now,
                checkpoint={
                    "thread_id": graph_config["configurable"]["thread_id"],
                    "checkpoint_ns": graph_config["configurable"].get("checkpoint_ns", ""),
                    "run_id": context["run"]["id"],
                    "request_id": context["run"]["request_id"],
                    "tool_call_id": action_request.get("id"),
                },
            )
        summary = f"删除任务“{task['title']}”"
        reply = f"删除任务“{task['title']}”需要二次确认。确认前不会执行工具。"
    elif tool_name == "delete_course_memory":
        if not context.get("course"):
            return "请先选择课程后再删除长期记忆。", None
        try:
            memory_id = int(arguments["memory_id"])
        except (KeyError, TypeError, ValueError):
            return "删除记忆缺少有效的记忆 ID。", None
        with get_cursor() as cursor:
            memory = repository.get_course_memory(
                cursor,
                memory_id,
                user_id,
                context["course"]["id"],
            )
            if memory is None:
                return f"没有找到记忆 #{memory_id}，或该记忆不属于当前课程。", None
            content = memory.get("content") or {}
            content_text = ""
            if isinstance(content, dict):
                content_text = str(
                    content.get("text")
                    or content.get("value")
                    or content.get("summary")
                    or content.get("goal")
                    or content.get("preference")
                    or content.get("description")
                    or ""
                ).strip()
            if not content_text:
                content_text = json.dumps(content, ensure_ascii=False, default=str)[:80]
            action = repository.create_action_request(
                cursor,
                user_id,
                context["session"]["id"],
                context["course"]["id"],
                "delete_course_memory",
                {
                    "course_id": context["course"]["id"],
                    "memory_id": memory_id,
                    "memory_key": memory.get("memory_key"),
                    "memory_type": memory.get("memory_type"),
                    "content_preview": content_text[:120],
                    "tool_call_id": action_request.get("id"),
                },
                _stable_idempotency_key(
                    context["run"]["request_id"],
                    "delete_course_memory",
                    {"memory_id": memory_id},
                ),
                now + timedelta(minutes=10),
                now,
                checkpoint={
                    "thread_id": graph_config["configurable"]["thread_id"],
                    "checkpoint_ns": graph_config["configurable"].get("checkpoint_ns", ""),
                    "run_id": context["run"]["id"],
                    "request_id": context["run"]["request_id"],
                    "tool_call_id": action_request.get("id"),
                },
            )
        summary = f"删除长期记忆“{content_text[:40] or memory.get('memory_key') or memory_id}”"
        reply = f"{summary}需要二次确认。确认前不会执行工具。"
    else:
        return "该工具需要确认后才能继续。", None

    confirmation = {
        "id": action["id"],
        "tool_name": action["tool_name"],
        "risk_level": action["risk_level"],
        "summary": summary,
        "status": action["status"],
        "expires_at": action["expires_at"],
    }
    return reply, confirmation


def _build_native_agent(user_id: int, context: dict):
    return build_course_tool_agent(
        user_id=user_id,
        context=context,
        run_tool=lambda name, risk, args, callback: _execute_registered_tool(
            user_id, context, name, risk, args, callback
        ),
        get_today=get_today_learning,
        get_progress=get_course_progress,
        get_plan=get_study_plan,
        get_wrong_answers=get_wrong_answers,
        generate_practice=generate_practice,
        generate_diagnostic=generate_diagnostic,
        get_diagnostic=get_diagnostic,
        get_latest_diagnostic_id=_native_latest_diagnostic_id,
        search_materials=search_course_materials,
        read_material_evidence=get_course_evidence_context,
        list_material_outline=list_course_material_outline,
        read_material_section=read_course_material_section,
        search_external=search_external_resources,
        list_memories=list_course_agent_memories,
        write_memory=write_chat_memory,
        update_memory=update_chat_memory,
        delete_memory=delete_chat_memory,
        delete_owned_task=_native_delete_task,
        calculate=calculate_expression,
        run_python=lambda code: PYTHON_SANDBOX.execute(
            code,
            user_id=user_id,
            course_id=context["course"]["id"],
        ),
        get_integration_status=integration_status,
        checkpointer=get_mysql_checkpointer(),
    )


def _resume_native_action(user_id: int, action: dict, confirmed: bool) -> dict:
    context = _load_native_resume_context(user_id, action)
    context["confirmed_tools"] = {action["tool_name"]} if confirmed else set()
    agent, artifacts = _build_native_agent(user_id, context)
    checkpoint = action["checkpoint"]
    config = {
        "configurable": {
            "thread_id": checkpoint["thread_id"],
            "checkpoint_ns": checkpoint.get("checkpoint_ns", ""),
        },
        "recursion_limit": 18,
    }
    decision = {"type": "approve" if confirmed else "reject"}
    if not confirmed:
        decision["message"] = "用户取消了该风险操作，未执行工具。"
    state = agent.invoke(Command(resume={"decisions": [decision]}), config=config)
    if state.get("__interrupt__"):
        raise AppError("风险操作恢复后再次中断", 409, "ACTION_RESUME_INTERRUPTED")
    reply = next(
        (
            str(message.content or "").strip()
            for message in reversed(state.get("messages", []))
            if isinstance(message, AIMessage) and message.content
        ),
        "操作已执行。" if confirmed else "已取消该操作。",
    )
    reply = _normalize_native_agent_reply(reply)
    result = None
    if confirmed and action["tool_name"] == "delete_task":
        task_id = int(action["payload"]["task_id"])
        with get_cursor() as cursor:
            result = {
                "task_id": task_id,
                "deleted": repository.get_task(cursor, task_id, user_id) is None,
            }
    elif confirmed and action["tool_name"] == "delete_course_memory":
        memory_id = int(action["payload"]["memory_id"])
        course_id = int(action["payload"].get("course_id") or context["course"]["id"])
        with get_cursor() as cursor:
            remaining = repository.get_course_memory(cursor, memory_id, user_id, course_id)
        result = {
            "memory_id": memory_id,
            "deleted": remaining is None,
        }
    return {
        "reply": reply,
        "result": result,
        "context": context,
        "citations": artifacts.citations,
        "cards": artifacts.cards,
        "resources": artifacts.resources,
        "actions": artifacts.actions,
    }


def _decide_durable_action(user_id: int, action_id: int, confirmed: bool) -> dict:
    now = _utc_now()
    resume_owner = uuid4().hex
    _, action_lease_seconds, heartbeat_seconds = _agent_lease_config()
    expired = False
    with get_cursor() as cursor:
        action = repository.get_action_request(cursor, action_id, user_id, for_update=True)
        if action is None:
            raise AppError("确认请求不存在或无访问权限", 404, "ACTION_NOT_FOUND")
        if action["status"] in {"executed", "cancelled"}:
            return {
                "action": action,
                "status": action["status"],
                "result": action["result"],
                "idempotent": True,
            }
        if action["status"] not in {"pending", "resuming"}:
            raise AppError("确认请求已失效", 409, "ACTION_NOT_PENDING")
        if action["expires_at"] < now:
            repository.set_action_status(cursor, action_id, "expired")
            expired = True
        else:
            claimed = repository.claim_action_resume(
                cursor,
                action_id,
                owner=resume_owner,
                started_at=now,
                lease_expires_at=now + timedelta(seconds=action_lease_seconds),
            )
            if not claimed:
                raise AppError("确认请求正在执行", 409, "ACTION_IN_PROGRESS")
    if expired:
        raise AppError("确认请求已过期", 409, "ACTION_EXPIRED")

    def renew_action_lease() -> bool:
        heartbeat_at = _utc_now()
        with get_cursor() as cursor:
            return repository.renew_action_resume_lease(
                cursor,
                action_id,
                user_id,
                resume_owner=resume_owner,
                heartbeat_at=heartbeat_at,
                lease_expires_at=heartbeat_at + timedelta(seconds=action_lease_seconds),
            )

    heartbeat = _LeaseHeartbeat(
        heartbeat_seconds,
        renew_action_lease,
        f"agent-action-lease-{action_id}",
    )
    heartbeat.start()
    try:
        resumed = _resume_native_action(user_id, action, confirmed)
    except Exception as exc:
        heartbeat.stop()
        if heartbeat.lost.is_set():
            raise _action_lease_lost() from exc
        with get_cursor() as cursor:
            repository.reset_action_pending(cursor, action_id, owner=resume_owner)
        raise
    heartbeat.stop()
    if heartbeat.lost.is_set():
        raise _action_lease_lost()

    status = "executed" if confirmed else "cancelled"
    completed_at = _utc_now()
    with get_cursor() as cursor:
        current = repository.get_action_request(cursor, action_id, user_id, for_update=True)
        if current is None:
            raise AppError("确认请求不存在", 404, "ACTION_NOT_FOUND")
        if current["status"] in {"executed", "cancelled"}:
            return {
                "action": current,
                "status": current["status"],
                "result": current["result"],
                "idempotent": True,
            }
        if current["status"] != "resuming":
            raise AppError("确认请求状态冲突", 409, "ACTION_STATE_CONFLICT")
        checkpoint = current.get("checkpoint") or {}
        if checkpoint.get("resume_owner") != resume_owner:
            raise _action_lease_lost()
        message = _persist_assistant_in_transaction(
            cursor,
            user_id,
            resumed["context"],
            resumed["reply"],
            "native_tool_agent_resume",
            "destructive",
            resumed["citations"],
            resumed["cards"],
            resumed["resources"],
            resumed["actions"],
            None,
            resumed["context"].get("context_report"),
            True,
            f"agent-action:{action_id}:final",
        )
        if not repository.finalize_action_resume(
            cursor,
            action_id,
            user_id,
            resume_owner=resume_owner,
            status=status,
            result=resumed["result"],
            completed_at=completed_at,
        ):
            raise _action_lease_lost()
        repository.add_audit_log(
            cursor,
            user_id,
            "AGENT_ACTION_EXECUTED" if confirmed else "AGENT_ACTION_CANCELLED",
            action["tool_name"],
            action_id,
            {
                "action_request_id": action_id,
                "tool_name": action["tool_name"],
                "result": resumed["result"],
                "graph_thread_id": checkpoint["thread_id"],
                "server_time_utc": completed_at.isoformat() + "Z",
            },
        )
    return {
        "action_id": action_id,
        "status": status,
        "result": resumed["result"],
        "reply": message["content"],
        "message": message,
    }


def run_native_tool_agent_chat(
    user_id: int,
    request: AgentChatRequest,
    on_delta: Callable[[str], None] | None = None,
    cancel_event: Event | None = None,
    on_status: Callable[[dict | str], None] | None = None,
) -> dict:
    """Run the v1 course agent using native model tool calls, not JSON plans."""
    if on_status is not None:
        on_status({"message": "已收到问题，正在加载课程上下文", "phase": "thinking"})
    context = _retry_transaction(
        lambda: _prepare_context(user_id, request, "native_tool_agent", "mixed")
    )
    if context.get("duplicate_request"):
        return _existing_run_response(context, request)
    context["cancel_event"] = cancel_event
    context["on_status"] = on_status
    course = context.get("course")
    artifacts = None
    confirmation = None
    llm_started = perf_counter()
    llm_status = "failed"
    inc_counter(
        "a3_llm_tokens_total",
        max(1, (len(request.message) + 3) // 4),
        direction="input",
        mode="native_tool_agent",
    )
    try:
        if on_status is not None:
            on_status({"message": "正在思考如何回答", "phase": "thinking"})
        agent, artifacts = _build_native_agent(user_id, context)
        thread_id = f"course-agent-{context['run']['request_id']}"
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 18,
        }
        _raise_if_cancelled(context)
        if on_delta is None:
            state = agent.invoke({"messages": [("user", request.message)]}, config=config)
        else:
            if on_status is not None:
                on_status({"message": "正在生成回答", "phase": "answering"})
            for chunk, _metadata in agent.stream(
                {"messages": [("user", request.message)]},
                config=config,
                stream_mode="messages",
            ):
                _raise_if_cancelled(context)
                if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str) and chunk.content:
                    on_delta(chunk.content)
            snapshot = agent.get_state(config)
            state = dict(snapshot.values)
            if snapshot.interrupts:
                state["__interrupt__"] = snapshot.interrupts
        _raise_if_cancelled(context)
        if on_status is not None:
            on_status({"message": "正在整理最终回答", "phase": "answering"})
        interrupts = state.get("__interrupt__") or []
        if interrupts:
            interrupt_value = getattr(interrupts[0], "value", {}) or {}
            pending = (interrupt_value.get("action_requests") or [{}])[0]
            reply, confirmation = _native_confirmation(user_id, context, pending, config)
        else:
            reply = next(
                (
                    str(message.content or "").strip()
                    for message in reversed(state.get("messages", []))
                    if isinstance(message, AIMessage) and message.content
                ),
                "处理完成。",
            )
        reply = _normalize_native_agent_reply(reply)
        inc_counter(
            "a3_llm_tokens_total",
            max(1, (len(reply) + 3) // 4),
            direction="output",
            mode="native_tool_agent",
        )
        message = _persist_assistant(
            user_id,
            context,
            reply,
            "native_tool_agent",
            "destructive" if confirmation else "mixed",
            artifacts.citations if artifacts else [],
            artifacts.cards if artifacts else [],
            artifacts.resources if artifacts else [],
            artifacts.actions if artifacts else [],
            confirmation,
            context.get("context_report"),
            complete_run=confirmation is None,
        )
        if confirmation is None:
            get_mysql_checkpointer().delete_thread(thread_id)
        llm_status = "completed"
        return {
            "session": {**context["session"], "course_id": course["id"] if course else None},
            "course": course,
            "agent": context.get("agent"),
            "message": message,
            "reply": reply,
            "intent": "native_tool_agent",
            "risk_level": "destructive" if confirmation else "mixed",
            "citations": artifacts.citations if artifacts else [],
            "cards": artifacts.cards if artifacts else [],
            "resources": artifacts.resources if artifacts else [],
            "actions": artifacts.actions if artifacts else [],
            "confirmation": confirmation,
            "current_time": context["server_time"],
            "run_id": context["run"]["id"] if context.get("run") else None,
        }
    except AgentRunCancelled as exc:
        _cancel_run(user_id, context, str(exc))
        llm_status = "cancelled"
        raise
    except Exception as exc:
        _fail_run(user_id, context, exc)
        raise
    finally:
        inc_counter("a3_llm_requests_total", mode="native_tool_agent", status=llm_status)
        observe(
            "a3_llm_request_duration_seconds",
            perf_counter() - llm_started,
            mode="native_tool_agent",
        )


async def run_native_tool_agent_chat_async(
    user_id: int,
    request: AgentChatRequest,
    on_delta: Callable[[str], None] | None = None,
    cancel_event: Event | None = None,
    on_status: Callable[[dict | str], None] | None = None,
) -> dict:
    """Run the streaming agent on LangGraph's async interface so cancellation propagates."""
    if on_status is not None:
        on_status({"message": "已收到问题，正在加载课程上下文", "phase": "thinking"})
    context = _retry_transaction(
        lambda: _prepare_context(user_id, request, "native_tool_agent", "mixed")
    )
    if context.get("duplicate_request"):
        return _existing_run_response(context, request)
    context["cancel_event"] = cancel_event
    context["on_status"] = on_status
    course = context.get("course")
    artifacts = None
    confirmation = None
    llm_started = perf_counter()
    llm_status = "failed"
    inc_counter(
        "a3_llm_tokens_total",
        max(1, (len(request.message) + 3) // 4),
        direction="input",
        mode="native_tool_agent_async",
    )
    thread_id = f"course-agent-{context['run']['request_id']}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 18,
    }
    try:
        if on_status is not None:
            on_status({"message": "正在思考如何回答", "phase": "thinking"})
        agent, artifacts = _build_native_agent(user_id, context)
        _raise_if_cancelled(context)
        answering_started = False
        async for chunk, _metadata in agent.astream(
            {"messages": [("user", request.message)]},
            config=config,
            stream_mode="messages",
        ):
            _raise_if_cancelled(context)
            if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str) and chunk.content:
                if on_status is not None and not answering_started:
                    answering_started = True
                    on_status({"message": "正在生成回答", "phase": "answering"})
                if on_delta is not None:
                    on_delta(chunk.content)
        snapshot = await agent.aget_state(config)
        state = dict(snapshot.values)
        if snapshot.interrupts:
            state["__interrupt__"] = snapshot.interrupts
        _raise_if_cancelled(context)
        if on_status is not None:
            on_status({"message": "正在整理最终回答", "phase": "answering"})
        interrupts = state.get("__interrupt__") or []
        if interrupts:
            interrupt_value = getattr(interrupts[0], "value", {}) or {}
            pending = (interrupt_value.get("action_requests") or [{}])[0]
            reply, confirmation = _native_confirmation(user_id, context, pending, config)
        else:
            reply = next(
                (
                    str(message.content or "").strip()
                    for message in reversed(state.get("messages", []))
                    if isinstance(message, AIMessage) and message.content
                ),
                "处理完成。",
            )
        reply = _normalize_native_agent_reply(reply)
        inc_counter(
            "a3_llm_tokens_total",
            max(1, (len(reply) + 3) // 4),
            direction="output",
            mode="native_tool_agent_async",
        )
        message = _persist_assistant(
            user_id,
            context,
            reply,
            "native_tool_agent",
            "destructive" if confirmation else "mixed",
            artifacts.citations if artifacts else [],
            artifacts.cards if artifacts else [],
            artifacts.resources if artifacts else [],
            artifacts.actions if artifacts else [],
            confirmation,
            context.get("context_report"),
            complete_run=confirmation is None,
        )
        if confirmation is None:
            get_mysql_checkpointer().delete_thread(thread_id)
        llm_status = "completed"
        return {
            "session": {**context["session"], "course_id": course["id"] if course else None},
            "course": course,
            "agent": context.get("agent"),
            "message": message,
            "reply": reply,
            "intent": "native_tool_agent",
            "risk_level": "destructive" if confirmation else "mixed",
            "citations": artifacts.citations if artifacts else [],
            "cards": artifacts.cards if artifacts else [],
            "resources": artifacts.resources if artifacts else [],
            "actions": artifacts.actions if artifacts else [],
            "confirmation": confirmation,
            "current_time": context["server_time"],
            "run_id": context["run"]["id"] if context.get("run") else None,
        }
    except asyncio.CancelledError:
        if cancel_event is not None:
            cancel_event.set()
        _cancel_run(user_id, context)
        llm_status = "cancelled"
        raise
    except AgentRunCancelled as exc:
        _cancel_run(user_id, context, str(exc))
        llm_status = "cancelled"
        raise
    except Exception as exc:
        _fail_run(user_id, context, exc)
        raise
    finally:
        inc_counter("a3_llm_requests_total", mode="native_tool_agent_async", status=llm_status)
        observe(
            "a3_llm_request_duration_seconds",
            perf_counter() - llm_started,
            mode="native_tool_agent_async",
        )
