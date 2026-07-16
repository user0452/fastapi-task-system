from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_USER_TIMEZONE = "Asia/Shanghai"
UTC = timezone.utc


def validate_timezone_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("timezone must not be blank")
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return name


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    return utc_now().replace(tzinfo=None)


def local_datetime(timezone_name: str, now_utc: datetime | None = None) -> datetime:
    instant = now_utc or utc_now()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(ZoneInfo(validate_timezone_name(timezone_name)))


def local_date(timezone_name: str, now_utc: datetime | None = None) -> date:
    return local_datetime(timezone_name, now_utc).date()


def to_utc_naive(value: datetime | None, timezone_name: str) -> datetime | None:
    if value is None:
        return None
    aware = (
        value.replace(tzinfo=ZoneInfo(validate_timezone_name(timezone_name)))
        if value.tzinfo is None
        else value
    )
    return aware.astimezone(UTC).replace(tzinfo=None)


def utc_naive_to_local(value: datetime, timezone_name: str) -> datetime:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.astimezone(ZoneInfo(validate_timezone_name(timezone_name)))


__all__ = [
    "DEFAULT_USER_TIMEZONE",
    "local_date",
    "local_datetime",
    "to_utc_naive",
    "utc_naive_to_local",
    "utc_now",
    "utc_now_naive",
    "validate_timezone_name",
]
