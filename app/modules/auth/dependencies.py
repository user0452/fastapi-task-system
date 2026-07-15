from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.database import get_cursor
from app.core.errors import AppError
from app.modules.auth.tokens import COOKIE_NAME

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    token = credentials.credentials if credentials else request.cookies.get(COOKIE_NAME)
    if not token:
        raise AppError("登录状态无效，请重新登录", 401, "AUTH_REQUIRED")
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = int(payload.get("sub") or payload.get("id"))
        token_version = int(payload.get("ver") or 0)
    except (JWTError, TypeError, ValueError):
        raise AppError("登录状态无效，请重新登录", 401, "AUTH_INVALID") from None
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, username, is_active, token_version
            FROM users WHERE id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()
    if (
        user is None
        or not bool(user.get("is_active"))
        or int(user.get("token_version") or 0) != token_version
    ):
        raise AppError("登录状态无效，请重新登录", 401, "AUTH_REVOKED")
    return {"id": user["id"], "username": user["username"]}


__all__ = ["get_current_user"]
