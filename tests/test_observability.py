import pytest

from app import main as app_main
from app.core.config import Settings


def test_request_id_is_echoed_and_prometheus_metrics_are_exposed(api_client):
    response = api_client.get(
        "/health/live", headers={"X-Request-ID": "test-request-123"}
    )
    metrics = api_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"
    assert metrics.status_code == 200
    assert "a3_http_requests_total" in metrics.text
    assert "a3_http_request_duration_seconds" in metrics.text


def test_retired_legacy_routes_are_not_registered(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings.from_env()
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)

    production_app = app_main.create_app()
    paths = {route.path for route in production_app.routes}

    assert "/tasks" not in paths
    assert "/api/v1/agent" not in paths
    assert "/api/v1/roadmaps" not in paths
    assert "/api/v1/resources" not in paths
    assert "/api/v1/courses" in paths
    assert "/api/v1/auth/login" in paths


def test_production_alias_uses_fail_closed_security_defaults(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    settings = Settings.from_env()

    assert settings.environment == "production"


def test_unknown_environment_name_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "productionn")

    with pytest.raises(RuntimeError, match="APP_ENV 无效"):
        Settings.from_env()


def test_security_boolean_typo_is_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "tru")

    with pytest.raises(RuntimeError, match="AUTH_RATE_LIMIT_ENABLED"):
        Settings.from_env()
