from fastapi import Depends, Query
from sqlalchemy import func, select

from app.core.database import get_cursor
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
)
from app.modules.account.service import get_account_settings, update_user_timezone
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
