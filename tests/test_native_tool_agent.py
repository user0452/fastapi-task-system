import json

import pytest
from langchain.agents.middleware import HumanInTheLoopMiddleware

from app.modules.agent import native_tool_agent


def _build_agent(monkeypatch, *, course=True, latest_diagnostic_id=91):
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
        delete_owned_task=lambda _user_id, task_id: task_id == 33,
        checkpointer="durable-checkpointer",
    )
    tools = {item.name: item for item in captured["tools"]}
    return agent, artifacts, captured, calls, tools


def test_native_agent_registers_tools_human_approval_and_checkpointer(monkeypatch):
    agent, artifacts, captured, calls, tools = _build_agent(monkeypatch)

    assert agent == {"kind": "fake-agent"}
    assert captured["model"] == "fake-model"
    assert captured["checkpointer"] == "durable-checkpointer"
    assert len(tools) == 12
    assert len(captured["middleware"]) == 1
    assert isinstance(captured["middleware"][0], HumanInTheLoopMiddleware)
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

    practice = json.loads(
        tools["generate_practice_questions"].invoke(
            {"knowledge_point_id": 8, "question_count": 50, "difficulty": "hard"}
        )
    )
    assert practice["count"] == 10
    diagnostic = json.loads(tools["generate_diagnostic_questions"].invoke({}))
    assert diagnostic == {"id": 91, "created": False}
    deleted = json.loads(tools["delete_task"].invoke({"task_id": 33}))
    assert deleted == {"task_id": 33, "deleted": True}

    called_names = {name for name, _risk, _args in calls}
    assert {
        "get_today_learning",
        "get_course_progress",
        "get_study_plan",
        "get_wrong_answers",
        "search_course_knowledge",
        "read_course_evidence",
        "list_course_material_outline",
        "read_course_section",
        "search_external_resources",
        "generate_practice",
        "get_or_generate_diagnostic",
        "delete_task",
    } == called_names
    assert next(risk for name, risk, _args in calls if name == "delete_task") == "destructive"
    assert any(card["type"] == "practice" for card in artifacts.cards)


def test_native_agent_rejects_course_tools_without_active_course(monkeypatch):
    _agent, _artifacts, _captured, _calls, tools = _build_agent(monkeypatch, course=False)

    with pytest.raises(ValueError):
        tools["get_today_learning"].invoke({})


def test_diagnostic_tool_generates_when_no_existing_quiz(monkeypatch):
    _agent, _artifacts, _captured, _calls, tools = _build_agent(
        monkeypatch, latest_diagnostic_id=None
    )

    assert json.loads(tools["generate_diagnostic_questions"].invoke({})) == {
        "id": 92,
        "created": True,
    }
