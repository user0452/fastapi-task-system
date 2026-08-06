from __future__ import annotations

import pytest

from app.modules.agent.fast_rag import FastRagFallback, prepare_fast_rag
from app.modules.agent.query_resolver import resolve_course_query
from app.modules.agent.rag_router import choose_rag_route


def _route(message: str, resolution, *, course=True):
    return choose_rag_route(
        message=message,
        course={"id": 1} if course else None,
        resolution=resolution,
        confidence_threshold=0.85,
        enabled=True,
    )


def test_query_resolver_keeps_complete_question_unchanged():
    result = resolve_course_query("TCP 三次握手的目的是什么？")
    assert result.resolved_query == "TCP 三次握手的目的是什么？"
    assert result.confidence >= 0.85


def test_query_resolver_resolves_unique_last_search_focus():
    result = resolve_course_query(
        "那它为什么不能立即释放？",
        retrieval_state={"last_resolved_query": "TIME_WAIT 为什么需要等待 2MSL", "last_focus_topic": "TIME_WAIT"},
    )
    assert result.resolved_query == "TIME_WAIT 为什么不能立即释放？"
    assert result.focus_topic == "TIME_WAIT"
    assert result.resolution_source == "last_focus_topic"


def test_query_resolver_does_not_force_ambiguous_topics():
    result = resolve_course_query(
        "这个怎么理解？",
        recent_messages=[{"content": "TCP 的状态"}, {"content": "HTTP 的状态"}],
    )
    assert result.resolved_query == "这个怎么理解？"
    assert result.confidence < 0.85
    assert result.unresolved_references


def test_query_resolver_without_history_is_low_confidence_and_ignores_filler():
    result = resolve_course_query("它讲一下")
    assert result.focus_topic is None
    assert result.confidence < 0.85


def test_query_resolver_uses_single_persisted_knowledge_point_name():
    result = resolve_course_query(
        "这个有什么作用？",
        retrieval_state={"last_knowledge_point_names": ["拥塞窗口"]},
    )
    assert result.resolved_query == "拥塞窗口 有什么作用？"
    assert result.resolution_source == "last_knowledge_point_name"


def test_router_uses_fast_rag_only_for_single_topic_course_question():
    resolution = resolve_course_query("TCP 三次握手的目的是什么？")
    assert _route("TCP 三次握手的目的是什么？", resolution).route == "fast_rag"


@pytest.mark.parametrize("message", ["比较 TCP 和 UDP 的区别", "总结这一章", "给我出三道题", "修改学习计划"])
def test_router_routes_complex_or_business_requests_to_agent(message):
    resolution = resolve_course_query(message)
    assert _route(message, resolution).route == "agentic_rag"


def test_router_routes_low_confidence_reference_to_agent():
    resolution = resolve_course_query("它是什么？")
    assert _route("它是什么？", resolution).route == "agentic_rag"


def _citation(chunk_id: int, *, score: float = 0.8, material_id: int = 1, heading="A"):
    return {"chunk_id": chunk_id, "rerank_score": score, "material_id": material_id, "heading_path": heading}


def _fast_query_context(message: str) -> dict:
    resolution = resolve_course_query(message)
    return {
        "query_resolution": resolution,
        "retrieval_query": resolution.resolved_query,
        "context_report": {"query_resolution": {"query_resolution_fallback": False}},
    }


def test_fast_rag_reads_final_reranked_anchors_before_neighbors():
    calls = []

    def search(_user, _course, query, _top_k):
        calls.append(("search", query))
        return {"citations": [_citation(8, heading="A"), _citation(9, heading="A"), _citation(10, heading="B")]}

    def evidence(_user, _course, ids, window, _budget):
        calls.append(("evidence", ids, window))
        return {"evidence_blocks": [{"chunk_ids": ids}]}

    prepared = prepare_fast_rag(
        user_id=1, course_id=2, resolved_query="TCP 握手", search_materials=search,
        read_evidence=evidence, max_anchors=2, neighbor_window=1, min_retrieval_score=0.1,
    )
    assert prepared.anchor_chunk_ids == [8, 10]
    assert calls == [("search", "TCP 握手"), ("evidence", [8, 10], 1)]


@pytest.mark.parametrize("search_result,evidence_result", [({"citations": []}, None), ({"citations": [_citation(8)]}, {"evidence_blocks": []})])
def test_fast_rag_degrades_for_missing_retrieval_or_evidence(search_result, evidence_result):
    def search(*_args):
        return search_result

    def evidence(*_args):
        return evidence_result or {"evidence_blocks": []}

    with pytest.raises(FastRagFallback):
        prepare_fast_rag(
            user_id=1, course_id=2, resolved_query="TCP 握手", search_materials=search,
            read_evidence=evidence, max_anchors=2, neighbor_window=1, min_retrieval_score=0.1,
        )


def test_fast_rag_invokes_only_final_answer_provider_and_persists_once(monkeypatch):
    from types import SimpleNamespace

    from app.modules.agent import service
    from app.modules.agent.fast_rag import FastRagPrepared
    calls = []
    context = {
        "course": {"id": 2, "name": "网络"}, "session": {"id": 3}, "run": {"id": 4},
        "profile": None, "mastery": [], "recent_messages": [], "server_time": "now", "agent": None,
        "web_search_mode": "auto", "context_report": {},
    }
    context.update(_fast_query_context("TCP is what?"))
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        fast_rag_enabled=True, fast_rag_confidence_threshold=0.85, fast_rag_max_anchors=2,
        fast_rag_neighbor_window=1, fast_rag_min_retrieval_score=0.1,
    ))
    monkeypatch.setattr(service, "prepare_fast_rag", lambda **_kwargs: FastRagPrepared(
        citations=[_citation(8)], anchor_chunk_ids=[8], evidence={"evidence_blocks": [{"evidence_text": "证据"}]},
        retrieval_ms=1, evidence_ms=1,
    ))
    monkeypatch.setattr(service, "generate_agent_reply", lambda *args, **kwargs: calls.append((args, kwargs)) or "答案")
    monkeypatch.setattr(service, "_persist_assistant", lambda *_args, **_kwargs: {"id": 5, "content": "答案"})
    monkeypatch.setattr(service, "_persist_retrieval_state", lambda *_args, **_kwargs: calls.append("state"))

    result = service._fast_rag_reply(1, SimpleNamespace(message="TCP 是什么？"), context)

    assert result["intent"] == "fast_rag"
    assert len([call for call in calls if isinstance(call, tuple)]) == 1
    assert calls[-1] == "state"


def test_fast_rag_recoverable_preparation_failure_returns_none(monkeypatch):
    from types import SimpleNamespace

    from app.modules.agent import service
    context = {
        "course": {"id": 2}, "session": {"id": 3}, "run": {"id": 4}, "recent_messages": [],
        "agent": None, "web_search_mode": "auto", "context_report": {},
    }
    context.update(_fast_query_context("TCP is what?"))
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        fast_rag_enabled=True, fast_rag_confidence_threshold=0.85, fast_rag_max_anchors=2,
        fast_rag_neighbor_window=1, fast_rag_min_retrieval_score=0.1,
    ))
    monkeypatch.setattr(service, "prepare_fast_rag", lambda **_kwargs: (_ for _ in ()).throw(FastRagFallback("no_hits")))

    assert service._fast_rag_reply(1, SimpleNamespace(message="TCP 是什么？"), context) is None
    assert context["rag_trace"]["fallback_to_agent"] is True
