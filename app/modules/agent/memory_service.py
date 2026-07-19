"""Course agent long-term memory CRUD and public projection."""

from __future__ import annotations

import hashlib
import json
import re

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.embedding.service import (
    EMBEDDING_MODEL_NAME,
    embed_texts,
    serialize_embedding,
)
from app.modules.agent import repository
from app.modules.agent.schemas import CourseAgentMemoryPatch, CourseAgentMemoryUpsert
from app.modules.audit.service import record_audit
from app.modules.courses import repository as course_repository

ALLOWED_MEMORY_TYPES = {
    "course_preference",
    "mastered_content",
    "weak_point",
    "error_pattern",
    "learning_goal",
    "course_context",
}
_MEMORY_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,120}$")


def public_memory(memory: dict) -> dict:
    public_keys = (
        "id",
        "agent_id",
        "course_id",
        "memory_key",
        "memory_type",
        "content",
        "source_message_id",
        "source_type",
        "enabled",
        "auto_generated",
        "confidence",
        "evidence",
        "last_observed_at",
        "status",
        "created_at",
        "updated_at",
    )
    return {key: memory.get(key) for key in public_keys if key in memory}


def require_course_agent(cursor, user_id: int, course_id: int) -> tuple[dict, dict]:
    course = course_repository.get_course(cursor, course_id, user_id)
    if course is None or course.get("status") == "archived":
        raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
    return course, repository.ensure_course_agent(cursor, user_id, course)


def _normalize_memory_type(memory_type: str | None) -> str:
    value = str(memory_type or "course_context").strip()
    if value not in ALLOWED_MEMORY_TYPES:
        raise AppError("不支持的记忆类型", 422, "MEMORY_TYPE_INVALID")
    return value


def _normalize_memory_key(memory_key: str | None, content_text: str) -> str:
    value = str(memory_key or "").strip()
    if not value:
        digest = hashlib.sha1(content_text.encode("utf-8")).hexdigest()[:12]
        value = f"chat_{digest}"
    if not _MEMORY_KEY_PATTERN.fullmatch(value):
        raise AppError("记忆键格式无效", 422, "MEMORY_KEY_INVALID")
    return value


def _normalize_content(content: dict | str | None) -> dict:
    if isinstance(content, dict):
        if not content:
            raise AppError("记忆内容不能为空", 422, "MEMORY_CONTENT_INVALID")
        return content
    text = str(content or "").strip()
    if not text:
        raise AppError("记忆内容不能为空", 422, "MEMORY_CONTENT_INVALID")
    return {"text": text[:2000]}


def list_course_agent_memories(user_id: int, course_id: int) -> dict:
    with get_cursor() as cursor:
        _, agent = require_course_agent(cursor, user_id, course_id)
        memories = repository.list_course_memories(
            cursor,
            agent["id"],
            user_id,
            include_disabled=True,
        )
        record_audit(
            user_id,
            "COURSE_AGENT_MEMORIES_VIEWED",
            "course_agent",
            agent["id"],
            {"course_id": course_id, "memory_count": len(memories)},
            cursor=cursor,
        )
    return {
        "items": [public_memory(memory) for memory in memories],
        "total": len(memories),
    }


def save_course_agent_memory(
    user_id: int,
    course_id: int,
    request: CourseAgentMemoryUpsert,
    *,
    source_type: str = "manual",
    source_message_id: int | None = None,
    auto_generated: bool = False,
    confidence: float | None = None,
    evidence: list[dict] | None = None,
) -> dict:
    with get_cursor() as cursor:
        _, agent = require_course_agent(cursor, user_id, course_id)
    content = _normalize_content(request.content)
    memory_type = _normalize_memory_type(request.memory_type)
    memory_key = _normalize_memory_key(
        request.memory_key,
        json.dumps(content, ensure_ascii=False, sort_keys=True),
    )
    memory_text = json.dumps(content, ensure_ascii=False, default=str, sort_keys=True)
    embedding = embed_texts([memory_text])[0]
    embedding_hash = hashlib.sha256(
        f"{EMBEDDING_MODEL_NAME}\0{memory_text}".encode("utf-8")
    ).hexdigest()
    with get_cursor() as cursor:
        memory = repository.upsert_course_memory(
            cursor,
            agent["id"],
            user_id,
            course_id,
            memory_key,
            memory_type,
            content,
            source_message_id=source_message_id,
            source_type=source_type,
            embedding_json=serialize_embedding(embedding),
            embedding_model=EMBEDDING_MODEL_NAME,
            embedding_hash=embedding_hash,
            auto_generated=auto_generated,
            confidence=confidence,
            evidence=evidence,
        )
        record_audit(
            user_id,
            "COURSE_AGENT_MEMORY_UPDATED",
            "course_agent_memory",
            memory["id"],
            {
                "course_id": course_id,
                "memory_key": memory_key,
                "source_type": source_type,
            },
            cursor=cursor,
        )
    return public_memory(memory)


def update_course_agent_memory(
    user_id: int,
    course_id: int,
    memory_id: int,
    request: CourseAgentMemoryPatch,
    *,
    source_type: str | None = None,
    source_message_id: int | None = None,
) -> dict:
    with get_cursor() as cursor:
        require_course_agent(cursor, user_id, course_id)
        existing = repository.get_course_memory(cursor, memory_id, user_id, course_id)
        if existing is None:
            raise AppError("记忆不存在或无访问权限", 404, "COURSE_MEMORY_NOT_FOUND")

    values: dict = {}
    if "memory_type" in request.model_fields_set and request.memory_type is not None:
        values["memory_type"] = _normalize_memory_type(request.memory_type)
    if "enabled" in request.model_fields_set and request.enabled is not None:
        values["enabled"] = request.enabled
    if "content" in request.model_fields_set and request.content is not None:
        content = _normalize_content(request.content)
        memory_text = json.dumps(content, ensure_ascii=False, default=str, sort_keys=True)
        embedding = embed_texts([memory_text])[0]
        values.update(
            {
                "content_json": memory_text,
                "embedding_json": serialize_embedding(embedding),
                "embedding_model": EMBEDDING_MODEL_NAME,
                "embedding_hash": hashlib.sha256(
                    f"{EMBEDDING_MODEL_NAME}\0{memory_text}".encode("utf-8")
                ).hexdigest(),
                "source_message_id": source_message_id,
                "source_type": source_type or "manual_edit",
            }
        )
    elif source_type is not None:
        values["source_type"] = source_type
        values["source_message_id"] = source_message_id

    with get_cursor() as cursor:
        memory = repository.update_course_memory(
            cursor,
            memory_id,
            user_id,
            course_id,
            values,
        )
        if memory is None:
            raise AppError("记忆不存在或无访问权限", 404, "COURSE_MEMORY_NOT_FOUND")
        record_audit(
            user_id,
            "COURSE_AGENT_MEMORY_UPDATED",
            "course_agent_memory",
            memory_id,
            {"course_id": course_id, "fields": sorted(values)},
            cursor=cursor,
        )
        repository.mark_user_learning_profile_stale(cursor, user_id)
    return public_memory(memory)


def set_course_agent_memory_type_enabled(
    user_id: int,
    course_id: int,
    memory_type: str,
    enabled: bool,
) -> dict:
    memory_type = _normalize_memory_type(memory_type)
    with get_cursor() as cursor:
        _, agent = require_course_agent(cursor, user_id, course_id)
        affected = repository.set_course_memory_type_enabled(
            cursor,
            agent["id"],
            user_id,
            course_id,
            memory_type,
            enabled,
        )
        if affected == 0:
            raise AppError("该类型没有可更新的记忆", 404, "COURSE_MEMORY_TYPE_NOT_FOUND")
        record_audit(
            user_id,
            "COURSE_AGENT_MEMORY_TYPE_TOGGLED",
            "course_agent",
            agent["id"],
            {
                "course_id": course_id,
                "memory_type": memory_type,
                "enabled": enabled,
                "affected": affected,
            },
            cursor=cursor,
        )
        repository.mark_user_learning_profile_stale(cursor, user_id)
    return {"memory_type": memory_type, "enabled": enabled, "affected": affected}


def delete_course_agent_memory(user_id: int, course_id: int, memory_id: int) -> None:
    with get_cursor() as cursor:
        require_course_agent(cursor, user_id, course_id)
        if not repository.delete_course_memory(cursor, memory_id, user_id, course_id):
            raise AppError("记忆不存在或无访问权限", 404, "COURSE_MEMORY_NOT_FOUND")
        record_audit(
            user_id,
            "COURSE_AGENT_MEMORY_DELETED",
            "course_agent_memory",
            memory_id,
            {"course_id": course_id},
            cursor=cursor,
        )
        repository.mark_user_learning_profile_stale(cursor, user_id)


def write_chat_memory(
    user_id: int,
    course_id: int,
    *,
    text: str,
    memory_type: str = "course_context",
    memory_key: str | None = None,
    source_message_id: int | None = None,
) -> dict:
    return save_course_agent_memory(
        user_id,
        course_id,
        CourseAgentMemoryUpsert(
            memory_key=_normalize_memory_key(memory_key, text),
            memory_type=_normalize_memory_type(memory_type),
            content=_normalize_content(text),
        ),
        source_type="chat",
        source_message_id=source_message_id,
    )


def update_chat_memory(
    user_id: int,
    course_id: int,
    memory_id: int,
    *,
    text: str | None = None,
    memory_type: str | None = None,
    enabled: bool | None = None,
    source_message_id: int | None = None,
) -> dict:
    payload: dict = {}
    if text is not None:
        payload["content"] = _normalize_content(text)
    if memory_type is not None:
        payload["memory_type"] = _normalize_memory_type(memory_type)
    if enabled is not None:
        payload["enabled"] = bool(enabled)
    if not payload:
        raise AppError("至少提供一个需要更新的记忆字段", 422, "MEMORY_PATCH_EMPTY")
    return update_course_agent_memory(
        user_id,
        course_id,
        memory_id,
        CourseAgentMemoryPatch(**payload),
        source_type="chat" if text is not None else None,
        source_message_id=source_message_id if text is not None else None,
    )


def delete_chat_memory(user_id: int, course_id: int, memory_id: int) -> dict:
    delete_course_agent_memory(user_id, course_id, memory_id)
    return {"memory_id": memory_id, "deleted": True}
