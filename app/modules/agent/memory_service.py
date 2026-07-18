"""Course agent long-term memory CRUD and public projection."""

from __future__ import annotations

import hashlib
import json

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
) -> dict:
    with get_cursor() as cursor:
        _, agent = require_course_agent(cursor, user_id, course_id)
    memory_text = json.dumps(request.content, ensure_ascii=False, default=str, sort_keys=True)
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
            request.memory_key,
            request.memory_type,
            request.content,
            source_type="manual",
            embedding_json=serialize_embedding(embedding),
            embedding_model=EMBEDDING_MODEL_NAME,
            embedding_hash=embedding_hash,
        )
        record_audit(
            user_id,
            "COURSE_AGENT_MEMORY_UPDATED",
            "course_agent_memory",
            memory["id"],
            {"course_id": course_id, "memory_key": request.memory_key},
            cursor=cursor,
        )
    return public_memory(memory)


def update_course_agent_memory(
    user_id: int,
    course_id: int,
    memory_id: int,
    request: CourseAgentMemoryPatch,
) -> dict:
    with get_cursor() as cursor:
        require_course_agent(cursor, user_id, course_id)
        existing = repository.get_course_memory(cursor, memory_id, user_id, course_id)
        if existing is None:
            raise AppError("记忆不存在或无访问权限", 404, "COURSE_MEMORY_NOT_FOUND")

    values: dict = {}
    if "memory_type" in request.model_fields_set and request.memory_type is not None:
        values["memory_type"] = request.memory_type
    if "enabled" in request.model_fields_set and request.enabled is not None:
        values["enabled"] = request.enabled
    if "content" in request.model_fields_set and request.content is not None:
        memory_text = json.dumps(request.content, ensure_ascii=False, default=str, sort_keys=True)
        embedding = embed_texts([memory_text])[0]
        values.update(
            {
                "content_json": memory_text,
                "embedding_json": serialize_embedding(embedding),
                "embedding_model": EMBEDDING_MODEL_NAME,
                "embedding_hash": hashlib.sha256(
                    f"{EMBEDDING_MODEL_NAME}\0{memory_text}".encode("utf-8")
                ).hexdigest(),
                "source_message_id": None,
                "source_type": "manual_edit",
            }
        )

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
    return public_memory(memory)


def set_course_agent_memory_type_enabled(
    user_id: int,
    course_id: int,
    memory_type: str,
    enabled: bool,
) -> dict:
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
