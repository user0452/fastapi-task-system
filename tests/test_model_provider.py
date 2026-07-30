from types import SimpleNamespace

from app.integrations.llm import model_provider
from app.integrations.llm.endpoint_security import ValidatedLlmEndpoint


def test_get_llm_prefers_enabled_user_openai_compatible_config(monkeypatch):
    custom = {
        "api_key": "sk-user-test",
        "base_url": "https://gateway.example/v1",
        "model": "gateway-chat",
    }
    sentinel = object()
    captured = {}

    monkeypatch.setattr(
        model_provider,
        "get_settings",
        lambda: SimpleNamespace(
            mock_llm=False,
            deepseek_api_key="server-key",
            deepseek_base_url="https://server.example/v1",
            deepseek_model="server-model",
            llm_timeout_seconds=30,
            llm_max_retries=2,
        ),
    )
    monkeypatch.setattr(
        model_provider,
        "get_enabled_user_llm_config",
        lambda user_id: custom if user_id == 42 else None,
    )

    def fake_build(**config):
        captured.update(config)
        return sentinel

    monkeypatch.setattr(model_provider, "build_openai_compatible_model", fake_build)

    assert model_provider.get_llm(42) is sentinel
    assert captured == custom


def test_user_model_uses_revalidated_pinned_http_clients(monkeypatch):
    endpoint = ValidatedLlmEndpoint(
        base_url="https://gateway.example/v1",
        hostname="gateway.example",
        port=443,
        addresses=("8.8.8.8",),
    )
    sync_client = object()
    async_client = object()
    sentinel = object()
    captured = {}

    monkeypatch.setattr(
        model_provider,
        "get_settings",
        lambda: SimpleNamespace(llm_timeout_seconds=12, llm_max_retries=1),
    )
    monkeypatch.setattr(
        model_provider,
        "validate_user_llm_endpoint",
        lambda value: endpoint if value == "https://gateway.example/v1/" else None,
    )
    monkeypatch.setattr(
        model_provider,
        "create_pinned_http_client",
        lambda resolved, *, timeout: sync_client
        if resolved is endpoint and timeout == 12
        else None,
    )
    monkeypatch.setattr(
        model_provider,
        "create_pinned_async_http_client",
        lambda resolved, *, timeout: async_client
        if resolved is endpoint and timeout == 12
        else None,
    )

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(model_provider, "ChatOpenAI", fake_chat_openai)

    result = model_provider.build_openai_compatible_model(
        api_key="sk-user-test",
        base_url="https://gateway.example/v1/",
        model="gateway-chat",
    )

    assert result is sentinel
    assert captured["base_url"] == endpoint.base_url
    assert captured["http_client"] is sync_client
    assert captured["http_async_client"] is async_client


def test_server_default_model_keeps_trusted_local_endpoint_compatibility(monkeypatch):
    sentinel = object()
    captured = {}

    monkeypatch.setattr(
        model_provider,
        "get_settings",
        lambda: SimpleNamespace(
            mock_llm=False,
            deepseek_api_key="server-key",
            deepseek_base_url="http://127.0.0.1:11434/v1",
            deepseek_model="local-model",
            llm_timeout_seconds=12,
            llm_max_retries=1,
        ),
    )
    monkeypatch.setattr(model_provider, "get_enabled_user_llm_config", lambda _user_id: None)

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(model_provider, "ChatOpenAI", fake_chat_openai)

    assert model_provider.get_llm() is sentinel
    assert captured["base_url"] == "http://127.0.0.1:11434/v1"
    assert captured["http_client"] is None
    assert captured["http_async_client"] is None
