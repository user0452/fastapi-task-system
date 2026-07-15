import hashlib
import hmac
from datetime import datetime, timezone

import bcrypt
from fastapi import Depends, Request, Response, status
from pymysql.err import IntegrityError

from app.core.config import get_settings
from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.responses import ApiResponse, V1APIRouter, success
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthCredentials, AuthUser
from app.modules.auth.tokens import COOKIE_NAME, create_access_token

router = V1APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_HASH = bcrypt.hashpw(b"not-the-user-password", bcrypt.gensalt()).decode("utf-8")


def _privacy_hash(value: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, value.casefold().encode("utf-8"), hashlib.sha256).hexdigest()


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.access_token_expire_hours * 3600,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AuthUser],
)
def register(credentials: AuthCredentials):
    password_hash = bcrypt.hashpw(
        credentials.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password, is_active) VALUES (%s, %s, TRUE)",
                (credentials.username, password_hash),
            )
            user_id = cursor.lastrowid
    except IntegrityError:
        raise AppError("无法注册该用户名", 409, "USERNAME_UNAVAILABLE") from None
    return success(
        {"id": user_id, "username": credentials.username},
        "注册成功",
        code=201,
    )


@router.post("/login", response_model=ApiResponse[AuthUser])
def login(credentials: AuthCredentials, request: Request, response: Response):
    settings = get_settings()
    identifier_hash = _privacy_hash(credentials.username)
    ip_hash = _privacy_hash(request.client.host if request.client else "unknown")
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT
                SUM(identifier_hash = %s) AS identifier_attempts,
                SUM(ip_hash = %s) AS ip_attempts
            FROM auth_login_events
            WHERE created_at >= DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 10 MINUTE)
            """,
            (identifier_hash, ip_hash),
        )
        attempts = cursor.fetchone()
        if settings.auth_rate_limit_enabled and (
            int(attempts.get("identifier_attempts") or 0) >= 8
            or int(attempts.get("ip_attempts") or 0) >= 30
        ):
            raise AppError("登录尝试过于频繁，请稍后再试", 429, "AUTH_RATE_LIMITED")
        cursor.execute(
            """
            SELECT id, username, password, is_active, token_version
            FROM users WHERE username = %s
            """,
            (credentials.username,),
        )
        user = cursor.fetchone()

    stored_hash = user["password"] if user else _DUMMY_HASH
    password_ok = bcrypt.checkpw(
        credentials.password.encode("utf-8"), stored_hash.encode("utf-8")
    )
    succeeded = bool(user and password_ok and user.get("is_active"))
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO auth_login_events
                (identifier_hash, ip_hash, succeeded)
            VALUES (%s, %s, %s)
            """,
            (identifier_hash, ip_hash, succeeded),
        )
        if succeeded:
            cursor.execute(
                "UPDATE users SET last_login_at = %s WHERE id = %s",
                (datetime.now(timezone.utc).replace(tzinfo=None), user["id"]),
            )
    if not succeeded:
        raise AppError("用户名或密码错误", 401, "INVALID_CREDENTIALS")
    _set_cookie(response, create_access_token(user))
    return success({"id": user["id"], "username": user["username"]}, "登录成功")


@router.post("/logout", response_model=ApiResponse[None])
def logout(response: Response, user=Depends(get_current_user)):
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE users SET token_version = token_version + 1 WHERE id = %s",
            (user["id"],),
        )
    response.delete_cookie(COOKIE_NAME, path="/")
    return success(message="已退出登录")


@router.get("/me", response_model=ApiResponse[AuthUser])
def me(user=Depends(get_current_user)):
    return success(user)


__all__ = ["router"]
