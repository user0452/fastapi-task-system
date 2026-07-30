import json

from fastapi import Depends, Query
from sqlalchemy import func, select

from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.responses import V1APIRouter, success
from app.models import model_as_dict, reflected_model
from app.modules.account.llm_config_service import (
    delete_user_llm_config,
    get_user_llm_config,
    save_user_llm_config,
    test_user_llm_config,
)
from app.modules.account.schemas import (
    AccountSettingsUpdate,
    UserLlmConfigTest,
    UserLlmConfigUpdate,
    UserMemorySettingsUpdate,
)
from app.modules.account.service import get_account_settings, update_user_timezone
from app.modules.agent import repository as agent_repository
from app.modules.audit.service import record_audit
from app.modules.auth.dependencies import get_current_user

router = V1APIRouter(tags=["account"])


@router.get("/account/settings")
def account_settings(user=Depends(get_current_user)):
    return success(data=get_account_settings(user["id"]))


@router.patch("/account/settings")
def update_account_settings(
    request: AccountSettingsUpdate,
    user=Depends(get_current_user),
):
    return success(
        data=update_user_timezone(user["id"], request.timezone),
        message="账户设置已更新",
    )


@router.get("/account/llm-config")
def user_llm_config(user=Depends(get_current_user)):
    return success(data=get_user_llm_config(user["id"]))


@router.put("/account/llm-config")
def update_user_llm_config(
    request: UserLlmConfigUpdate,
    user=Depends(get_current_user),
):
    result = save_user_llm_config(user["id"], **request.model_dump())
    record_audit(
        user["id"],
        "USER_LLM_CONFIG_UPDATED",
        "user_llm_config",
        user["id"],
        {
            "enabled": result["enabled"],
            "base_url": result["base_url"],
            "model": result["model"],
        },
    )
    return success(data=result, message="模型 API 配置已保存")


@router.post("/account/llm-config/test")
def test_saved_user_llm_config(
    request: UserLlmConfigTest,
    user=Depends(get_current_user),
):
    return success(
        data=test_user_llm_config(user["id"], **request.model_dump()),
        message="连接成功",
    )


@router.delete("/account/llm-config")
def remove_user_llm_config(user=Depends(get_current_user)):
    delete_user_llm_config(user["id"])
    record_audit(
        user["id"],
        "USER_LLM_CONFIG_DELETED",
        "user_llm_config",
        user["id"],
    )
    return success(data=get_user_llm_config(user["id"]), message="已恢复服务端默认模型")


@router.get("/account/memory-settings")
def get_memory_settings(user=Depends(get_current_user)):
    with get_cursor() as cursor:
        settings = agent_repository.get_memory_settings(cursor, user["id"])
    return success(data=settings)


@router.patch("/account/memory-settings")
def update_memory_settings(
    request: UserMemorySettingsUpdate,
    user=Depends(get_current_user),
):
    values = {
        field: value
        for field, value in request.model_dump().items()
        if value is not None
    }
    if not values:
        raise AppError("至少提供一个需要更新的记忆设置", 422, "MEMORY_SETTINGS_EMPTY")
    with get_cursor() as cursor:
        if values.get("cross_course_profile_enabled") is True:
            values.setdefault("course_auto_memory_enabled", True)
        elif values.get("course_auto_memory_enabled") is False:
            values.setdefault("cross_course_profile_enabled", False)
        settings = agent_repository.update_memory_settings(cursor, user["id"], values)
        if values.get("course_auto_memory_enabled") is False:
            agent_repository.mark_user_learning_profile_stale(cursor, user["id"])
    return success(data=settings, message="自动学习记忆设置已更新")


@router.get("/account/profile")
def get_profile(user=Depends(get_current_user)):
    StudentProfile = reflected_model("student_profiles")
    with get_cursor() as cursor:
        profile_model = cursor.session.scalar(
            select(StudentProfile).where(StudentProfile.user_id == user["id"])
        )
        row = model_as_dict(profile_model) if profile_model is not None else None
        derived = agent_repository.get_user_learning_profile(cursor, user["id"])
        memory_settings = agent_repository.get_memory_settings(cursor, user["id"])
    baseline = None
    if row is not None:
        try:
            baseline = json.loads(row["profile_json"])
            if isinstance(baseline, str):
                baseline = json.loads(baseline)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AppError(
                "学习画像数据格式无效，请重新生成画像",
                422,
                "PROFILE_DATA_INVALID",
            ) from exc
        if not isinstance(baseline, dict):
            raise AppError(
                "学习画像数据格式无效，请重新生成画像",
                422,
                "PROFILE_DATA_INVALID",
            )
    if row is None and derived is None:
        return success(
            data={
                "profile": None,
                "baseline_profile": None,
                "derived_profile": None,
                "memory_settings": memory_settings,
            },
            message="当前用户还没有学习画像",
        )
    return success(
        data={
            "id": row["id"] if row else None,
            "user_id": user["id"],
            "profile": baseline,
            "baseline_profile": baseline,
            "derived_profile": derived.get("profile") if derived else None,
            "derived_profile_meta": {
                key: derived.get(key)
                for key in ("id", "version", "status", "source_memory_count", "source_course_count", "generated_at", "updated_at")
            } if derived else None,
            "memory_settings": memory_settings,
            "created_at": row["created_at"] if row else None,
            "updated_at": row["updated_at"] if row else (derived.get("updated_at") if derived else None),
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
