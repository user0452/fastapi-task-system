from types import SimpleNamespace

from app.integrations.llm import model_provider


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
