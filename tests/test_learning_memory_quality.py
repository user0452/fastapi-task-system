from types import SimpleNamespace

import numpy as np

from app.integrations.embedding.service import serialize_embedding
from app.jobs import learning_memory_job
from app.modules.agent.context_manager import select_relevant_memories


def test_memory_selection_drops_candidates_below_relevance_threshold():
    memories = [
        {
            "id": 1,
            "content": {"text": "讲代码时先说明整体流程"},
            "embedding_json": serialize_embedding(np.asarray([1.0, 0.0], dtype="float32")),
            "updated_at": "2026-08-06T00:00:00",
        },
        {
            "id": 2,
            "content": {"text": "准备计算机网络考试"},
            "embedding_json": serialize_embedding(np.asarray([0.0, 1.0], dtype="float32")),
            "updated_at": "2026-08-06T00:00:01",
        },
    ]

    selected = select_relevant_memories(
        "继续讲代码整体流程",
        memories,
        min_score=0.20,
        embedding_provider=lambda _texts: np.asarray([[1.0, 0.0]], dtype="float32"),
    )

    assert [item["id"] for item in selected] == [1]


def test_memory_selection_uses_lexical_fallback_without_forcing_top_k():
    memories = [
        {"id": 1, "content": {"text": "代码讲解先说整体流程"}},
        {"id": 2, "content": {"text": "目标是通过计算机网络考试"}},
    ]

    selected = select_relevant_memories(
        "代码整体流程怎么走",
        memories,
        min_score=0.20,
        embedding_provider=lambda _texts: np.empty((0, 0), dtype="float32"),
    )

    assert [item["id"] for item in selected] == [1]
    assert select_relevant_memories(
        "今天天气怎么样",
        memories,
        min_score=0.20,
        embedding_provider=lambda _texts: np.empty((0, 0), dtype="float32"),
    ) == []


def test_llm_memory_extraction_returns_structured_durable_candidates(monkeypatch):
    monkeypatch.setattr(
        learning_memory_job,
        "_settings",
        lambda: SimpleNamespace(mock_llm=False),
    )
    monkeypatch.setattr(learning_memory_job, "get_llm", lambda _user_id: object())

    def structured_provider(_messages, schema, *, model):
        assert model is not None
        return schema.model_validate(
            {
                "candidates": [
                    {
                        "memory_type": "course_preference",
                        "text": "  用户偏好先了解代码整体流程，再分析细节  ",
                        "confidence": 0.95,
                        "evidence_kind": "explicit_user_statement",
                    },
                    {
                        "memory_type": "weak_point",
                        "text": "用户容易混淆三次握手和四次挥手",
                        "confidence": 0.90,
                        "evidence_kind": "turn_observation",
                    },
                ]
            }
        )

    candidates = learning_memory_job._extract_candidates(
        {"content": "以后讲代码先说整体流程。我总弄混三次握手和四次挥手。"},
        {"content": "本轮已对两者进行了区分。"},
        {"id": 7, "name": "计算机网络", "goal": "掌握核心协议"},
        user_id=3,
        max_candidates=2,
        structured_provider=structured_provider,
    )

    assert candidates == [
        {
            "memory_type": "course_preference",
            "text": "用户偏好先了解代码整体流程，再分析细节",
            "confidence": 0.95,
            "evidence_kind": "explicit_user_statement",
        },
        {
            "memory_type": "weak_point",
            "text": "用户容易混淆三次握手和四次挥手",
            "confidence": 0.90,
            "evidence_kind": "turn_observation",
        },
    ]


def test_llm_memory_extraction_falls_back_to_conservative_rules(monkeypatch):
    monkeypatch.setattr(
        learning_memory_job,
        "_settings",
        lambda: SimpleNamespace(mock_llm=False),
    )
    monkeypatch.setattr(learning_memory_job, "get_llm", lambda _user_id: object())

    def failing_provider(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    candidates = learning_memory_job._extract_candidates(
        {"content": "我喜欢先看整体流程，再看逐行代码。"},
        {"content": "收到。"},
        {"id": 8, "name": "Python", "goal": "学习后端"},
        user_id=4,
        max_candidates=2,
        structured_provider=failing_provider,
    )

    assert candidates[0]["memory_type"] == "course_preference"
    assert candidates[0]["evidence_kind"] == "explicit_user_statement"
