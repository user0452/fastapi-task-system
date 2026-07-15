from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_cursor
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
