from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import get_cursor
from app.modules.auth.dependencies import get_current_user
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course
from main import app


def _create_course(client, name: str):
    response = client.post(
        "/api/v1/courses",
        json={
            "name": name,
            "goal": "通过课程冲刺掌握核心知识点",
            "daily_minutes": 30,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["code"] == 201
    return payload["data"]


def test_course_lifecycle_and_current_selection(api_client):
    first = _create_course(api_client, "课程一")
    second = _create_course(api_client, "课程二")

    assert first["is_current"] == 1
    assert second["is_current"] == 0

    response = api_client.post(f"/api/v1/courses/{second['id']}/select")
    assert response.status_code == 200
    assert response.json()["data"]["is_current"] == 1

    current = api_client.get("/api/v1/courses/current")
    assert current.status_code == 200
    assert current.json()["data"]["id"] == second["id"]

    updated = api_client.patch(
        f"/api/v1/courses/{second['id']}",
        json={"daily_minutes": 45},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["daily_minutes"] == 45

    preparing = api_client.post(
        f"/api/v1/courses/{second['id']}/status",
        json={"status": "preparing"},
    )
    assert preparing.status_code == 200
    assert preparing.json()["data"]["status"] == "preparing"

    archived = api_client.delete(f"/api/v1/courses/{second['id']}?confirmed=true")
    assert archived.status_code == 200

    new_current = api_client.get("/api/v1/courses/current")
    assert new_current.status_code == 200
    assert new_current.json()["data"]["id"] == first["id"]


def test_course_list_hides_archived_by_default(api_client):
    course = _create_course(api_client, "待归档课程")
    api_client.delete(f"/api/v1/courses/{course['id']}?confirmed=true")

    active = api_client.get("/api/v1/courses")
    archived = api_client.get("/api/v1/courses?include_archived=true")

    assert active.status_code == 200
    assert all(item["id"] != course["id"] for item in active.json()["data"]["items"])
    assert any(item["id"] == course["id"] for item in archived.json()["data"]["items"])


def test_course_access_is_isolated_between_users(api_client, two_users):
    first_user, second_user = two_users
    course = _create_course(api_client, "用户一课程")

    app.dependency_overrides[get_current_user] = lambda: second_user
    attempts = [
        api_client.get(f"/api/v1/courses/{course['id']}"),
        api_client.patch(f"/api/v1/courses/{course['id']}", json={"name": "越权修改"}),
        api_client.post(f"/api/v1/courses/{course['id']}/select"),
        api_client.post(
            f"/api/v1/courses/{course['id']}/status",
            json={"status": "preparing"},
        ),
        api_client.post(f"/api/v1/courses/{course['id']}/complete"),
        api_client.post(
            f"/api/v1/courses/{course['id']}/archive",
            json={"confirmed": True},
        ),
        api_client.delete(f"/api/v1/courses/{course['id']}?confirmed=true"),
        api_client.get(f"/api/v1/courses/{course['id']}/materials"),
    ]

    assert all(response.status_code == 404 for response in attempts)
    assert all(response.json().get("error_code") == "COURSE_NOT_FOUND" for response in attempts)

    app.dependency_overrides[get_current_user] = lambda: first_user
    owner_view = api_client.get(f"/api/v1/courses/{course['id']}")
    assert owner_view.status_code == 200
    assert owner_view.json()["data"]["name"] == "用户一课程"
    assert owner_view.json()["data"]["status"] == "draft"


def test_retired_legacy_route_is_absent(api_client):
    response = api_client.get("/tasks?page=0&size=10")

    assert response.status_code == 404


def test_empty_course_update_is_rejected(api_client):
    course = _create_course(api_client, "更新校验课程")
    response = api_client.patch(f"/api/v1/courses/{course['id']}", json={})

    assert response.status_code == 422


def test_generic_course_patch_rejects_status(api_client):
    course = _create_course(api_client, "状态命令课程")
    response = api_client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"daily_minutes": 50, "status": "completed"},
    )

    assert response.status_code == 422
    stored = api_client.get(f"/api/v1/courses/{course['id']}").json()["data"]
    assert stored["daily_minutes"] == 30
    assert stored["status"] == "draft"


def test_course_status_commands_enforce_transition_graph(api_client):
    course = _create_course(api_client, "状态流转课程")

    invalid = api_client.post(
        f"/api/v1/courses/{course['id']}/complete",
    )
    assert invalid.status_code == 409
    assert invalid.json()["error_code"] == "COURSE_STATUS_TRANSITION_INVALID"

    for target in ("preparing", "diagnostic_pending", "active"):
        response = api_client.post(
            f"/api/v1/courses/{course['id']}/status",
            json={"status": target},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == target

    completed = api_client.post(f"/api/v1/courses/{course['id']}/complete")
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "completed"

    confirmation = api_client.post(
        f"/api/v1/courses/{course['id']}/archive",
        json={"confirmed": False},
    )
    assert confirmation.status_code == 409
    archived = api_client.post(
        f"/api/v1/courses/{course['id']}/archive",
        json={"confirmed": True},
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"


def test_concurrent_first_course_creation_keeps_exactly_one_current(two_users):
    user, _ = two_users
    workers = 6
    barrier = Barrier(workers)

    def create(index: int):
        barrier.wait()
        return create_user_course(
            user["id"],
            CourseCreate(name=f"并发课程 {index}"),
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(create, range(workers)))

    assert sum(bool(item["is_current"]) for item in results) == 1
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM courses WHERE user_id = %s AND is_current = TRUE",
            (user["id"],),
        )
        assert cursor.fetchone()["total"] == 1


def test_database_rejects_two_current_courses_for_one_user(api_client, two_users):
    user, _ = two_users
    first = _create_course(api_client, "唯一当前课程一")
    second = _create_course(api_client, "唯一当前课程二")

    with pytest.raises(IntegrityError):
        with get_cursor() as cursor:
            cursor.execute(
                "UPDATE courses SET is_current = TRUE WHERE id IN (%s, %s) AND user_id = %s",
                (first["id"], second["id"], user["id"]),
            )
