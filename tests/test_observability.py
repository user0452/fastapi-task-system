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


def test_production_disables_legacy_routes_by_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ENABLE_LEGACY_ROUTES", raising=False)
    settings = Settings.from_env()
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)

    production_app = app_main.create_app()
    paths = {route.path for route in production_app.routes}

    assert settings.enable_legacy_routes is False
    assert "/tasks" not in paths
    assert "/api/v1/courses" in paths
    assert "/api/v1/auth/login" in paths


def test_production_explicitly_disabled_legacy_routes_stay_absent(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_LEGACY_ROUTES", "false")
    settings = Settings.from_env()
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)

    production_app = app_main.create_app()
    paths = {route.path for route in production_app.routes}

    assert settings.enable_legacy_routes is False
    assert "/tasks" not in paths
    assert "/api/v1/courses" in paths


def test_production_explicit_legacy_routes_fail_startup(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_LEGACY_ROUTES", "true")
    monkeypatch.setenv("SECRET_KEY", "production-secret-key-with-at-least-32-characters")
    settings = Settings.from_env()
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="生产环境禁止启用旧版路由"):
        settings.validate_startup()
    with pytest.raises(RuntimeError, match="生产环境禁止启用旧版路由"):
        app_main.create_app()


def test_development_legacy_routes_remain_configurable(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_LEGACY_ROUTES", "true")
    enabled = Settings.from_env()
    monkeypatch.setattr(app_main, "get_settings", lambda: enabled)
    enabled_paths = {route.path for route in app_main.create_app().routes}

    monkeypatch.setenv("ENABLE_LEGACY_ROUTES", "false")
    disabled = Settings.from_env()
    monkeypatch.setattr(app_main, "get_settings", lambda: disabled)
    disabled_paths = {route.path for route in app_main.create_app().routes}

    assert "/tasks" in enabled_paths
    assert "/tasks" not in disabled_paths
    assert "/api/v1/courses" in enabled_paths
    assert "/api/v1/courses" in disabled_paths
