from main import app
from utils import get_current_user


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
        json={"daily_minutes": 45, "status": "preparing"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["daily_minutes"] == 45
    assert updated.json()["data"]["status"] == "preparing"

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


def test_legacy_errors_use_real_http_status(api_client):
    response = api_client.get("/tasks?page=0&size=10")

    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_empty_course_update_is_rejected(api_client):
    course = _create_course(api_client, "更新校验课程")
    response = api_client.patch(f"/api/v1/courses/{course['id']}", json={})

    assert response.status_code == 422
