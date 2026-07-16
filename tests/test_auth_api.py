from types import SimpleNamespace
from uuid import uuid4

import bcrypt
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.database import get_cursor
from app.modules.auth import client_ip
from app.modules.auth.client_ip import get_client_ip
from app.modules.auth.router import _privacy_hash
from app.modules.auth.tokens import COOKIE_NAME
from main import app


def test_cookie_authentication_and_logout_revocation():
    username = f"auth_{uuid4().hex[:16]}"
    password = "correct-password-0"
    app.dependency_overrides.clear()

    try:
        with TestClient(app) as client:
            registered = client.post(
                "/api/v1/auth/register",
                json={"username": username, "password": password},
            )
            assert registered.status_code == 201
            assert registered.json()["code"] == 201

            logged_in = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            assert logged_in.status_code == 200
            assert "token" not in logged_in.json()
            assert COOKIE_NAME in client.cookies
            assert "HttpOnly" in logged_in.headers["set-cookie"]

            old_token = client.cookies.get(COOKIE_NAME)
            current = client.get("/api/v1/auth/me")
            assert current.status_code == 200
            assert current.json()["data"]["username"] == username

            logged_out = client.post("/api/v1/auth/logout")
            assert logged_out.status_code == 200
            assert COOKIE_NAME not in client.cookies

            client.cookies.set(COOKIE_NAME, old_token)
            revoked = client.get("/api/v1/auth/me")
            assert revoked.status_code == 401
            assert revoked.json()["error_code"] == "AUTH_REVOKED"
    finally:
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM auth_login_events WHERE identifier_hash = %s",
                (_privacy_hash(username),),
            )
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))


def test_login_does_not_reveal_whether_username_exists():
    username = f"auth_{uuid4().hex[:16]}"
    missing_username = f"missing_{uuid4().hex[:16]}"
    password = "correct-password-0"
    app.dependency_overrides.clear()

    try:
        with TestClient(app) as client:
            client.post(
                "/api/v1/auth/register",
                json={"username": username, "password": password},
            )
            wrong_password = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": "incorrect-password"},
            )
            missing_user = client.post(
                "/api/v1/auth/login",
                json={"username": missing_username, "password": "incorrect-password"},
            )

            assert wrong_password.status_code == missing_user.status_code == 401
            assert wrong_password.json()["message"] == missing_user.json()["message"]
            assert wrong_password.json()["error_code"] == "INVALID_CREDENTIALS"
            assert missing_user.json()["error_code"] == "INVALID_CREDENTIALS"
    finally:
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM auth_login_events WHERE identifier_hash IN (%s, %s)",
                (_privacy_hash(username), _privacy_hash(missing_username)),
            )
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))


def test_argon2id_distinguishes_passwords_beyond_bcrypt_limit():
    username = f"argon_{uuid4().hex[:16]}"
    correct_password = "a" * 72 + "甲"
    different_suffix = "a" * 72 + "乙"
    app.dependency_overrides.clear()

    try:
        with TestClient(app) as client:
            registered = client.post(
                "/api/v1/auth/register",
                json={"username": username, "password": correct_password},
            )
            assert registered.status_code == 201

            wrong = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": different_suffix},
            )
            assert wrong.status_code == 401

            logged_in = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": correct_password},
            )
            assert logged_in.status_code == 200

        with get_cursor() as cursor:
            cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
            assert cursor.fetchone()["password"].startswith("$argon2id$")
    finally:
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM auth_login_events WHERE identifier_hash = %s",
                (_privacy_hash(username),),
            )
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))


def test_legacy_bcrypt_hash_is_replaced_after_successful_login():
    username = f"bcrypt_{uuid4().hex[:16]}"
    password = "legacy-password-0"
    legacy_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    app.dependency_overrides.clear()

    try:
        with get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s)",
                (username, legacy_hash),
            )
        with TestClient(app) as client:
            logged_in = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            assert logged_in.status_code == 200
        with get_cursor() as cursor:
            cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
            assert cursor.fetchone()["password"].startswith("$argon2id$")
    finally:
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM auth_login_events WHERE identifier_hash = %s",
                (_privacy_hash(username),),
            )
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))


def test_login_rate_limit_counts_failures_not_successes():
    username = f"rate_{uuid4().hex[:16]}"
    password = "correct-password-0"
    identifier_hash = _privacy_hash(username)
    ip_hash = _privacy_hash("testclient")
    app.dependency_overrides.clear()

    try:
        with TestClient(app) as client:
            assert client.post(
                "/api/v1/auth/register",
                json={"username": username, "password": password},
            ).status_code == 201
            with get_cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO auth_login_events (identifier_hash, ip_hash, succeeded)
                    VALUES (%s, %s, TRUE)
                    """,
                    [(identifier_hash, ip_hash)] * 8,
                )
            assert client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            ).status_code == 200

            with get_cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO auth_login_events (identifier_hash, ip_hash, succeeded)
                    VALUES (%s, %s, FALSE)
                    """,
                    [(identifier_hash, ip_hash)] * 8,
                )
            limited = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            assert limited.status_code == 429
            assert limited.json()["error_code"] == "AUTH_RATE_LIMITED"
    finally:
        with get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM auth_login_events WHERE identifier_hash = %s",
                (identifier_hash,),
            )
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))


def _request(client_host: str, forwarded_for: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", forwarded_for.encode())],
            "client": (client_host, 1234),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_client_ip_uses_forwarded_chain_only_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(
        client_ip,
        "get_settings",
        lambda: SimpleNamespace(trusted_proxy_cidrs=("10.0.0.0/8",)),
    )

    spoofed = _request("203.0.113.9", "198.51.100.2")
    proxied = _request("10.0.0.2", "198.51.100.4, 10.0.0.3")
    prepended_spoof = _request("10.0.0.2", "192.0.2.8, 198.51.100.4")

    assert get_client_ip(spoofed) == "203.0.113.9"
    assert get_client_ip(proxied) == "198.51.100.4"
    assert get_client_ip(prepended_spoof) == "198.51.100.4"
