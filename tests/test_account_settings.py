from datetime import datetime, timezone

from app.core.database import get_cursor
from app.core.secret_crypto import decrypt_secret
from app.modules.account.llm_config_service import get_user_llm_config
from app.modules.account.service import (
    get_user_local_date,
    update_user_timezone,
)
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course


def test_account_timezone_can_be_read_and_updated(api_client, two_users):
    user, _ = two_users

    current = api_client.get("/api/v1/account/settings")
    assert current.status_code == 200
    assert current.json()["data"]["timezone"] == "Asia/Shanghai"

    invalid = api_client.patch(
        "/api/v1/account/settings",
        json={"timezone": "Mars/Olympus"},
    )
    assert invalid.status_code == 422

    updated = api_client.patch(
        "/api/v1/account/settings",
        json={"timezone": "America/Los_Angeles"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["timezone"] == "America/Los_Angeles"

    with get_cursor() as cursor:
        cursor.execute("SELECT timezone FROM users WHERE id = %s", (user["id"],))
        assert cursor.fetchone()["timezone"] == "America/Los_Angeles"


def test_user_local_date_uses_iana_timezone(two_users):
    user, _ = two_users
    instant = datetime(2026, 7, 16, 16, 30, tzinfo=timezone.utc)

    update_user_timezone(user["id"], "Asia/Shanghai")
    assert get_user_local_date(user["id"], instant).isoformat() == "2026-07-17"

    update_user_timezone(user["id"], "America/Los_Angeles")
    assert get_user_local_date(user["id"], instant).isoformat() == "2026-07-16"


def test_naive_exam_time_is_stored_as_utc(two_users):
    user, _ = two_users
    update_user_timezone(user["id"], "America/Los_Angeles")

    course = create_user_course(
        user["id"],
        CourseCreate(
            name="UTC 考试课程",
            exam_at=datetime(2026, 7, 20, 0, 30),
        ),
    )

    assert course["exam_at"] == datetime(2026, 7, 20, 7, 30)


def test_database_sessions_are_utc():
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT @@session.time_zone AS timezone_name,
                   TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW()) AS utc_delta
            """
        )
        row = cursor.fetchone()

    assert row["timezone_name"] == "+00:00"
    assert abs(int(row["utc_delta"])) <= 1


def test_user_llm_config_is_encrypted_masked_and_user_scoped(
    api_client,
    two_users,
    monkeypatch,
):
    user, other_user = two_users
    secret = "sk-user-owned-secret-1234"
    monkeypatch.setattr(
        "app.integrations.llm.endpoint_security._resolve_public_addresses",
        lambda _hostname, _port: ("8.8.8.8",),
    )

    initial = api_client.get("/api/v1/account/llm-config")
    assert initial.status_code == 200
    assert initial.json()["data"]["configured"] is False

    saved = api_client.put(
        "/api/v1/account/llm-config",
        json={
            "enabled": True,
            "base_url": "https://example.ai/v1/",
            "model": "example-chat",
            "api_key": secret,
        },
    )
    assert saved.status_code == 200
    payload = saved.json()["data"]
    assert payload["enabled"] is True
    assert payload["base_url"] == "https://example.ai/v1"
    assert payload["api_key_hint"] == "••••1234"
    assert "api_key" not in payload

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT api_key_ciphertext FROM user_llm_configs WHERE user_id = %s",
            (user["id"],),
        )
        ciphertext = cursor.fetchone()["api_key_ciphertext"]
    assert secret not in ciphertext
    assert decrypt_secret(ciphertext) == secret

    retained = api_client.put(
        "/api/v1/account/llm-config",
        json={
            "enabled": False,
            "base_url": "https://example.ai/v1",
            "model": "example-chat-v2",
        },
    )
    assert retained.status_code == 200
    assert retained.json()["data"]["has_api_key"] is True
    assert retained.json()["data"]["active_source"] == "server_default"

    rejected = api_client.put(
        "/api/v1/account/llm-config",
        json={
            "enabled": True,
            "base_url": "https://attacker.example/v1",
            "model": "stolen-key-model",
        },
    )
    assert rejected.status_code == 422
    assert (
        rejected.json()["error_code"]
        == "LLM_API_KEY_REQUIRED_FOR_ENDPOINT_CHANGE"
    )
    assert get_user_llm_config(user["id"])["base_url"] == "https://example.ai/v1"
    assert get_user_llm_config(other_user["id"])["configured"] is False


def test_user_llm_config_connection_uses_candidate_without_exposing_key(
    api_client,
    two_users,
    monkeypatch,
):
    _user, _other_user = two_users
    secret = "sk-connection-secret-9876"
    monkeypatch.setattr(
        "app.integrations.llm.endpoint_security._resolve_public_addresses",
        lambda _hostname, _port: ("8.8.8.8",),
    )
    saved = api_client.put(
        "/api/v1/account/llm-config",
        json={
            "enabled": True,
            "base_url": "https://gateway.example/v1",
            "model": "gateway-chat",
            "api_key": secret,
        },
    )
    assert saved.status_code == 200

    captured = {}

    def fake_probe(config):
        captured.update(config)
        return {"ok": True, "model": config["model"], "latency_ms": 12}

    monkeypatch.setattr(
        "app.modules.account.llm_config_service._probe_openai_compatible",
        fake_probe,
    )
    response = api_client.post(
        "/api/v1/account/llm-config/test",
        json={
            "base_url": "https://gateway.example/v1",
            "model": "gateway-chat",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"ok": True, "model": "gateway-chat", "latency_ms": 12}
    assert captured["api_key"] == secret
    assert secret not in response.text

    captured.clear()
    rejected = api_client.post(
        "/api/v1/account/llm-config/test",
        json={
            "base_url": "https://attacker.example/v1",
            "model": "gateway-chat",
        },
    )
    assert rejected.status_code == 422
    assert (
        rejected.json()["error_code"]
        == "LLM_API_KEY_REQUIRED_FOR_ENDPOINT_CHANGE"
    )
    assert captured == {}


def test_user_llm_config_rejects_non_http_endpoint(api_client):
    response = api_client.put(
        "/api/v1/account/llm-config",
        json={
            "enabled": True,
            "base_url": "file:///etc/passwd",
            "model": "unsafe-model",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 422
