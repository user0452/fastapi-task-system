import json

from app.modules.agent import router as agent_router


def test_agent_v1_routes_delegate_and_keep_response_envelope(api_client, monkeypatch):
    monkeypatch.setattr(
        agent_router,
        "list_agent_tools",
        lambda: {"items": [{"name": "calculator"}]},
    )
    monkeypatch.setattr(
        agent_router,
        "list_chat_sessions",
        lambda user_id, page, size, course_id: {
            "user_id": user_id,
            "page": page,
            "size": size,
            "course_id": course_id,
        },
    )
    monkeypatch.setattr(
        agent_router,
        "get_course_agent_workspace",
        lambda user_id, course_id, limit, session_id: {
            "user_id": user_id,
            "course_id": course_id,
            "limit": limit,
            "session_id": session_id,
        },
    )
    monkeypatch.setattr(agent_router, "save_course_agent_memory", lambda user_id, course_id, request: {"user_id": user_id, "course_id": course_id, "key": request.memory_key})
    monkeypatch.setattr(
        agent_router,
        "list_course_agent_memories",
        lambda user_id, course_id: {"items": [], "user_id": user_id, "course_id": course_id},
    )
    monkeypatch.setattr(
        agent_router,
        "update_course_agent_memory",
        lambda user_id, course_id, memory_id, request: {
            "id": memory_id,
            "user_id": user_id,
            "course_id": course_id,
            "enabled": request.enabled,
        },
    )
    monkeypatch.setattr(
        agent_router,
        "set_course_agent_memory_type_enabled",
        lambda user_id, course_id, memory_type, enabled: {
            "user_id": user_id,
            "course_id": course_id,
            "memory_type": memory_type,
            "enabled": enabled,
        },
    )
    deleted_memories = []
    monkeypatch.setattr(
        agent_router,
        "delete_course_agent_memory",
        lambda user_id, course_id, memory_id: deleted_memories.append(
            (user_id, course_id, memory_id)
        ),
    )
    monkeypatch.setattr(agent_router, "create_chat_session", lambda user_id, request: {"id": 41, "user_id": user_id, "title": request.title})
    monkeypatch.setattr(agent_router, "get_chat_session", lambda user_id, session_id, before_id, size: {"user_id": user_id, "session_id": session_id, "before_id": before_id, "size": size})
    archived = []
    monkeypatch.setattr(agent_router, "archive_chat_session", lambda user_id, session_id: archived.append((user_id, session_id)))
    monkeypatch.setattr(agent_router, "run_native_tool_agent_chat", lambda user_id, request, **_kwargs: {"user_id": user_id, "reply": request.message})
    monkeypatch.setattr(agent_router, "decide_action", lambda user_id, action_id, confirmed: {"user_id": user_id, "action_id": action_id, "confirmed": confirmed})

    assert api_client.get("/api/v1/agent/tools").json()["data"]["items"][0] == {
        "name": "calculator"
    }
    sessions = api_client.get(
        "/api/v1/agent/sessions?page=2&size=5&course_id=13"
    ).json()["data"]
    assert sessions["page"] == 2
    assert sessions["course_id"] == 13
    workspace = api_client.get(
        "/api/v1/agent/courses/13/workspace?message_limit=7&session_id=41"
    ).json()["data"]
    assert workspace["limit"] == 7
    assert workspace["session_id"] == 41
    memory = api_client.put(
        "/api/v1/agent/courses/13/memories",
        json={"memory_key": "style", "memory_type": "preference", "content": {"brief": True}},
    )
    assert memory.json()["data"]["key"] == "style"
    memory_list = api_client.get("/api/v1/agent/courses/13/memories").json()["data"]
    assert memory_list["course_id"] == 13
    patched = api_client.patch(
        "/api/v1/agent/courses/13/memories/8",
        json={"enabled": False},
    ).json()["data"]
    assert patched["id"] == 8
    assert patched["course_id"] == 13
    assert patched["enabled"] is False
    type_state = api_client.patch(
        "/api/v1/agent/courses/13/memory-types/weak_point",
        json={"enabled": False},
    ).json()["data"]
    assert type_state["memory_type"] == "weak_point"
    assert api_client.delete("/api/v1/agent/courses/13/memories/8").status_code == 200
    assert deleted_memories and deleted_memories[0][1:] == (13, 8)
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
