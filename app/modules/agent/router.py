import asyncio
import json
import os
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Event

from fastapi import Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.responses import V1APIRouter, success
from app.modules.agent.schemas import (
    ActionDecision,
    AgentChatRequest,
    ChatSessionCreate,
    CourseAgentMemoryUpsert,
)
from app.modules.agent.service import (
    archive_chat_session,
    create_chat_session,
    decide_action,
    get_chat_session,
    get_course_agent_workspace,
    list_chat_sessions,
    run_native_tool_agent_chat,
    save_course_agent_memory,
)
from app.modules.auth.dependencies import get_current_user

router = V1APIRouter(prefix="/agent", tags=["course-agent"])
MAX_CONCURRENT_STREAMS = max(1, int(os.getenv("AGENT_MAX_CONCURRENT_STREAMS", "8")))
STREAM_TIMEOUT_SECONDS = max(10.0, float(os.getenv("AGENT_STREAM_TIMEOUT_SECONDS", "180")))
_stream_slots = asyncio.Semaphore(MAX_CONCURRENT_STREAMS)


def _event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False, default=str) + "\n"


@router.get("/sessions")
def sessions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user=Depends(get_current_user),
):
    return success(data=list_chat_sessions(user["id"], page, size))


@router.get("/courses/{course_id}/workspace")
def course_agent_workspace(
    course_id: int,
    message_limit: int = Query(default=100, ge=1, le=100),
    user=Depends(get_current_user),
):
    return success(data=get_course_agent_workspace(user["id"], course_id, message_limit))


@router.put("/courses/{course_id}/memories")
def update_course_agent_memory(
    course_id: int,
    request: CourseAgentMemoryUpsert,
    user=Depends(get_current_user),
):
    return success(
        data=save_course_agent_memory(user["id"], course_id, request),
        message="课程助手记忆已更新",
    )


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def new_session(request: ChatSessionCreate, user=Depends(get_current_user)):
    return success(data=create_chat_session(user["id"], request), message="会话已创建", code=201)


@router.get("/sessions/{session_id}")
def session_detail(
    session_id: int,
    before_id: int | None = Query(default=None, gt=0),
    size: int = Query(default=100, ge=1, le=100),
    user=Depends(get_current_user),
):
    return success(data=get_chat_session(user["id"], session_id, before_id, size))


@router.post("/sessions/{session_id}/archive")
def archive_session(session_id: int, user=Depends(get_current_user)):
    archive_chat_session(user["id"], session_id)
    return success(message="会话已归档")


@router.post("/chat")
def chat(request: AgentChatRequest, user=Depends(get_current_user)):
    return success(data=run_native_tool_agent_chat(user["id"], request))


@router.post("/chat/stream", response_model=None)
async def chat_stream(request: AgentChatRequest, http_request: Request, user=Depends(get_current_user)):
    async def stream():
        events: asyncio.Queue[tuple[str, object]] = asyncio.Queue(maxsize=128)
        cancelled = Event()
        loop = asyncio.get_running_loop()

        def publish(event_type: str, payload: object) -> None:
            if cancelled.is_set():
                return
            future = asyncio.run_coroutine_threadsafe(events.put((event_type, payload)), loop)
            try:
                future.result(timeout=2)
            except FutureTimeoutError:
                cancelled.set()
                future.cancel()

        def run() -> None:
            try:
                publish("status", "已收到问题，正在加载课程上下文")
                publish("status", "Agent 正在选择并执行工具")
                result = run_native_tool_agent_chat(
                    user["id"],
                    request,
                    on_delta=lambda delta: publish("reply_delta", delta),
                    cancel_event=cancelled,
                )
                publish("result", result)
            except Exception as exc:
                if not cancelled.is_set():
                    publish("error", str(exc))
            finally:
                publish("worker_done", None)

        async with _stream_slots:
            worker = asyncio.create_task(asyncio.to_thread(run))
            worker_done = False
            try:
                async with asyncio.timeout(STREAM_TIMEOUT_SECONDS):
                    while not worker_done or not events.empty():
                        if await http_request.is_disconnected():
                            cancelled.set()
                            break
                        try:
                            event_type, payload = await asyncio.wait_for(events.get(), timeout=0.25)
                        except TimeoutError:
                            if worker.done() and events.empty():
                                break
                            continue
                        if event_type == "worker_done":
                            worker_done = True
                        elif event_type == "status":
                            yield _event("status", message=str(payload))
                        elif event_type == "reply_delta":
                            yield _event("reply_delta", delta=str(payload))
                        elif event_type == "result":
                            yield _event("result", data=payload)
                            yield _event("done")
                        else:
                            yield _event("error", message=str(payload))
            except TimeoutError:
                cancelled.set()
                yield _event("error", message="生成超时，请稍后重试")
            finally:
                cancelled.set()
                if not worker.done():
                    worker.cancel()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/actions/{action_id}/decision")
def action_decision(
    action_id: int,
    request: ActionDecision,
    user=Depends(get_current_user),
):
    return success(data=decide_action(user["id"], action_id, request.confirmed))
