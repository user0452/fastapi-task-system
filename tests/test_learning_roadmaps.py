from app.core.database import get_cursor
from app.modules.roadmaps.service import (
    adjust_roadmap_for_evaluation,
    get_learning_roadmap,
)
from main import app
from utils import get_current_user


def _create_course(client, name: str = "路线图课程") -> dict:
    response = client.post(
        "/api/v1/courses",
        json={
            "name": name,
            "goal": "在六周内掌握核心方法并完成综合练习",
            "daily_minutes": 35,
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def test_course_creation_generates_idempotent_staged_roadmap(api_client):
    course = _create_course(api_client)
    assert course["roadmap_summary"]["status"] == "ready"
    assert course["roadmap_summary"]["stage_total"] == 4

    first = api_client.get(f"/api/v1/courses/{course['id']}/roadmap")
    second = api_client.get(f"/api/v1/courses/{course['id']}/roadmap")

    assert first.status_code == 200
    roadmap = first.json()["data"]
    repeated = second.json()["data"]
    assert roadmap["status"] == "ready"
    assert roadmap["generation_method"] == "rules_v1"
    assert roadmap["generation_job"]["status"] == "ready"
    assert [stage["position"] for stage in roadmap["stages"]] == [1, 2, 3, 4]
    assert roadmap["stages"][0]["status"] == "active"
    assert "六周内掌握核心方法" in roadmap["stages"][0]["goal"]
    assert [stage["id"] for stage in repeated["stages"]] == [
        stage["id"] for stage in roadmap["stages"]
    ]

    listed = api_client.get("/api/v1/courses").json()["data"]["items"]
    listed_course = next(item for item in listed if item["id"] == course["id"])
    assert listed_course["roadmap_summary"]["current_stage_name"] == "目标定标与基础诊断"


def test_roadmap_access_is_course_and_user_scoped(api_client, two_users):
    first_user, second_user = two_users
    course = _create_course(api_client, "隔离路线图")

    app.dependency_overrides[get_current_user] = lambda: second_user
    response = api_client.get(f"/api/v1/courses/{course['id']}/roadmap")
    retry = api_client.post(
        f"/api/v1/courses/{course['id']}/roadmap/retry",
        json={"reason": "越权尝试"},
    )
    assert response.status_code == 404
    assert retry.status_code == 404

    app.dependency_overrides[get_current_user] = lambda: first_user
    assert api_client.get(f"/api/v1/courses/{course['id']}/roadmap").status_code == 200


def test_failed_generation_can_be_retried_with_a_new_durable_job(api_client):
    course = _create_course(api_client, "重试路线图")
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE learning_roadmaps
            SET status = 'failed', last_error = '测试故障'
            WHERE course_id = %s
            """,
            (course["id"],),
        )

    response = api_client.post(
        f"/api/v1/courses/{course['id']}/roadmap/retry",
        json={"reason": "恢复测试故障"},
    )
    assert response.status_code == 200
    roadmap = response.json()["data"]
    assert roadmap["status"] == "ready"
    assert roadmap["version"] == 2
    assert roadmap["generation_job"]["attempt"] == 2
    assert roadmap["generation_job"]["status"] == "ready"


def test_evaluation_adjustment_links_real_points_and_is_idempotent(api_client, two_users):
    user, _ = two_users
    course = _create_course(api_client, "动态路线图")
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO knowledge_points
                (user_id, course_id, name, description, sort_order)
            VALUES (%s, %s, '核心概念一', '真实知识点一', 1),
                   (%s, %s, '核心概念二', '真实知识点二', 2)
            """,
            (user["id"], course["id"], user["id"], course["id"]),
        )
        cursor.execute(
            "SELECT id FROM knowledge_points WHERE course_id = %s ORDER BY sort_order",
            (course["id"],),
        )
        point_ids = [row["id"] for row in cursor.fetchall()]
        for point_id, mastery in zip(point_ids, (50, 70), strict=True):
            cursor.execute(
                """
                INSERT INTO mastery_records
                    (user_id, course_id, knowledge_point_id, mastery)
                VALUES (%s, %s, %s, %s)
                """,
                (user["id"], course["id"], point_id, mastery),
            )

    get_learning_roadmap(user["id"], course["id"])
    with get_cursor() as cursor:
        payload = {
            "cursor": cursor,
            "user_id": user["id"],
            "course_id": course["id"],
            "trigger_type": "practice",
            "trigger_id": 991,
            "evaluation": {"score": 65},
            "mastery_changes": [
                {"knowledge_point_id": point_ids[0], "after": 50},
                {"knowledge_point_id": point_ids[1], "after": 70},
            ],
        }
        assert adjust_roadmap_for_evaluation(**payload) is True
        assert adjust_roadmap_for_evaluation(**payload) is False

    roadmap = get_learning_roadmap(user["id"], course["id"])
    stages = {stage["position"]: stage for stage in roadmap["stages"]}
    assert stages[1]["status"] == "completed"
    assert stages[2]["status"] == "active"
    assert stages[2]["progress"] == 60
    assert len(stages[2]["knowledge_points"]) == 2
    matching = [item for item in roadmap["adjustments"] if item["trigger_id"] == 991]
    assert len(matching) == 1
