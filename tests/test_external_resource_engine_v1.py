from datetime import datetime

import pytest

from app.core.database import get_cursor
from app.core.errors import AppError
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course
from app.modules.resources.providers import ResourceCandidate, canonicalize_url
from app.modules.resources.schemas import ExternalResourceSearchRequest, ResourceInteractionRequest
from app.modules.resources.service import (
    check_resource_availability,
    list_external_resources,
    record_resource_interaction,
    search_external_resources,
)


class FakeProvider:
    def __init__(self, name: str, candidates: list[ResourceCandidate]):
        self.name = name
        self.candidates = candidates
        self.calls = 0

    def search(self, _course_name, _topic, max_results):
        self.calls += 1
        return self.candidates[:max_results]


def _candidate(provider: str, resource_id: str, url: str, title: str) -> ResourceCandidate:
    return ResourceCandidate(
        provider=provider,
        provider_resource_id=resource_id,
        resource_type="video",
        canonical_url=url,
        title=title,
        author="课程讲师",
        summary="课程知识点视频讲解",
        thumbnail_url=f"https://img.example.com/{resource_id}.jpg",
        duration_seconds=600,
        published_at=datetime(2026, 1, 1),
        relevance_score=0.9,
        quality_score=0.8,
    )


def test_provider_fallback_deduplicates_caches_and_records_interactions(two_users):
    user, other_user = two_users
    course = create_user_course(user["id"], CourseCreate(name="外部资源课程"))
    primary = FakeProvider(
        "bilibili",
        [
            _candidate("bilibili", "BV1", "https://www.bilibili.com/video/BV1?utm_source=test", "知识点入门"),
            _candidate("bilibili", "BV2", "https://www.bilibili.com/video/BV2", "知识点案例"),
        ],
    )
    fallback = FakeProvider(
        "tavily",
        [
            _candidate("bilibili", "BV1", "https://bilibili.com/video/BV1", "重复视频"),
            _candidate("youtube", "abcdefghijk", "https://youtube.com/watch?v=abcdefghijk&utm_source=x", "知识点详解"),
            _candidate("youtube", "lmnopqrstuv", "https://youtu.be/lmnopqrstuv", "知识点练习"),
        ],
    )
    request = ExternalResourceSearchRequest(topic="知识点", max_results=4)

    first = search_external_resources(
        user["id"],
        course["id"],
        request,
        providers=[primary],
        fallback_provider=fallback,
    )
    second = search_external_resources(
        user["id"],
        course["id"],
        request,
        providers=[primary],
        fallback_provider=fallback,
    )

    assert 3 <= first["total"] <= 4
    assert len({item["canonical_url"] for item in first["resources"]}) == first["total"]
    assert first["cached"] is False
    assert second["cached"] is True
    assert primary.calls == 1
    assert fallback.calls == 1
    resource = first["resources"][0]

    saved = record_resource_interaction(
        user["id"],
        course["id"],
        resource["id"],
        ResourceInteractionRequest(interaction_type="saved"),
    )
    completed = record_resource_interaction(
        user["id"],
        course["id"],
        resource["id"],
        ResourceInteractionRequest(interaction_type="completed"),
    )
    record_resource_interaction(
        user["id"],
        course["id"],
        resource["id"],
        ResourceInteractionRequest(interaction_type="opened"),
    )
    helpful = record_resource_interaction(
        user["id"],
        course["id"],
        resource["id"],
        ResourceInteractionRequest(interaction_type="helpful"),
    )

    assert saved["interaction"]["saved"] is True
    assert completed["interaction"]["completed"] is True
    assert helpful["interaction"]["helpful"] is True
    restored = list_external_resources(user["id"], course["id"])["items"]
    restored_item = next(item for item in restored if item["id"] == resource["id"])
    assert restored_item["interaction"] == {
        "saved": True,
        "completed": True,
        "helpful": True,
        "opened_count": 1,
    }

    with pytest.raises(AppError):
        record_resource_interaction(
            other_user["id"],
            course["id"],
            resource["id"],
            ResourceInteractionRequest(interaction_type="saved"),
        )
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM external_resources WHERE user_id = %s AND course_id = %s",
            (user["id"], course["id"]),
        )
        assert cursor.fetchone()["total"] == first["total"]


def test_video_urls_are_canonicalized_without_tracking_parameters():
    assert canonicalize_url("http://www.youtube.com/watch?v=abcdefghijk&utm_source=x&feature=share") == (
        "https://youtube.com/watch?v=abcdefghijk"
    )
    assert canonicalize_url("https://www.bilibili.com/video/BV123?spm_id_from=333") == (
        "https://bilibili.com/video/BV123"
    )
    assert canonicalize_url("javascript:alert(1)") is None


def test_resource_availability_updates_status_checks_owner_and_audits(two_users, monkeypatch):
    user, other_user = two_users
    course = create_user_course(user["id"], CourseCreate(name="资源有效性课程"))
    provider = FakeProvider(
        "youtube",
        [_candidate("youtube", "abcdefghijk", "https://youtube.com/watch?v=abcdefghijk", "有效性视频")],
    )
    found = search_external_resources(
        user["id"],
        course["id"],
        ExternalResourceSearchRequest(topic="有效性视频", max_results=3),
        providers=[provider],
        fallback_provider=FakeProvider("empty", []),
    )["resources"][0]

    monkeypatch.setattr(
        "app.modules.resources.service.requests.head",
        lambda *_args, **_kwargs: type("Response", (), {"status_code": 404})(),
    )
    unavailable = check_resource_availability(user["id"], course["id"], found["id"])
    assert unavailable == {"resource_id": found["id"], "available": False, "status_code": 404}
    assert list_external_resources(user["id"], course["id"])["items"] == []
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT status FROM external_resources WHERE id = %s AND user_id = %s",
            (found["id"], user["id"]),
        )
        assert cursor.fetchone()["status"] == "unavailable"

    monkeypatch.setattr(
        "app.modules.resources.service.requests.head",
        lambda *_args, **_kwargs: type("Response", (), {"status_code": 405})(),
    )
    available = check_resource_availability(user["id"], course["id"], found["id"])
    assert available["available"] is True
    assert list_external_resources(user["id"], course["id"])["items"][0]["validity_status"] == "active"

    with pytest.raises(AppError) as denied:
        check_resource_availability(other_user["id"], course["id"], found["id"])
    assert denied.value.status_code == 404
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM operation_logs
            WHERE user_id = %s AND action = 'COURSE_RESOURCE_AVAILABILITY_CHECKED'
              AND target_id = %s
            """,
            (user["id"], found["id"]),
        )
        assert cursor.fetchone()["total"] == 2
