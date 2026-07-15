"""
AI 长期记忆 API 路由
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional

from db import get_cursor
from services.memory_service import memory_service
from utils import success, error, get_current_user

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500, description="记忆内容")
    memory_type: str = Field(default="episodic", description="记忆类型: episodic/semantic/procedural")
    category: Optional[str] = Field(default=None, description="分类: preference/weakness/goal/fact/habit/strength")
    summary: Optional[str] = Field(default=None, max_length=100, description="摘要")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性 0-1")
    confidence: float = Field(default=0.8, ge=0, le=1, description="置信度 0-1")


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=500)
    category: Optional[str] = None
    summary: Optional[str] = Field(default=None, max_length=100)
    importance: Optional[float] = Field(default=None, ge=0, le=1)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


@router.post("")
def create_memory(
    request: MemoryCreateRequest,
    user=Depends(get_current_user)
):
    """手动创建一条记忆"""
    try:
        memory_id = memory_service.save_memory(
            user_id=user["id"],
            content=request.content,
            memory_type=request.memory_type,
            category=request.category,
            summary=request.summary,
            source="explicit",
            importance=request.importance,
            confidence=request.confidence
        )

        return success(
            data={"id": memory_id},
            message="记忆创建成功"
        )
    except Exception as e:
        return error(message=f"创建记忆失败：{str(e)}", code=500)


@router.get("")
def list_memories(
    memory_type: Optional[str] = Query(default=None, description="记忆类型过滤"),
    category: Optional[str] = Query(default=None, description="分类过滤"),
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    user=Depends(get_current_user)
):
    """获取当前用户的记忆列表"""
    try:
        result = memory_service.get_user_memories(
            user_id=user["id"],
            memory_type=memory_type,
            category=category,
            page=page,
            size=size
        )

        return success(data=result, message="获取记忆列表成功")
    except Exception as e:
        return error(message=f"获取记忆列表失败：{str(e)}", code=500)


@router.get("/stats")
def get_memory_stats(user=Depends(get_current_user)):
    """获取记忆统计信息"""
    try:
        stats = memory_service.get_memory_stats(user["id"])
        return success(data=stats, message="获取记忆统计成功")
    except Exception as e:
        return error(message=f"获取记忆统计失败：{str(e)}", code=500)


@router.post("/search")
def search_memories(
    query: str = Query(..., min_length=1, max_length=200, description="搜索查询"),
    memory_type: Optional[str] = Query(default=None, description="记忆类型过滤"),
    top_k: int = Query(default=5, ge=1, le=20, description="返回数量"),
    user=Depends(get_current_user)
):
    """语义检索记忆"""
    try:
        results = memory_service.recall(
            user_id=user["id"],
            query=query,
            memory_type=memory_type,
            top_k=top_k
        )

        return success(
            data={"items": results, "total": len(results)},
            message="记忆检索成功"
        )
    except Exception as e:
        return error(message=f"记忆检索失败：{str(e)}", code=500)


@router.put("/{memory_id}")
def update_memory(
    memory_id: int,
    request: MemoryUpdateRequest,
    user=Depends(get_current_user)
):
    """更新记忆"""
    try:
        success_flag = memory_service.update_memory(
            memory_id=memory_id,
            user_id=user["id"],
            content=request.content,
            summary=request.summary,
            importance=request.importance,
            confidence=request.confidence,
            category=request.category
        )

        if success_flag:
            return success(message="记忆更新成功")
        else:
            return error(message="记忆不存在或无权限", code=404)
    except Exception as e:
        return error(message=f"更新记忆失败：{str(e)}", code=500)


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: int,
    confirmed: bool = False,
    user=Depends(get_current_user)
):
    """删除记忆"""
    if not confirmed:
        return error(message="删除记忆需要二次确认", code=409)
    try:
        success_flag = memory_service.delete_memory(memory_id, user["id"])

        if success_flag:
            return success(message="记忆删除成功")
        else:
            return error(message="记忆不存在或无权限", code=404)
    except Exception as e:
        return error(message=f"删除记忆失败：{str(e)}", code=500)


@router.post("/forget-old")
def forget_old_memories(
    days: int = Query(default=90, ge=1, le=365, description="遗忘天数"),
    confirmed: bool = False,
    user=Depends(get_current_user)
):
    """遗忘旧记忆"""
    if not confirmed:
        return error(message="批量遗忘记忆需要二次确认", code=409)
    try:
        count = memory_service.forget_old_memories(user["id"], days)
        return success(
            data={"forgotten_count": count},
            message=f"已遗忘 {count} 条旧记忆"
        )
    except Exception as e:
        return error(message=f"遗忘旧记忆失败：{str(e)}", code=500)
