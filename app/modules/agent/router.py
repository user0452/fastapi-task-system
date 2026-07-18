import asyncio
import json
import os
from contextlib import suppress
from threading import Event

from fastapi import Depends, Path, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.responses import V1APIRouter, success
from app.modules.agent.schemas import (
    ActionDecision,
    AgentChatRequest,
    ChatSessionCreate,
    CourseAgentMemoryPatch,
    CourseAgentMemoryTypeToggle,
    CourseAgentMemoryUpsert,
)
from app.modules.agent.service import (
    archive_chat_session,
    create_chat_session,
    decide_action,
    delete_course_agent_memory,
    get_chat_session,
    get_course_agent_workspace,
    list_agent_tools,
    list_chat_sessions,
    list_course_agent_memories,
    run_native_tool_agent_chat,
    run_native_tool_agent_chat_async,
    save_course_agent_memory,
    set_course_agent_memory_type_enabled,
    update_course_agent_memory,
)
from app.modules.auth.dependencies import get_current_user

router = V1APIRouter(prefix="/agent", tags=["course-agent"])
MAX_CONCURRENT_STREAMS = max(1, int(os.getenv("AGENT_MAX_CONCURRENT_STREAMS", "8")))
STREAM_TIMEOUT_SECONDS = max(10.0, float(os.getenv("AGENT_STREAM_TIMEOUT_SECONDS", "180")))
_stream_slots = asyncio.Semaphore(MAX_CONCURRENT_STREAMS)


@router.get("/tools")
def tools_catalog(user=Depends(get_current_user)):
    _ = user
    return success(data=list_agent_tools())


def _event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False, default=str) + "\n"


@router.get("/sessions")
def sessions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    course_id: int | None = Query(default=None, gt=0),
    user=Depends(get_current_user),
):
    return success(data=list_chat_sessions(user["id"], page, size, course_id))


@router.get("/courses/{course_id}/workspace")
def course_agent_workspace(
    course_id: int,
    message_limit: int = Query(default=100, ge=1, le=100),
    session_id: int | None = Query(default=None, gt=0),
    user=Depends(get_current_user),
):
    return success(
        data=get_course_agent_workspace(user["id"], course_id, message_limit, session_id)
    )


@router.put("/courses/{course_id}/memories")
def put_course_agent_memory(
    course_id: int,
    request: CourseAgentMemoryUpsert,
    user=Depends(get_current_user),
):
    return success(
        data=save_course_agent_memory(user["id"], course_id, request),
        message="课程助手记忆已更新",
    )


@router.get("/courses/{course_id}/memories")
def course_agent_memories(course_id: int, user=Depends(get_current_user)):
    return success(data=list_course_agent_memories(user["id"], course_id))


@router.patch("/courses/{course_id}/memories/{memory_id}")
def patch_course_agent_memory(
    course_id: int,
    memory_id: int,
    request: CourseAgentMemoryPatch,
    user=Depends(get_current_user),
):
    return success(
        data=update_course_agent_memory(user["id"], course_id, memory_id, request),
        message="课程助手记忆已更新",
    )


@router.patch("/courses/{course_id}/memory-types/{memory_type}")
def toggle_course_agent_memory_type(
    course_id: int,
    request: CourseAgentMemoryTypeToggle,
    memory_type: str = Path(
        ...,
        min_length=1,
        max_length=40,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    ),
    user=Depends(get_current_user),
):
    return success(
        data=set_course_agent_memory_type_enabled(
            user["id"],
            course_id,
            memory_type,
            request.enabled,
        ),
        message="记忆类型状态已更新",
    )


@router.delete("/courses/{course_id}/memories/{memory_id}")
def remove_course_agent_memory(
    course_id: int,
    memory_id: int,
    user=Depends(get_current_user),
):
    delete_course_agent_memory(user["id"], course_id, memory_id)
    return success(message="课程助手记忆已删除")


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

        def publish(event_type: str, payload: object) -> None:
            if cancelled.is_set():
                return
            try:
                events.put_nowait((event_type, payload))
            except asyncio.QueueFull:
                cancelled.set()

        async def run() -> None:
            try:
                def publish_status(payload: object) -> None:
                    if isinstance(payload, dict):
                        message = str(payload.get("message") or "").strip()
                        phase = str(payload.get("phase") or "thinking")
                        tool = payload.get("tool")
                        publish(
                            "status",
                            {
                                "message": message or "正在处理",
                                "phase": phase,
                                "tool": tool,
                            },
                        )
                    else:
                        publish("status", {"message": str(payload), "phase": "thinking"})

                result = await run_native_tool_agent_chat_async(
                    user["id"],
                    request,
                    on_delta=lambda delta: publish("reply_delta", delta),
                    cancel_event=cancelled,
                    on_status=publish_status,
                )
                publish("result", result)
            except Exception as exc:
                if not cancelled.is_set():
                    publish("error", str(exc))
            finally:
                publish("worker_done", None)

        async with _stream_slots:
            worker = asyncio.create_task(run())
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
                            if isinstance(payload, dict):
                                yield _event(
                                    "status",
                                    message=str(payload.get("message") or ""),
                                    phase=str(payload.get("phase") or "thinking"),
                                    tool=payload.get("tool"),
                                )
                            else:
                                yield _event("status", message=str(payload), phase="thinking")
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
                with suppress(asyncio.CancelledError):
                    await worker

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
