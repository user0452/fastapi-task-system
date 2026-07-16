import json

from fastapi import Depends, Query
from sqlalchemy import func, select

from app.core.database import get_cursor
from app.core.responses import V1APIRouter, success
from app.models import model_as_dict, reflected_model
from app.modules.auth.dependencies import get_current_user

router = V1APIRouter(tags=["account"])


@router.get("/account/profile")
def get_profile(user=Depends(get_current_user)):
    StudentProfile = reflected_model("student_profiles")
    with get_cursor() as cursor:
        profile_model = cursor.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user["id"])
        )
        row = model_as_dict(profile_model) if profile_model is not None else None
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
    OperationLog = reflected_model("operation_logs")
    with get_cursor() as cursor:
        total = int(
            cursor.session.scalar(
                select(func.count()).select_from(OperationLog).where(OperationLog.user_id == user["id"])
            ) or 0
        )
        items = [
            model_as_dict(item)
            for item in cursor.session.scalars(
                select(OperationLog)
                .where(OperationLog.user_id == user["id"])
                .order_by(OperationLog.id.desc())
                .limit(size)
                .offset(offset)
            )
        ]
    return success(data={"items": items, "total": total, "page": page, "size": size})


__all__ = ["router"]
