import json

from fastapi import Depends, Query

from app.core.database import get_cursor
from app.core.responses import V1APIRouter, success
from app.modules.auth.dependencies import get_current_user

router = V1APIRouter(tags=["account"])


@router.get("/account/profile")
def get_profile(user=Depends(get_current_user)):
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, user_id, profile_json, created_at, updated_at
            FROM student_profiles
            WHERE user_id = %s
            """,
            (user["id"],),
        )
        row = cursor.fetchone()
    if row is None:
        return success(data=None, message="当前用户还没有学习画像")

    profile = json.loads(row["profile_json"])
    if isinstance(profile, str):
        profile = json.loads(profile)
    return success(
        data={
            "id": row["id"],
            "user_id": row["user_id"],
            "profile": profile,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


@router.get("/audit/logs")
def list_operation_logs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user=Depends(get_current_user),
):
    offset = (page - 1) * size
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM operation_logs WHERE user_id = %s",
            (user["id"],),
        )
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT id, action, target_type, target_id, detail, created_at
            FROM operation_logs
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (user["id"], size, offset),
        )
        items = cursor.fetchall()
    return success(data={"items": items, "total": total, "page": page, "size": size})


__all__ = ["router"]
