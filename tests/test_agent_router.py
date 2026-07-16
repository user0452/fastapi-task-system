import json

from app.modules.agent import router as agent_router


def test_agent_v1_routes_delegate_and_keep_response_envelope(api_client, monkeypatch):
    monkeypatch.setattr(agent_router, "list_chat_sessions", lambda user_id, page, size: {"user_id": user_id, "page": page, "size": size})
    monkeypatch.setattr(agent_router, "get_course_agent_workspace", lambda user_id, course_id, limit: {"user_id": user_id, "course_id": course_id, "limit": limit})
    monkeypatch.setattr(agent_router, "save_course_agent_memory", lambda user_id, course_id, request: {"user_id": user_id, "course_id": course_id, "key": request.memory_key})
    monkeypatch.setattr(agent_router, "create_chat_session", lambda user_id, request: {"id": 41, "user_id": user_id, "title": request.title})
    monkeypatch.setattr(agent_router, "get_chat_session", lambda user_id, session_id, before_id, size: {"user_id": user_id, "session_id": session_id, "before_id": before_id, "size": size})
    archived = []
    monkeypatch.setattr(agent_router, "archive_chat_session", lambda user_id, session_id: archived.append((user_id, session_id)))
    monkeypatch.setattr(agent_router, "run_native_tool_agent_chat", lambda user_id, request, **_kwargs: {"user_id": user_id, "reply": request.message})
    monkeypatch.setattr(agent_router, "decide_action", lambda user_id, action_id, confirmed: {"user_id": user_id, "action_id": action_id, "confirmed": confirmed})

    assert api_client.get("/api/v1/agent/sessions?page=2&size=5").json()["data"]["page"] == 2
    assert api_client.get("/api/v1/agent/courses/13/workspace?message_limit=7").json()["data"]["limit"] == 7
    memory = api_client.put(
        "/api/v1/agent/courses/13/memories",
        json={"memory_key": "style", "memory_type": "preference", "content": {"brief": True}},
    )
    assert memory.json()["data"]["key"] == "style"
    created = api_client.post("/api/v1/agent/sessions", json={"course_id": 13, "title": "Review"})
    assert created.status_code == 201
    assert created.json()["code"] == 201
    detail = api_client.get("/api/v1/agent/sessions/41?before_id=99&size=6")
    assert detail.json()["data"]["before_id"] == 99
    assert api_client.post("/api/v1/agent/sessions/41/archive").status_code == 200
    assert archived and archived[0][1] == 41
    assert api_client.post("/api/v1/agent/chat", json={"message": "hello"}).json()["data"]["reply"] == "hello"
    decision = api_client.post("/api/v1/agent/actions/12/decision", json={"confirmed": False})
    assert decision.json()["data"]["confirmed"] is False


def test_agent_stream_emits_real_deltas_result_and_done(api_client, monkeypatch):
    async def fake_chat(_user_id, request, *, on_delta, cancel_event):
        assert request.message == "stream this"
        assert not cancel_event.is_set()
        on_delta("first ")
        on_delta("second")
        return {"reply": "first second", "citations": [{"chunk_id": 9}]}

    monkeypatch.setattr(agent_router, "run_native_tool_agent_chat_async", fake_chat)

    with api_client.stream(
        "POST", "/api/v1/agent/chat/stream", json={"message": "stream this"}
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert [event["delta"] for event in events if event["type"] == "reply_delta"] == [
        "first ",
        "second",
    ]
    assert next(event for event in events if event["type"] == "result")["data"]["reply"] == "first second"
    assert events[-1]["type"] == "done"


def test_agent_stream_serializes_worker_failure(api_client, monkeypatch):
    async def failed_chat(*_args, **_kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(agent_router, "run_native_tool_agent_chat_async", failed_chat)

    response = api_client.post("/api/v1/agent/chat/stream", json={"message": "fail"})
    events = [json.loads(line) for line in response.text.splitlines() if line]

    assert response.status_code == 200
    assert any(
        event["type"] == "error" and event["message"] == "model unavailable"
        for event in events
    )
