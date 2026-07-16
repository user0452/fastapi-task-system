from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.time_utils import (
    DEFAULT_USER_TIMEZONE,
    local_date,
    local_datetime,
    utc_now,
    validate_timezone_name,
)
from app.models import reflected_model


def get_user_timezone(user_id: int) -> str:
    User = reflected_model("users")
    with get_cursor() as cursor:
        value = cursor.session.scalar(select(User.timezone).where(User.id == user_id))
    if value is None:
        raise AppError("用户不存在", 404, "USER_NOT_FOUND")
    return validate_timezone_name(str(value or DEFAULT_USER_TIMEZONE))


def get_user_local_date(user_id: int, now_utc: datetime | None = None) -> date:
    return local_date(get_user_timezone(user_id), now_utc or utc_now())


def get_user_server_time(user_id: int, now_utc: datetime | None = None) -> str:
    return local_datetime(
        get_user_timezone(user_id),
        now_utc or utc_now(),
    ).isoformat()


def update_user_timezone(user_id: int, timezone_name: str) -> dict:
    name = validate_timezone_name(timezone_name)
    User = reflected_model("users")
    with get_cursor() as cursor:
        user = cursor.session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise AppError("用户不存在", 404, "USER_NOT_FOUND")
        user.timezone = name
        cursor.session.flush()
    return {"timezone": name, "server_time": get_user_server_time(user_id)}


def get_account_settings(user_id: int) -> dict:
    timezone_name = get_user_timezone(user_id)
    return {
        "timezone": timezone_name,
        "server_time": get_user_server_time(user_id),
    }


__all__ = [
    "get_account_settings",
    "get_user_local_date",
    "get_user_server_time",
    "get_user_timezone",
    "update_user_timezone",
]
