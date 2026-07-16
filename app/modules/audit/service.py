import json
import logging
from typing import Any

from app.core.database import get_cursor
from app.models import reflected_model

logger = logging.getLogger(__name__)


def _write(
    cursor,
    user_id: int,
    action: str,
    target_type: str | None,
    target_id: int | None,
    detail: dict[str, Any] | None,
) -> None:
    OperationLog = reflected_model("operation_logs")
    cursor.session.add(
        OperationLog(
            user_id=user_id,
            action=action[:100],
            target_type=target_type[:50] if target_type else None,
            target_id=target_id,
            detail=json.dumps(detail or {}, ensure_ascii=False, default=str),
        )
    )


def record_audit(
    user_id: int,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: dict[str, Any] | None = None,
    *,
    cursor=None,
    strict: bool = False,
) -> None:
    try:
        if cursor is not None:
            _write(cursor, user_id, action, target_type, target_id, detail)
            return
        with get_cursor() as owned_cursor:
            _write(owned_cursor, user_id, action, target_type, target_id, detail)
    except Exception:
        logger.warning("audit_log_write_failed action=%s", action, exc_info=True)
        if strict:
            raise
