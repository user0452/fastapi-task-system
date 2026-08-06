"""Regression coverage for the single, session-scoped retrieval query."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from app.modules.agent.context_manager import select_relevant_memories
from app.modules.agent.fast_rag import FastRagPrepared
from app.modules.agent.query_resolver import resolve_course_query
from app.modules.agent.schemas import AgentChatRequest


def _settings():
    return SimpleNamespace(fast_rag_confidence_threshold=0.85)


def test_self_contained_question_keeps_one_unified_retrieval_query(monkeypatch):
    from app.modules.agent import service

    monkeypatch.setattr(service, "get_settings", _settings)
    result, retrieval_query = service._resolve_retrieval_query(
        "What does ThreadPoolExecutor corePoolSize do?",
        retrieval_state=None,
        recent_messages=[],
        conversation_summary=None,
    )

    assert retrieval_query == "What does ThreadPoolExecutor corePoolSize do?"
    assert result["trace"]["original_query"] == retrieval_query
    assert result["trace"]["resolved_query"] == retrieval_query
    assert result["trace"]["query_resolution_fallback"] is False


def test_resolved_reference_is_used_for_memory_retrieval(monkeypatch):
    from app.modules.agent import service

    monkeypatch.setattr(service, "get_settings", _settings)
    result, retrieval_query = service._resolve_retrieval_query(
        "\u90a3\u8fd9\u4e2a\u8bbe\u7f6e\u592a\u5927\u4f1a\u600e\u4e48\u6837\uff1f",
        retrieval_state={"last_focus_topic": "corePoolSize"},
        recent_messages=[],
        conversation_summary=None,
    )
    memories = [
        {
            "memory_key": "pool-size",
            "memory_type": "learning_state",
            "content": "User does not understand ThreadPoolExecutor corePoolSize sizing.",
        }
    ]

    assert "corePoolSize" in retrieval_query
    assert result["resolution"].unresolved_references == []
    assert select_relevant_memories("this setting is too large", memories, min_score=0.01) == []
    assert select_relevant_memories(retrieval_query, memories, min_score=0.01) == memories


def test_ambiguous_reference_falls_back_to_original_query(monkeypatch):
    from app.modules.agent import service

    monkeypatch.setattr(service, "get_settings", _settings)
    original = "\u90a3\u8fd9\u4e2a\u5462\uff1f"
    result, retrieval_query = service._resolve_retrieval_query(
        original,
        retrieval_state=None,
        recent_messages=[
            {"role": "user", "content": "Explain corePoolSize."},
            {"role": "assistant", "content": "Also consider maximumPoolSize."},
        ],
        conversation_summary=None,
    )

    assert retrieval_query == original
    assert result["trace"]["query_resolution_fallback"] is True
    assert result["resolution"].unresolved_references


def test_prepare_context_resolves_once_and_shares_query_with_memory_lookup(monkeypatch):
    """The request path must not re-run resolution for its first retrieval."""
    from app.modules.agent import service

    cursor = object()

    @contextmanager
    def fake_cursor():
        yield cursor

    request = AgentChatRequest(
        message="\u90a3\u8fd9\u4e2a\u8bbe\u7f6e\u592a\u5927\u4f1a\u600e\u4e48\u6837\uff1f",
        course_id=7,
        session_id=11,
    )
    saved_messages: list[tuple] = []
    resolver_calls: list[str] = []
    memory_queries: list[str] = []
    original_resolver = service.resolve_course_query
    original_selector = service.select_relevant_memories

    def spy_resolver(*args, **kwargs):
        resolver_calls.append(args[0])
        return original_resolver(*args, **kwargs)

    def spy_selector(query, memories):
        memory_queries.append(query)
        return original_selector(query, memories)

    monkeypatch.setattr(service, "get_cursor", fake_cursor)
    monkeypatch.setattr(service, "get_settings", _settings)
    monkeypatch.setattr(service, "get_user_server_time", lambda _user_id: "now")
    monkeypatch.setattr(service.repository, "get_session", lambda *_args: {"id": 11, "course_id": 7})
    monkeypatch.setattr(service.course_repository, "get_course", lambda *_args: {"id": 7, "name": "Java"})
    monkeypatch.setattr(
        service.repository,
        "ensure_course_agent",
        lambda *_args: {"id": 9, "primary_session": {"id": 11, "course_id": 7}},
    )
    monkeypatch.setattr(
        service.repository,
        "list_course_memories",
        lambda *_args: [{"memory_key": "pool", "memory_type": "learning_state", "content": "corePoolSize sizing"}],
    )
    monkeypatch.setattr(
        service.repository,
        "claim_agent_run",
        lambda *_args, **_kwargs: ({"id": 99, "request_id": "request-99"}, True),
    )
    monkeypatch.setattr(service.repository, "set_agent_run_user_message", lambda *_args: None)
    monkeypatch.setattr(service.repository, "add_message", lambda *_args, **_kwargs: saved_messages.append(_args) or {"id": 100})
    monkeypatch.setattr(service.repository, "update_session_title_if_default", lambda *_args: None)
    monkeypatch.setattr(service.repository, "load_profile", lambda *_args: None)
    monkeypatch.setattr(service.repository, "get_memory_settings", lambda *_args: {})
    monkeypatch.setattr(service.repository, "get_user_learning_profile", lambda *_args: None)
    monkeypatch.setattr(service.learning_repository, "list_points_with_mastery", lambda *_args: [])
    monkeypatch.setattr(service.repository, "list_session_messages_for_context", lambda *_args, **_kwargs: [{"id": 100, "role": "user", "content": request.message}])
    monkeypatch.setattr(service.repository, "list_active_conversation_summary_blocks", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service.repository, "get_session_context_state", lambda *_args, **_kwargs: {"covered_until_message_id": None})
    retrieval_context_calls: list[dict] = []
    monkeypatch.setattr(
        service.repository,
        "get_session_retrieval_context",
        lambda *_args, **kwargs: retrieval_context_calls.append(kwargs) or {"last_focus_topic": "corePoolSize"},
    )
    monkeypatch.setattr(service.repository, "touch_course_agent", lambda *_args: None)
    monkeypatch.setattr(service, "resolve_course_query", spy_resolver)
    monkeypatch.setattr(service, "select_relevant_memories", spy_selector)
    monkeypatch.setattr(service, "build_agent_context", lambda **_kwargs: ("context", {}))

    context = service._prepare_context(1, request, "native_tool_agent", "mixed")

    assert resolver_calls == [request.message]
    assert "corePoolSize" in context["retrieval_query"]
    assert memory_queries == [context["retrieval_query"]]
    assert saved_messages[0][5] == request.message
    assert retrieval_context_calls == [{"user_id": 1, "course_id": 7, "session_id": 11}]
    assert context["context_report"]["query_resolution"]["retrieval_query"] == context["retrieval_query"]


def test_fast_rag_reuses_prepared_retrieval_query_without_resolving_again(monkeypatch):
    from app.modules.agent import service

    request = AgentChatRequest(message="\u90a3\u8fd9\u4e2a\u8bbe\u7f6e\u592a\u5927\u4f1a\u600e\u4e48\u6837\uff1f")
    resolution = resolve_course_query(request.message, retrieval_state={"last_focus_topic": "corePoolSize"})
    context = {
        "course": {"id": 7, "name": "Java"}, "session": {"id": 11}, "run": {"id": 99},
        "profile": None, "mastery": [], "recent_messages": [], "server_time": "now", "agent": None,
        "web_search_mode": "auto", "query_resolution": resolution, "retrieval_query": resolution.resolved_query,
        "context_report": {"query_resolution": {"query_resolution_fallback": False}},
    }
    prepared_queries: list[str] = []
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            fast_rag_enabled=True, fast_rag_confidence_threshold=0.85, fast_rag_max_anchors=2,
            fast_rag_neighbor_window=1, fast_rag_min_retrieval_score=0.1,
        ),
    )
    monkeypatch.setattr(service, "resolve_course_query", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not resolve twice")))
    monkeypatch.setattr(
        service,
        "prepare_fast_rag",
        lambda **kwargs: prepared_queries.append(kwargs["resolved_query"]) or FastRagPrepared(
            citations=[], anchor_chunk_ids=[], evidence={"evidence_blocks": [{"evidence_text": "evidence"}]},
            retrieval_ms=1, evidence_ms=1,
        ),
    )
    monkeypatch.setattr(service, "generate_agent_reply", lambda *_args, **_kwargs: "answer")
    monkeypatch.setattr(service, "_persist_assistant", lambda *_args, **_kwargs: {"id": 101, "content": "answer"})
    monkeypatch.setattr(service, "_persist_retrieval_state", lambda *_args, **_kwargs: None)

    result = service._fast_rag_reply(1, request, context)

    assert result is not None
    assert prepared_queries == [context["retrieval_query"]]


def test_native_agentic_initial_message_reuses_prepared_retrieval_query(monkeypatch):
    from langchain_core.messages import AIMessage

    from app.modules.agent import service

    request = AgentChatRequest(message="\u90a3\u8fd9\u4e2a\u8bbe\u7f6e\u592a\u5927\u4f1a\u600e\u4e48\u6837\uff1f")
    resolution = resolve_course_query(request.message, retrieval_state={"last_focus_topic": "corePoolSize"})
    context = {
        "course": {"id": 7, "name": "Java"}, "session": {"id": 11},
        "run": {"id": 99, "request_id": "request-99"}, "profile": None, "mastery": [],
        "recent_messages": [], "server_time": "now", "agent": None, "retrieval_query": resolution.resolved_query,
        "query_resolution": resolution, "context_report": {}, "web_search_mode": "auto",
    }
    invocations: list[dict] = []

    class FakeAgent:
        def invoke(self, payload, *, config):
            invocations.append(payload)
            return {"messages": [AIMessage(content="answer")]}

    monkeypatch.setattr(service, "_prepare_context", lambda *_args: context)
    monkeypatch.setattr(service, "_fast_rag_reply", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_build_native_agent", lambda *_args: (FakeAgent(), SimpleNamespace(citations=[], cards=[], resources=[], actions=[])))
    monkeypatch.setattr(service, "_persist_assistant", lambda *_args, **_kwargs: {"id": 101, "content": "answer"})
    monkeypatch.setattr(service, "get_mysql_checkpointer", lambda: SimpleNamespace(delete_thread=lambda *_args: None))

    result = service.run_native_tool_agent_chat(1, request)

    assert result["reply"] == "answer"
    assert invocations == [{"messages": [("user", context["retrieval_query"])]}]
