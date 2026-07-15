import json
from datetime import datetime
from typing import Any

RESOURCE_COLUMNS = """
    id, user_id, course_id, knowledge_point_id, provider,
    provider_resource_id, resource_type, canonical_url, url_hash,
    title, author, summary, thumbnail_url, duration_seconds,
    published_at, language, relevance_score, quality_score,
    search_query, metadata_json, status, last_checked_at,
    created_at, updated_at
"""


def _loads(value: Any, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _resource(row: dict | None) -> dict | None:
    if row:
        row["metadata"] = _loads(row.pop("metadata_json", None), {})
    return row


def get_resource(cursor, resource_id: int, user_id: int, course_id: int) -> dict | None:
    cursor.execute(
        f"""
        SELECT {RESOURCE_COLUMNS}
        FROM external_resources
        WHERE id = %s AND user_id = %s AND course_id = %s
        """,
        (resource_id, user_id, course_id),
    )
    return _resource(cursor.fetchone())


def upsert_resource(cursor, user_id: int, course_id: int, item: dict) -> dict:
    cursor.execute(
        """
        INSERT INTO external_resources
            (user_id, course_id, knowledge_point_id, provider,
             provider_resource_id, resource_type, canonical_url, url_hash,
             title, author, summary, thumbnail_url, duration_seconds,
             published_at, language, relevance_score, quality_score,
             search_query, metadata_json, status, last_checked_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, 'active', CURRENT_TIMESTAMP)
        ON DUPLICATE KEY UPDATE
            knowledge_point_id = COALESCE(VALUES(knowledge_point_id), knowledge_point_id),
            provider = VALUES(provider),
            provider_resource_id = VALUES(provider_resource_id),
            title = VALUES(title),
            author = COALESCE(VALUES(author), author),
            summary = COALESCE(VALUES(summary), summary),
            thumbnail_url = COALESCE(VALUES(thumbnail_url), thumbnail_url),
            duration_seconds = COALESCE(VALUES(duration_seconds), duration_seconds),
            published_at = COALESCE(VALUES(published_at), published_at),
            relevance_score = GREATEST(relevance_score, VALUES(relevance_score)),
            quality_score = GREATEST(quality_score, VALUES(quality_score)),
            search_query = VALUES(search_query),
            metadata_json = VALUES(metadata_json),
            status = 'active',
            last_checked_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            course_id,
            item.get("knowledge_point_id"),
            item["provider"],
            item.get("provider_resource_id"),
            item.get("resource_type", "video"),
            item["canonical_url"],
            item["url_hash"],
            item["title"][:500],
            (item.get("author") or "")[:255] or None,
            item.get("summary"),
            item.get("thumbnail_url"),
            item.get("duration_seconds"),
            item.get("published_at"),
            item.get("language", "zh-CN"),
            item.get("relevance_score", 0),
            item.get("quality_score", 0),
            item.get("search_query", "")[:500],
            json.dumps(item.get("metadata") or {}, ensure_ascii=False, default=str),
        ),
    )
    cursor.execute(
        f"""
        SELECT {RESOURCE_COLUMNS}
        FROM external_resources
        WHERE user_id = %s AND course_id = %s AND url_hash = %s
        """,
        (user_id, course_id, item["url_hash"]),
    )
    resource = _resource(cursor.fetchone())
    if resource is None:
        raise RuntimeError("resource upsert succeeded but the row could not be reloaded")
    return resource


def _interaction_states(
    cursor, user_id: int, course_id: int, resource_ids: list[int]
) -> dict[int, dict[str, Any]]:
    states = {
        resource_id: {
            "saved": False,
            "completed": False,
            "helpful": None,
            "opened_count": 0,
        }
        for resource_id in resource_ids
    }
    if not resource_ids:
        return states
    placeholders = ",".join(["%s"] * len(resource_ids))
    cursor.execute(
        f"""
        SELECT resource_id, interaction_type, value_json, created_at
        FROM resource_interactions
        WHERE user_id = %s AND course_id = %s
          AND resource_id IN ({placeholders})
        ORDER BY id
        """,
        (user_id, course_id, *resource_ids),
    )
    for row in cursor.fetchall():
        state = states[row["resource_id"]]
        kind = row["interaction_type"]
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
    placeholders = ",".join(["%s"] * len(resource_ids))
    cursor.execute(
        f"""
        SELECT {RESOURCE_COLUMNS}
        FROM external_resources
        WHERE user_id = %s AND course_id = %s AND id IN ({placeholders})
        """,
        (user_id, course_id, *resource_ids),
    )
    by_id = {row["id"]: _resource(row) for row in cursor.fetchall()}
    states = _interaction_states(cursor, user_id, course_id, resource_ids)
    items = []
    for resource_id in resource_ids:
        item = by_id.get(resource_id)
        if item:
            item["interaction"] = states[resource_id]
            items.append(item)
    return items


def list_course_resources(cursor, user_id: int, course_id: int, limit: int = 100) -> list[dict]:
    cursor.execute(
        f"""
        SELECT {RESOURCE_COLUMNS}
        FROM external_resources
        WHERE user_id = %s AND course_id = %s AND status = 'active'
        ORDER BY updated_at DESC, id DESC
        LIMIT %s
        """,
        (user_id, course_id, limit),
    )
    items = [item for row in cursor.fetchall() if (item := _resource(row)) is not None]
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
    cursor.execute(
        """
        INSERT INTO resource_interactions
            (resource_id, user_id, course_id, interaction_type, value_json)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            resource_id,
            user_id,
            course_id,
            interaction_type,
            json.dumps(value or {}, ensure_ascii=False, default=str),
        ),
    )


def get_cache(cursor, user_id: int, course_id: int, query_hash: str, now: datetime) -> dict | None:
    cursor.execute(
        """
        SELECT result_ids_json, degraded, warning, expires_at
        FROM external_resource_search_cache
        WHERE user_id = %s AND course_id = %s AND query_hash = %s AND expires_at > %s
        """,
        (user_id, course_id, query_hash, now),
    )
    row = cursor.fetchone()
    if row:
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
    cursor.execute(
        """
        INSERT INTO external_resource_search_cache
            (user_id, course_id, query_hash, query_text, result_ids_json,
             degraded, warning, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            query_text = VALUES(query_text),
            result_ids_json = VALUES(result_ids_json),
            degraded = VALUES(degraded),
            warning = VALUES(warning),
            expires_at = VALUES(expires_at),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            course_id,
            query_hash,
            query_text[:500],
            json.dumps(resource_ids),
            degraded,
            warning,
            expires_at,
        ),
    )


def update_resource_status(
    cursor,
    resource_id: int,
    user_id: int,
    course_id: int,
    status: str,
) -> None:
    cursor.execute(
        """
        UPDATE external_resources
        SET status = %s, last_checked_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s AND course_id = %s
        """,
        (status, resource_id, user_id, course_id),
    )
