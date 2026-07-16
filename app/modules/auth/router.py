import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Request, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.responses import ApiResponse, V1APIRouter, success
from app.models import model_as_dict, reflected_model
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
    User = reflected_model("users")
    try:
        with get_cursor() as cursor:
            user = User(username=credentials.username, password=password_hash, is_active=True)
            cursor.session.add(user)
            cursor.session.flush()
            user_id = user.id
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
    User = reflected_model("users")
    LoginEvent = reflected_model("auth_login_events")
    with get_cursor() as cursor:
        attempts = cursor.session.execute(
            select(
                func.coalesce(func.sum(case((LoginEvent.identifier_hash == identifier_hash, 1), else_=0)), 0),
                func.coalesce(func.sum(case((LoginEvent.ip_hash == ip_hash, 1), else_=0)), 0),
            ).where(LoginEvent.created_at >= datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10))
        ).one()
        if settings.auth_rate_limit_enabled and (
            int(attempts[0] or 0) >= 8
            or int(attempts[1] or 0) >= 30
        ):
            raise AppError("登录尝试过于频繁，请稍后再试", 429, "AUTH_RATE_LIMITED")
        user_model = cursor.session.scalar(select(User).where(User.username == credentials.username))
        user = model_as_dict(user_model) if user_model is not None else None

    stored_hash = user["password"] if user else _DUMMY_HASH
    password_ok = bcrypt.checkpw(
        credentials.password.encode("utf-8"), stored_hash.encode("utf-8")
    )
    succeeded = bool(user and password_ok and user.get("is_active"))
    with get_cursor() as cursor:
        cursor.session.add(
            LoginEvent(identifier_hash=identifier_hash, ip_hash=ip_hash, succeeded=succeeded)
        )
        if succeeded:
            assert user is not None
            user_model = cursor.session.get(User, user["id"])
            if user_model is not None:
                user_model.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if not succeeded:
        raise AppError("用户名或密码错误", 401, "INVALID_CREDENTIALS")
    assert user is not None
    _set_cookie(response, create_access_token(user))
    return success({"id": user["id"], "username": user["username"]}, "登录成功")


@router.post("/logout", response_model=ApiResponse[None])
def logout(response: Response, user=Depends(get_current_user)):
    User = reflected_model("users")
    with get_cursor() as cursor:
        user_model = cursor.session.get(User, user["id"])
        if user_model is not None:
            user_model.token_version = int(user_model.token_version or 0) + 1
    response.delete_cookie(COOKIE_NAME, path="/")
    return success(message="已退出登录")


@router.get("/me", response_model=ApiResponse[AuthUser])
def me(user=Depends(get_current_user)):
    return success(user)


__all__ = ["router"]
