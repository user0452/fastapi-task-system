from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import get_settings

COOKIE_NAME = "a3_access_token"


def create_access_token(user: dict) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "ver": int(user.get("token_version") or 0),
        "iat": now,
        "exp": now + timedelta(hours=settings.access_token_expire_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


__all__ = ["COOKIE_NAME", "create_access_token"]
