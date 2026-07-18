import json

import pytest
from langchain.agents.middleware import HumanInTheLoopMiddleware

from app.modules.agent import native_tool_agent


def _build_agent(monkeypatch, *, course=True, latest_diagnostic_id=91, web_search_mode='auto'):
    captured = {}
    calls = []

    def fake_create_agent(model, **kwargs):
        captured.update(model=model, **kwargs)
        return {"kind": "fake-agent"}

    def run_tool(name, risk_level, arguments, callback):
        calls.append((name, risk_level, arguments))
        return callback()

    monkeypatch.setattr(native_tool_agent, "create_agent", fake_create_agent)
    monkeypatch.setattr(native_tool_agent, "get_llm", lambda: "fake-model")

    agent, artifacts = native_tool_agent.build_course_tool_agent(
        user_id=7,
        context={
            "course": {"id": 13, "name": "Databases"} if course else None,
            "prompt_context": '{"safe": true}',
            "web_search_mode": web_search_mode,
        },
        run_tool=run_tool,
        get_today=lambda user_id, course_id: {"user_id": user_id, "course_id": course_id},
        get_progress=lambda _user_id, _course_id: {"percent": 42},
        get_plan=lambda _user_id, _course_id: None,
        get_wrong_answers=lambda _user_id, _course_id: {"total": 3},
        generate_practice=lambda _user_id, _course_id, count, point_id, difficulty: {
            "count": count,
            "knowledge_point_id": point_id,
            "difficulty": difficulty,
        },
        generate_diagnostic=lambda _user_id, _course_id: {"id": 92, "created": True},
        get_diagnostic=lambda _user_id, diagnostic_id: {"id": diagnostic_id, "created": False},
        get_latest_diagnostic_id=lambda _user_id, _course_id: latest_diagnostic_id,
        search_materials=lambda _user_id, _course_id, query, count: {
            "citations": [
                {"chunk_id": 101, "snippet": query},
                {"chunk_id": 101, "snippet": "duplicate"},
                {"chunk_id": 102, "snippet": str(count)},
            ]
        },
        read_material_evidence=lambda _user_id, _course_id, ids, window, budget: {
            "chunk_ids": ids,
            "neighbor_window": window,
            "budget": budget,
            "used_tokens": 750,
        },
        list_material_outline=lambda _user_id, _course_id, material_id: {
            "materials": [
                {"id": material_id or 1, "sections": list(range(80))}
                for _ in range(15)
            ]
        },
        read_material_section=lambda _user_id, _course_id, material_id, heading, budget: {
            "material_id": material_id,
            "heading": heading,
            "budget": budget,
            "used_tokens": 500,
        },
        search_external=lambda _user_id, _course_id, request: {
            "resources": [{"title": request.topic}]
        },
        list_memories=lambda _user_id, _course_id: {
            "items": [
                {
                    "id": 7,
                    "memory_key": "preferred_style",
                    "memory_type": "course_preference",
                    "content": {"text": "先给结论"},
                    "enabled": True,
                    "source_type": "manual",
                    "updated_at": "2026-07-19T00:00:00",
                }
            ],
            "total": 1,
        },
        write_memory=lambda _user_id, _course_id, **kwargs: {
            "id": 8,
            "memory_key": kwargs.get("memory_key") or "chat_demo",
            "memory_type": kwargs.get("memory_type") or "course_context",
            "content": {"text": kwargs.get("text")},
            "enabled": True,
            "source_type": "chat",
        },
        update_memory=lambda _user_id, _course_id, memory_id, **kwargs: {
            "id": memory_id,
            "memory_type": kwargs.get("memory_type") or "course_context",
            "content": {"text": kwargs.get("text") or "updated"},
            "enabled": True if kwargs.get("enabled") is None else kwargs.get("enabled"),
            "source_type": "chat",
        },
        delete_memory=lambda _user_id, _course_id, memory_id: {
            "memory_id": memory_id,
            "deleted": True,
        },
        delete_owned_task=lambda _user_id, task_id: task_id == 33,
        calculate=lambda expression: {"expression": expression, "result": 42},
        run_python=lambda code: {"status": "completed", "stdout": code},
        get_integration_status=lambda: {
            "status": "available",
            "integrations": {"mcp": {"status": "unconfigured"}},
        },
        checkpointer="durable-checkpointer",
    )
    tools = {item.name: item for item in captured["tools"]}
    return agent, artifacts, captured, calls, tools


def test_native_agent_registers_tools_human_approval_and_checkpointer(monkeypatch):
    agent, artifacts, captured, calls, tools = _build_agent(monkeypatch)

    assert agent == {"kind": "fake-agent"}
    assert captured["model"] == "fake-model"
    assert captured["checkpointer"] == "durable-checkpointer"
    assert len(tools) == 20
    assert "search_external_learning_resources" in tools
    assert "write_course_memory" in tools
    assert "update_course_memory" in tools
    assert "delete_course_memory" in tools
    assert "list_course_memories" in tools
    assert "自动模式" in captured["system_prompt"] or "自动" in captured["system_prompt"]
    assert "write_course_memory" in captured["system_prompt"]
    assert len(captured["middleware"]) == 1
    assert isinstance(captured["middleware"][0], HumanInTheLoopMiddleware)
    assert set(captured["middleware"][0].interrupt_on) >= {
        "delete_course_memory",
        "delete_task",
    }
    assert "prompt_context" not in captured["system_prompt"]
    assert '{"safe": true}' in captured["system_prompt"]

    assert json.loads(tools["get_today_learning"].invoke({}))["course_id"] == 13
    assert json.loads(tools["get_course_progress"].invoke({}))["percent"] == 42
    assert "message" in json.loads(tools["get_study_plan"].invoke({}))
    assert json.loads(tools["get_wrong_answer_summary"].invoke({}))["total"] == 3

    search = json.loads(
        tools["search_course_knowledge"].invoke({"query": "B-tree", "result_count": 99})
    )
    assert search["total"] == 3
    assert search["anchors"][0]["chunk_id"] == 101
    assert [item["chunk_id"] for item in artifacts.citations] == [101, 102]
    tools["search_course_knowledge"].invoke({"query": "index", "result_count": 4})
    tools["search_course_knowledge"].invoke({"query": "join", "result_count": 4})
    assert json.loads(
        tools["search_course_knowledge"].invoke({"query": "limit", "result_count": 4})
    )["error"] == "RAG_SEARCH_LIMIT_REACHED"

    evidence = json.loads(
        tools["read_course_evidence"].invoke(
            {"chunk_ids": [101, 101, -1, 102], "neighbor_window": 9}
        )
    )
    assert evidence["chunk_ids"] == [101, 102]
    assert evidence["neighbor_window"] == 2
    assert evidence["remaining_evidence_tokens"] == 11_250

    outline = json.loads(tools["list_course_material_outline"].invoke({"material_id": 5}))
    assert len(outline["materials"]) == 12
    assert len(outline["materials"][0]["sections"]) == 60
    files = json.loads(tools["list_course_files"].invoke({}))
    assert len(files["files"]) == 15

    section = json.loads(
        tools["read_course_section"].invoke({"material_id": 5, "heading_path": "1/2"})
    )
    assert section["heading"] == "1/2"
    assert section["remaining_evidence_tokens"] == 10_750
    tools["read_course_evidence"].invoke({"chunk_ids": [102], "neighbor_window": 1})
    assert json.loads(
        tools["read_course_evidence"].invoke({"chunk_ids": [102], "neighbor_window": 1})
    )["error"] == "RAG_EVIDENCE_LIMIT_REACHED"

    external = json.loads(
        tools["search_external_learning_resources"].invoke({"topic": "normalization"})
    )
    assert external["resources"][0]["title"] == "normalization"
    assert artifacts.resources == external["resources"]

    memories = json.loads(tools["list_course_memories"].invoke({}))
    assert memories["total"] == 1
    written = json.loads(
        tools["write_course_memory"].invoke(
            {
                "text": "我更喜欢先看结论",
                "memory_type": "course_preference",
                "memory_key": "style_pref",
            }
        )
    )
    assert written["memory"]["content"]["text"] == "我更喜欢先看结论"
    updated = json.loads(
        tools["update_course_memory"].invoke(
            {"memory_id": 7, "text": "使用短段落", "enabled": True}
        )
    )
    assert updated["memory"]["content"]["text"] == "使用短段落"
    deleted_memory = json.loads(tools["delete_course_memory"].invoke({"memory_id": 7}))
    assert deleted_memory == {"memory_id": 7, "deleted": True}

    practice = json.loads(
        tools["generate_practice_questions"].invoke(
            {"knowledge_point_id": 8, "question_count": 50, "difficulty": "hard"}
        )
    )
    assert practice["count"] == 10
    diagnostic = json.loads(tools["generate_diagnostic_questions"].invoke({}))
    assert diagnostic == {"id": 91, "created": False}
    assert artifacts.actions[-1] == {
        "type": "open_panel",
        "panel": "diagnostic",
        "label": "开始诊断",
        "to": "/learn/13?panel=diagnostic",
    }
    deleted = json.loads(tools["delete_task"].invoke({"task_id": 33}))
    assert deleted == {"task_id": 33, "deleted": True}
    assert json.loads(tools["calculator"].invoke({"expression": "6 * 7"}))["result"] == 42
    assert json.loads(tools["python_sandbox"].invoke({"code": "print(42)"}))["stdout"] == "print(42)"
    assert json.loads(tools["integration_status"].invoke({}))["integrations"]["mcp"]["status"] == "unconfigured"

    called_names = {name for name, _risk, _args in calls}
    assert {
        "get_today_learning",
        "get_course_progress",
        "get_study_plan",
        "get_wrong_answers",
        "search_course_knowledge",
        "read_course_evidence",
        "list_course_material_outline",
        "list_course_files",
        "read_course_section",
        "search_external_resources",
        "list_course_memories",
        "write_course_memory",
        "update_course_memory",
        "delete_course_memory",
        "generate_practice",
        "get_or_generate_diagnostic",
        "calculator",
        "python_sandbox",
        "integration_status",
        "delete_task",
    } == called_names
    assert next(risk for name, risk, _args in calls if name == "delete_task") == "destructive"
    assert next(risk for name, risk, _args in calls if name == "delete_course_memory") == "destructive"
    assert next(risk for name, risk, _args in calls if name == "write_course_memory") == "write"
    assert any(card["type"] == "practice" for card in artifacts.cards)


def test_native_agent_disables_external_search_when_web_search_off(monkeypatch):
    _agent, _artifacts, captured, _calls, tools = _build_agent(
        monkeypatch, web_search_mode="off"
    )

    assert "search_external_learning_resources" not in tools
    assert len(tools) == 19
    assert "关闭联网搜索" in captured["system_prompt"]


def test_native_agent_prefers_external_search_when_web_search_on(monkeypatch):
    _agent, _artifacts, captured, _calls, tools = _build_agent(
        monkeypatch, web_search_mode="on"
    )

    assert "search_external_learning_resources" in tools
    assert "开启联网搜索" in captured["system_prompt"]


def test_native_agent_rejects_course_tools_without_active_course(monkeypatch):
    _agent, _artifacts, _captured, _calls, tools = _build_agent(monkeypatch, course=False)

    with pytest.raises(ValueError):
        tools["get_today_learning"].invoke({})


def test_diagnostic_tool_generates_when_no_existing_quiz(monkeypatch):
    _agent, artifacts, _captured, _calls, tools = _build_agent(
        monkeypatch, latest_diagnostic_id=None
    )

    assert json.loads(tools["generate_diagnostic_questions"].invoke({})) == {
        "id": 92,
        "created": True,
    }
    assert artifacts.actions[-1]["panel"] == "diagnostic"
