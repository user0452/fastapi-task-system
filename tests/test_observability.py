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
