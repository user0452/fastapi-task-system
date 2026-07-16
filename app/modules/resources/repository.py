"""External-resource persistence implemented with SQLAlchemy ORM."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.models import model_as_dict, reflected_model


def _loads(value: Any, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _resource(resource: Any | None) -> dict | None:
    if resource is None:
        return None
    row = model_as_dict(resource)
    row["metadata"] = _loads(row.pop("metadata_json", None), {})
    if isinstance(row.get("published_at"), datetime):
        published_at = row["published_at"]
        row["published_at"] = (
            published_at.replace(tzinfo=timezone.utc)
            if published_at.tzinfo is None
            else published_at.astimezone(timezone.utc)
        )
    return row


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _resource_models():
    return (
        reflected_model("external_resources"),
        reflected_model("resource_interactions"),
        reflected_model("external_resource_search_cache"),
    )


def get_resource(cursor, resource_id: int, user_id: int, course_id: int) -> dict | None:
    ExternalResource, _, _ = _resource_models()
    resource = cursor.session.scalar(
        select(ExternalResource).where(
            ExternalResource.id == resource_id,
            ExternalResource.user_id == user_id,
            ExternalResource.course_id == course_id,
        )
    )
    return _resource(resource)


def upsert_resource(cursor, user_id: int, course_id: int, item: dict) -> dict:
    ExternalResource, _, _ = _resource_models()
    session = cursor.session
    resource = session.scalar(
        select(ExternalResource)
        .where(
            ExternalResource.user_id == user_id,
            ExternalResource.course_id == course_id,
            ExternalResource.url_hash == item["url_hash"],
        )
        .with_for_update()
    )
    if resource is None:
        resource = ExternalResource(
            user_id=user_id,
            course_id=course_id,
            knowledge_point_id=item.get("knowledge_point_id"),
            provider=item["provider"],
            provider_resource_id=item.get("provider_resource_id"),
            resource_type=item.get("resource_type", "video"),
            canonical_url=item["canonical_url"],
            url_hash=item["url_hash"],
            title=item["title"][:500],
            author=(item.get("author") or "")[:255] or None,
            summary=item.get("summary"),
            thumbnail_url=item.get("thumbnail_url"),
            duration_seconds=item.get("duration_seconds"),
            published_at=_utc_naive(item.get("published_at")),
            language=item.get("language", "zh-CN"),
            relevance_score=item.get("relevance_score", 0),
            quality_score=item.get("quality_score", 0),
            search_query=item.get("search_query", "")[:500],
            metadata_json=json.dumps(item.get("metadata") or {}, ensure_ascii=False, default=str),
            status="active",
        )
        session.add(resource)
    else:
        if item.get("knowledge_point_id") is not None:
            resource.knowledge_point_id = item["knowledge_point_id"]
        resource.provider = item["provider"]
        resource.provider_resource_id = item.get("provider_resource_id")
        resource.title = item["title"][:500]
        resource.author = (item.get("author") or "")[:255] or resource.author
        resource.summary = item.get("summary") or resource.summary
        resource.thumbnail_url = item.get("thumbnail_url") or resource.thumbnail_url
        resource.duration_seconds = item.get("duration_seconds") or resource.duration_seconds
        resource.published_at = _utc_naive(item.get("published_at")) or resource.published_at
        resource.relevance_score = max(float(resource.relevance_score or 0), item.get("relevance_score", 0))
        resource.quality_score = max(float(resource.quality_score or 0), item.get("quality_score", 0))
        resource.search_query = item.get("search_query", "")[:500]
        resource.metadata_json = json.dumps(item.get("metadata") or {}, ensure_ascii=False, default=str)
        resource.status = "active"
    session.flush()
    session.refresh(resource)
    return _resource(resource) or {}


def _interaction_states(
    cursor, user_id: int, course_id: int, resource_ids: list[int]
) -> dict[int, dict[str, Any]]:
    states = {
        resource_id: {"saved": False, "completed": False, "helpful": None, "opened_count": 0}
        for resource_id in resource_ids
    }
    if not resource_ids:
        return states
    _, ResourceInteraction, _ = _resource_models()
    interactions = cursor.session.scalars(
        select(ResourceInteraction)
        .where(
            ResourceInteraction.user_id == user_id,
            ResourceInteraction.course_id == course_id,
            ResourceInteraction.resource_id.in_(resource_ids),
        )
        .order_by(ResourceInteraction.id)
    )
    for interaction in interactions:
        state = states[interaction.resource_id]
        kind = interaction.interaction_type
        if kind == "opened":
            state["opened_count"] = int(state["opened_count"] or 0) + 1
        elif kind == "saved":
            state["saved"] = True
        elif kind == "unsaved":
            state["saved"] = False
        elif kind == "completed":
            state["completed"] = True
        elif kind == "uncompleted":
            state["completed"] = False
        elif kind == "helpful":
            state["helpful"] = True
        elif kind == "not_helpful":
            state["helpful"] = False
    return states


def list_resources_by_ids(
    cursor,
    user_id: int,
    course_id: int,
    resource_ids: list[int],
) -> list[dict]:
    if not resource_ids:
        return []
    ExternalResource, _, _ = _resource_models()
    resources = cursor.session.scalars(
        select(ExternalResource).where(
            ExternalResource.user_id == user_id,
            ExternalResource.course_id == course_id,
            ExternalResource.id.in_(resource_ids),
        )
    )
    by_id = {resource.id: _resource(resource) for resource in resources}
    states = _interaction_states(cursor, user_id, course_id, resource_ids)
    items = []
    for resource_id in resource_ids:
        item = by_id.get(resource_id)
        if item:
            item["interaction"] = states[resource_id]
            items.append(item)
    return items


def list_course_resources(cursor, user_id: int, course_id: int, limit: int = 100) -> list[dict]:
    ExternalResource, _, _ = _resource_models()
    resources = cursor.session.scalars(
        select(ExternalResource)
        .where(
            ExternalResource.user_id == user_id,
            ExternalResource.course_id == course_id,
            ExternalResource.status == "active",
        )
        .order_by(ExternalResource.updated_at.desc(), ExternalResource.id.desc())
        .limit(limit)
    )
    items = [item for resource in resources if (item := _resource(resource)) is not None]
    states = _interaction_states(cursor, user_id, course_id, [item["id"] for item in items])
    for item in items:
        item["interaction"] = states[item["id"]]
    return items


def add_interaction(
    cursor,
    resource_id: int,
    user_id: int,
    course_id: int,
    interaction_type: str,
    value: dict,
) -> None:
    _, ResourceInteraction, _ = _resource_models()
    cursor.session.add(
        ResourceInteraction(
            resource_id=resource_id,
            user_id=user_id,
            course_id=course_id,
            interaction_type=interaction_type,
            value_json=json.dumps(value or {}, ensure_ascii=False, default=str),
        )
    )
    # The caller reads the current interaction state in the same transaction.
    cursor.session.flush()


def get_cache(cursor, user_id: int, course_id: int, query_hash: str, now: datetime) -> dict | None:
    _, _, SearchCache = _resource_models()
    cache = cursor.session.scalar(
        select(SearchCache).where(
            SearchCache.user_id == user_id,
            SearchCache.course_id == course_id,
            SearchCache.query_hash == query_hash,
            SearchCache.expires_at > now,
        )
    )
    if cache is None:
        return None
    row = model_as_dict(cache)
    row["result_ids"] = _loads(row.pop("result_ids_json"), [])
    return row


def save_cache(
    cursor,
    user_id: int,
    course_id: int,
    query_hash: str,
    query_text: str,
    resource_ids: list[int],
    degraded: bool,
    warning: str | None,
    expires_at: datetime,
) -> None:
    _, _, SearchCache = _resource_models()
    session = cursor.session
    cache = session.scalar(
        select(SearchCache)
        .where(
            SearchCache.user_id == user_id,
            SearchCache.course_id == course_id,
            SearchCache.query_hash == query_hash,
        )
        .with_for_update()
    )
    values = {
        "query_text": query_text[:500],
        "result_ids_json": json.dumps(resource_ids),
        "degraded": degraded,
        "warning": warning,
        "expires_at": expires_at,
    }
    if cache is None:
        session.add(SearchCache(user_id=user_id, course_id=course_id, query_hash=query_hash, **values))
    else:
        for field, value in values.items():
            setattr(cache, field, value)


def update_resource_status(
    cursor,
    resource_id: int,
    user_id: int,
    course_id: int,
    status: str,
) -> None:
    ExternalResource, _, _ = _resource_models()
    resource = cursor.session.scalar(
        select(ExternalResource).where(
            ExternalResource.id == resource_id,
            ExternalResource.user_id == user_id,
            ExternalResource.course_id == course_id,
        )
    )
    if resource is not None:
        resource.status = status
