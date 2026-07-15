import contextvars
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def bind_request_id(value: str):
    return _request_id.set(value)


def reset_request_id(token: Any) -> None:
    _request_id.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": _request_id.get(),
            "message": record.getMessage(),
        }
        for field in ("event", "method", "path", "status_code", "duration_ms", "user_id", "course_id", "job_id", "tool_name"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(item.formatter, JsonFormatter) for item in root.handlers):
        root.handlers.clear()
        root.addHandler(handler)


__all__ = ["bind_request_id", "configure_logging", "reset_request_id"]
