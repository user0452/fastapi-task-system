import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

import requests

from app.core.config import get_settings
from app.core.database import get_cursor
from app.core.errors import AppError
from app.modules.audit.service import record_audit
from app.modules.courses.service import get_user_course
from app.modules.resources import repository
from app.modules.resources.providers import (
    BilibiliProvider,
    DeterministicVideoProvider,
    ResourceCandidate,
    ResourceProvider,
    TavilyVideoProvider,
    YouTubeProvider,
    canonicalize_url,
)
from app.modules.resources.schemas import ExternalResourceSearchRequest, ResourceInteractionRequest

logger = logging.getLogger(__name__)

GENERIC_SEARCH_TERMS = {
    "视频",
    "教程",
    "讲解",
    "学习",
    "课程",
    "网上",
    "帮我",
    "给我",
    "资源",
    "入门",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _query_terms(value: str) -> set[str]:
    compact = re.sub(r"\s+", "", (value or "").lower())
    terms = set(re.findall(r"[a-z0-9_]+", compact))
    for run in re.findall(r"[\u4e00-\u9fff]+", compact):
        terms.add(run)
        terms.update(run[index : index + 2] for index in range(max(0, len(run) - 1)))
    return {term for term in terms if term and term not in GENERIC_SEARCH_TERMS}


def _text_relevance(topic: str, title: str, summary: str | None) -> float:
    expected = _query_terms(topic)
    if not expected:
        return 0.5
    actual = _query_terms(f"{title} {summary or ''}")
    overlap = len(expected & actual) / len(expected)
    if re.sub(r"\s+", "", topic.lower()) in re.sub(r"\s+", "", title.lower()):
        overlap = max(overlap, 0.95)
    return min(1.0, overlap)


def _resolve_knowledge_point(
    user_id: int,
    course_id: int,
    topic: str,
    knowledge_point_id: int | None,
) -> dict | None:
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT point.id, point.name, point.description,
                   COALESCE(mastery.mastery, 0) AS mastery
            FROM knowledge_points point
            LEFT JOIN mastery_records mastery
              ON mastery.knowledge_point_id = point.id
             AND mastery.user_id = point.user_id
             AND mastery.course_id = point.course_id
            WHERE point.user_id = %s AND point.course_id = %s
              AND point.status = 'active'
            ORDER BY point.sort_order, point.id
            """,
            (user_id, course_id),
        )
        points = list(cursor.fetchall())
    if knowledge_point_id is not None:
        point = next((item for item in points if item["id"] == knowledge_point_id), None)
        if point is None:
            raise AppError("知识点不存在或无访问权限", 404, "KNOWLEDGE_POINT_NOT_FOUND")
        return point
    normalized = re.sub(r"\s+", "", topic.lower())
    exact = [item for item in points if re.sub(r"\s+", "", item["name"].lower()) in normalized]
    if exact:
        return max(exact, key=lambda item: len(item["name"]))
    ranked = sorted(
        points,
        key=lambda item: _text_relevance(topic, item["name"], item.get("description")),
        reverse=True,
    )
    return ranked[0] if ranked and _text_relevance(topic, ranked[0]["name"], ranked[0].get("description")) > 0 else None


def _recommendation_reason(point: dict | None, provider: str) -> str:
    platform = "Bilibili" if provider == "bilibili" else "YouTube" if provider == "youtube" else provider
    if point is None:
        return f"来自 {platform} 的补充视频，可用于建立课程主题的直观理解。"
    mastery = float(point.get("mastery") or 0)
    if mastery < 60:
        return f"你对“{point['name']}”的掌握度为 {mastery:.0f}，建议先看讲解再完成针对性练习。"
    if mastery < 80:
        return f"用于巩固“{point['name']}”并补充课程资料中的例子。"
    return f"作为“{point['name']}”的拓展材料，适合完成基础复习后观看。"


def _run_provider(
    provider: ResourceProvider,
    course_name: str,
    topic: str,
    max_results: int,
) -> tuple[list[ResourceCandidate], str | None]:
    try:
        return provider.search(course_name, topic, max_results), None
    except Exception as exc:
        logger.warning("external_provider_failed provider=%s", provider.name, exc_info=True)
        return [], f"{provider.name}: {str(exc)[:160]}"


def _public_resource(item: dict, point: dict | None = None) -> dict:
    public = dict(item)
    public.pop("url_hash", None)
    public["validity_status"] = public.get("status", "active")
    public["reason"] = _recommendation_reason(point, public.get("provider", "外部来源"))
    public["duration_label"] = _duration_label(public.get("duration_seconds"))
    return public


def _duration_label(seconds: int | None) -> str | None:
    if not seconds:
        return None
    minutes, remaining = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remaining:02d}"
    return f"{minutes}:{remaining:02d}"


def search_external_resources(
    user_id: int,
    course_id: int,
    request: ExternalResourceSearchRequest,
    *,
    providers: Iterable[ResourceProvider] | None = None,
    fallback_provider: ResourceProvider | None = None,
) -> dict:
    course = get_user_course(user_id, course_id)
    point = _resolve_knowledge_point(
        user_id,
        course_id,
        request.topic,
        request.knowledge_point_id,
    )
    query_key = "|".join(
        [
            request.topic.strip().lower(),
            str(point["id"] if point else 0),
            str(request.max_results),
        ]
    )
    query_hash = hashlib.sha256(query_key.encode("utf-8")).hexdigest()
    now = _utc_now()

    if not request.force_refresh:
        with get_cursor() as cursor:
            cached = repository.get_cache(cursor, user_id, course_id, query_hash, now)
            if cached:
                items = repository.list_resources_by_ids(
                    cursor,
                    user_id,
                    course_id,
                    [int(item) for item in cached["result_ids"]],
                )
                if items:
                    record_audit(
                        user_id,
                        "COURSE_EXTERNAL_RESOURCES_VIEWED",
                        "course",
                        course_id,
                        {"topic": request.topic, "cached": True, "count": len(items)},
                        cursor=cursor,
                    )
                    return {
                        "course_id": course_id,
                        "topic": request.topic,
                        "knowledge_point": point,
                        "resources": [_public_resource(item, point) for item in items],
                        "total": len(items),
                        "cached": True,
                        "degraded": bool(cached["degraded"]),
                        "warning": cached.get("warning"),
                        "providers": sorted({item["provider"] for item in items}),
                    }

    if providers is not None:
        provider_list = list(providers)
    elif get_settings().mock_llm:
        provider_list = [DeterministicVideoProvider()]
    else:
        provider_list = [BilibiliProvider(), YouTubeProvider()]
    fallback = fallback_provider if fallback_provider is not None else TavilyVideoProvider()
    ranking_topic = f"{course['name']} {point['name'] if point else request.topic}"
    candidates: list[ResourceCandidate] = []
    failures = []
    provider_states = []
    for provider in provider_list:
        found, failure = _run_provider(provider, course["name"], request.topic, request.max_results)
        candidates.extend(found)
        provider_states.append({"provider": provider.name, "count": len(found), "available": failure is None})
        if failure:
            failures.append(failure)

    qualified_primary = [
        item
        for item in candidates
        if _text_relevance(ranking_topic, item.title, item.summary) >= 0.12
    ]
    if len(qualified_primary) < request.max_results:
        found, failure = _run_provider(fallback, course["name"], request.topic, request.max_results * 2)
        candidates.extend(found)
        provider_states.append({"provider": fallback.name, "count": len(found), "available": failure is None})
        if failure:
            failures.append(failure)

    deduplicated: dict[str, tuple[float, ResourceCandidate]] = {}
    for candidate in candidates:
        url = canonicalize_url(candidate.canonical_url)
        if not url or candidate.resource_type != "video":
            continue
        relevance = max(
            0.0,
            min(
                1.0,
                _text_relevance(ranking_topic, candidate.title, candidate.summary) * 0.82
                + min(1.0, float(candidate.relevance_score or 0)) * 0.18,
            ),
        )
        if _text_relevance(ranking_topic, candidate.title, candidate.summary) < 0.08:
            continue
        candidate.canonical_url = url
        candidate.relevance_score = relevance
        current = deduplicated.get(url)
        score = relevance * 0.75 + max(0.0, min(1.0, float(candidate.quality_score or 0))) * 0.25
        if current is None or score > current[0]:
            deduplicated[url] = (score, candidate)
    ranked = [item[1] for item in sorted(deduplicated.values(), key=lambda item: item[0], reverse=True)]
    ranked = ranked[: request.max_results]

    degraded = bool(failures) or len(ranked) < 3
    warning = None
    if len(ranked) < 3:
        warning = "外部平台暂时没有返回足够的视频；课程资料、练习和进度功能不受影响。"
    elif failures:
        warning = "部分外部平台暂时不可用，已展示其他平台和缓存中的可用视频。"

    stored = []
    expires_at = now + timedelta(minutes=get_settings().external_resource_cache_minutes)
    with get_cursor() as cursor:
        for candidate in ranked:
            payload = candidate.to_dict()
            payload.update(
                {
                    "knowledge_point_id": point["id"] if point else None,
                    "url_hash": hashlib.sha256(candidate.canonical_url.encode("utf-8")).hexdigest(),
                    "search_query": request.topic,
                }
            )
            stored.append(repository.upsert_resource(cursor, user_id, course_id, payload))
        repository.save_cache(
            cursor,
            user_id,
            course_id,
            query_hash,
            request.topic,
            [item["id"] for item in stored],
            degraded,
            warning,
            expires_at,
        )
        items = repository.list_resources_by_ids(
            cursor,
            user_id,
            course_id,
            [item["id"] for item in stored],
        )
        record_audit(
            user_id,
            "COURSE_EXTERNAL_RESOURCES_SEARCHED",
            "course",
            course_id,
            {
                "topic": request.topic,
                "knowledge_point_id": point["id"] if point else None,
                "count": len(items),
                "providers": provider_states,
                "degraded": degraded,
            },
            cursor=cursor,
        )
    return {
        "course_id": course_id,
        "topic": request.topic,
        "knowledge_point": point,
        "resources": [_public_resource(item, point) for item in items],
        "total": len(items),
        "cached": False,
        "degraded": degraded,
        "warning": warning,
        "providers": provider_states,
    }


def list_external_resources(user_id: int, course_id: int) -> dict:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        items = repository.list_course_resources(cursor, user_id, course_id)
        record_audit(
            user_id,
            "COURSE_EXTERNAL_RESOURCES_VIEWED",
            "course",
            course_id,
            {"count": len(items)},
            cursor=cursor,
        )
    return {
        "items": [_public_resource(item) for item in items],
        "total": len(items),
    }


def record_resource_interaction(
    user_id: int,
    course_id: int,
    resource_id: int,
    request: ResourceInteractionRequest,
) -> dict:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        resource = repository.get_resource(cursor, resource_id, user_id, course_id)
        if resource is None:
            raise AppError("外部资源不存在或无访问权限", 404, "EXTERNAL_RESOURCE_NOT_FOUND")
        repository.add_interaction(
            cursor,
            resource_id,
            user_id,
            course_id,
            request.interaction_type,
            request.value,
        )
        updated = repository.list_resources_by_ids(cursor, user_id, course_id, [resource_id])[0]
        record_audit(
            user_id,
            "COURSE_RESOURCE_INTERACTION_RECORDED",
            "external_resource",
            resource_id,
            {"course_id": course_id, "interaction_type": request.interaction_type},
            cursor=cursor,
        )
    return _public_resource(updated)


def check_resource_availability(user_id: int, course_id: int, resource_id: int) -> dict:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        resource = repository.get_resource(cursor, resource_id, user_id, course_id)
    if resource is None:
        raise AppError("外部资源不存在或无访问权限", 404, "EXTERNAL_RESOURCE_NOT_FOUND")
    available = False
    status_code = None
    try:
        response = requests.head(
            resource["canonical_url"],
            allow_redirects=True,
            timeout=get_settings().external_resource_timeout_seconds,
            headers={"User-Agent": "Mozilla/5.0 A3CourseCoach/1.0"},
        )
        status_code = response.status_code
        available = response.status_code < 400 or response.status_code in {401, 403, 405}
    except requests.RequestException:
        available = False
    with get_cursor() as cursor:
        repository.update_resource_status(
            cursor,
            resource_id,
            user_id,
            course_id,
            "active" if available else "unavailable",
        )
        record_audit(
            user_id,
            "COURSE_RESOURCE_AVAILABILITY_CHECKED",
            "external_resource",
            resource_id,
            {"course_id": course_id, "available": available, "status_code": status_code},
            cursor=cursor,
        )
    return {"resource_id": resource_id, "available": available, "status_code": status_code}
