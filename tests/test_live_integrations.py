from types import SimpleNamespace

import numpy as np
import pytest

from scripts import verify_live_integrations as canary


def test_embedding_canary_accepts_distinct_normalized_vectors(monkeypatch):
    monkeypatch.setattr(canary, "USE_MOCK_EMBEDDING", False)

    result = canary.check_embedding(
        lambda _texts: np.asarray([[1.0, *([0.0] * 127)], [0.0, 1.0, *([0.0] * 126)]])
    )

    assert result["passed"] is True
    assert result["dimensions"] == 128


def test_embedding_canary_rejects_mock_mode(monkeypatch):
    monkeypatch.setattr(canary, "USE_MOCK_EMBEDDING", True)

    with pytest.raises(RuntimeError, match="A3_MOCK_EMBEDDING"):
        canary.check_embedding()


def test_llm_canary_requires_non_empty_response(monkeypatch):
    monkeypatch.setattr(
        canary,
        "get_settings",
        lambda: SimpleNamespace(mock_llm=False, deepseek_model="test"),
    )
    model = SimpleNamespace(invoke=lambda _messages: SimpleNamespace(content=""))

    with pytest.raises(RuntimeError, match="empty response"):
        canary.check_llm(lambda: model)


def test_llm_canary_returns_only_safe_metadata(monkeypatch):
    monkeypatch.setattr(
        canary,
        "get_settings",
        lambda: SimpleNamespace(mock_llm=False, deepseek_model="safe-model"),
    )
    model = SimpleNamespace(invoke=lambda _messages: SimpleNamespace(content="A3_CANARY_OK"))

    result = canary.check_llm(lambda: model)

    assert result["passed"] is True
    assert result["model"] == "safe-model"
    assert "content" not in result
