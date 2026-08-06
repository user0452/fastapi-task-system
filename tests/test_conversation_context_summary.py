from __future__ import annotations

import json
from types import SimpleNamespace

from app.modules.agent import context_manager


def _settings(*, budget=10_000, minimum=3, target=5):
    return SimpleNamespace(
        agent_context_budget_tokens=budget,
        agent_min_recent_rounds=minimum,
        agent_target_recent_rounds=target,
        conversation_summary_max_tokens=3_000,
        memory_relevance_threshold=0.2,
    )


def _messages(round_count: int, *, content_size=20):
    rows = []
    for number in range(round_count):
        rows.extend([
            {"id": number * 2 + 1, "role": "user", "content": f"u{number}-" + "x" * content_size},
            {"id": number * 2 + 2, "role": "assistant", "content": f"a{number}-" + "y" * content_size},
        ])
    return rows


def _build(monkeypatch, messages, **kwargs):
    monkeypatch.setattr(context_manager, "get_settings", lambda: _settings(**kwargs.pop("settings", {})))
    prompt, report = context_manager.build_agent_context(
        course={"id": 1, "name": "课程"}, profile=None, mastery=[], memories=[], messages=messages,
        summary_blocks=kwargs.pop("summary_blocks", []), covered_until_message_id=kwargs.pop("covered_until", None),
    )
    return json.loads(prompt), report


def test_recent_three_complete_rounds_are_hard_preserved_under_budget(monkeypatch):
    layers, report = _build(monkeypatch, _messages(6, content_size=4_000), settings={"budget": 2_000})
    assert [item["id"] for item in layers["recent_rounds"]][-6:] == [7, 8, 9, 10, 11, 12]
    assert report["recent_round_count"] == 3
    assert report["budget_tokens"] == 2_000


def test_budget_allows_expansion_to_five_complete_rounds(monkeypatch):
    layers, report = _build(monkeypatch, _messages(6))
    assert [item["id"] for item in layers["recent_rounds"]] == list(range(3, 13))
    assert report["recent_round_count"] == 5


def test_context_never_emits_half_complete_round(monkeypatch):
    messages = _messages(4) + [{"id": 9, "role": "user", "content": "still waiting"}]
    layers, _ = _build(monkeypatch, messages)
    recent_ids = [item["id"] for item in layers["recent_rounds"]]
    assert len(recent_ids) % 2 == 0
    assert layers["pending_original_messages"][-1]["id"] == 9


def test_completed_summary_keeps_overlapping_recent_raw_rounds(monkeypatch):
    blocks = [{"id": 1, "start_message_id": 1, "end_message_id": 8, "summary_text": "早期 TCP 讨论", "level": 0}]
    layers, report = _build(monkeypatch, _messages(5), summary_blocks=blocks, covered_until=8)
    assert layers["summary_blocks"][0]["id"] == 1
    assert {7, 8, 9, 10}.issubset({item["id"] for item in layers["recent_rounds"]})
    assert report["covered_until_message_id"] == 8


def test_uncovered_old_rounds_remain_pending_until_async_summary_succeeds(monkeypatch):
    layers, report = _build(monkeypatch, _messages(10), covered_until=0)
    pending_ids = {item["id"] for item in layers["pending_original_messages"]}
    assert {1, 2, 3, 4}.issubset(pending_ids)
    assert report["pending_message_count"] >= 10


def test_default_context_budget_is_ten_thousand_tokens():
    assert context_manager.get_settings().agent_context_budget_tokens == 10_000
