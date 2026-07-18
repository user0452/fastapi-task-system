from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest

from app.core.database import get_cursor
from app.modules.account.service import get_user_local_date
from app.modules.courses.schemas import CourseUpdate
from app.modules.courses.service import (
    get_user_current_course,
    list_user_courses,
    update_user_course,
)
from app.modules.roadmaps import repository as roadmap_repository
from app.modules.roadmaps.service import (
    _allocate_stage_days,
    adjust_roadmap_for_evaluation,
    calculate_overall_progress,
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


def test_course_list_and_current_initialize_missing_roadmap_concurrently(
    api_client,
    two_users,
):
    user, _ = two_users
    course = _create_course(api_client, "并发初始化路线图")
    with get_cursor() as cursor:
        cursor.execute(
            "DELETE FROM learning_roadmaps WHERE user_id = %s AND course_id = %s",
            (user["id"], course["id"]),
        )

    both_requests_ready = Barrier(2)

    def list_courses_after_barrier():
        both_requests_ready.wait(timeout=5)
        return list_user_courses(user["id"])

    def get_current_after_barrier():
        both_requests_ready.wait(timeout=5)
        return get_user_current_course(user["id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        listed_future = executor.submit(list_courses_after_barrier)
        current_future = executor.submit(get_current_after_barrier)
        listed = listed_future.result(timeout=10)
        current = current_future.result(timeout=10)

    listed_course = next(item for item in listed if item["id"] == course["id"])
    assert current["id"] == course["id"]
    assert listed_course["roadmap_summary"]["status"] == "ready"
    assert current["roadmap_summary"]["status"] == "ready"
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM learning_roadmaps WHERE course_id = %s",
            (course["id"],),
        )
        assert cursor.fetchone()["total"] == 1


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


@pytest.mark.parametrize("total_days", [4, 7, 8, 14, 28, 30])
def test_stage_day_allocator_preserves_the_exact_target_cycle(total_days):
    days = _allocate_stage_days(total_days)

    assert len(days) == 4
    assert all(day >= 1 for day in days)
    assert sum(days) == total_days


def test_stage_day_allocator_does_not_invent_days_for_a_short_cycle():
    assert _allocate_stage_days(1) == [1, 0, 0, 0]
    assert _allocate_stage_days(3) == [1, 1, 1, 0]


def test_missing_and_expired_target_dates_have_explicit_non_negative_cycles(
    api_client,
    two_users,
):
    user, _ = two_users
    course = _create_course(api_client, "目标日期边界")
    initial = api_client.get(f"/api/v1/courses/{course['id']}/roadmap").json()["data"]
    assert sum(stage["estimated_days"] for stage in initial["stages"]) == 28

    expired = get_user_local_date(user["id"]) - timedelta(days=3)
    response = api_client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"exam_at": f"{expired.isoformat()}T12:00:00"},
    )
    assert response.status_code == 200
    refreshed = api_client.get(f"/api/v1/courses/{course['id']}/roadmap").json()["data"]
    days = [stage["estimated_days"] for stage in refreshed["stages"]]
    assert days == [1, 0, 0, 0]
    assert sum(days) == 1


def test_course_goal_update_recalculates_unfinished_stage_content(api_client):
    course = _create_course(api_client, "目标重算")
    before = api_client.get(f"/api/v1/courses/{course['id']}/roadmap").json()["data"]
    response = api_client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"goal": "通过真实项目掌握测试架构"},
    )

    assert response.status_code == 200
    after = api_client.get(f"/api/v1/courses/{course['id']}/roadmap").json()["data"]
    assert [stage["id"] for stage in after["stages"]] == [
        stage["id"] for stage in before["stages"]
    ]
    assert "通过真实项目掌握测试架构" in after["stages"][0]["goal"]
    assert "通过真实项目掌握测试架构" in after["stages"][3]["goal"]
    adjustment = after["adjustments"][0]
    assert adjustment["details"]["changed_fields"] == ["goal"]
    assert adjustment["details"]["before"]["goal"] != adjustment["details"]["after"]["goal"]


def test_exam_date_and_daily_minutes_recalculate_days_and_learning_content(
    api_client,
    two_users,
):
    user, _ = two_users
    course = _create_course(api_client, "周期重算")
    target = get_user_local_date(user["id"]) + timedelta(days=7)

    date_update = api_client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"exam_at": f"{target.isoformat()}T20:00:00"},
    )
    assert date_update.status_code == 200
    dated = api_client.get(f"/api/v1/courses/{course['id']}/roadmap").json()["data"]
    assert sum(stage["estimated_days"] for stage in dated["stages"]) == 7

    minutes_update = api_client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"daily_minutes": 75},
    )
    assert minutes_update.status_code == 200
    refreshed = api_client.get(f"/api/v1/courses/{course['id']}/roadmap").json()["data"]
    assert refreshed["daily_minutes"] == 75
    assert "每天约 75 分钟" in refreshed["stages"][1]["goal"]


def test_course_update_preserves_completed_stages_mastery_and_stage_links(
    api_client,
    two_users,
):
    user, _ = two_users
    course = _create_course(api_client, "已完成阶段保留")
    roadmap = get_learning_roadmap(user["id"], course["id"])
    stages = {stage["position"]: stage for stage in roadmap["stages"]}
    completed_goal = stages[1]["goal"]
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE learning_roadmap_stages SET status = 'completed', progress = 100 WHERE id = %s",
            (stages[1]["id"],),
        )
        cursor.execute(
            """
            INSERT INTO knowledge_points (user_id, course_id, name, description, sort_order)
            VALUES (%s, %s, '保留知识点', '路线重算不应删除', 1)
            """,
            (user["id"], course["id"]),
        )
        point_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO mastery_records (user_id, course_id, knowledge_point_id, mastery)
            VALUES (%s, %s, %s, 64)
            """,
            (user["id"], course["id"], point_id),
        )
        cursor.execute(
            """
            INSERT INTO roadmap_stage_points
                (stage_id, knowledge_point_id, user_id, course_id, sort_order, required_mastery)
            VALUES (%s, %s, %s, %s, 1, 70)
            """,
            (stages[2]["id"], point_id, user["id"], course["id"]),
        )

    response = api_client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"goal": "新的课程目标"},
    )
    assert response.status_code == 200
    refreshed = get_learning_roadmap(user["id"], course["id"])
    next_stages = {stage["position"]: stage for stage in refreshed["stages"]}
    assert next_stages[1]["id"] == stages[1]["id"]
    assert next_stages[1]["status"] == "completed"
    assert next_stages[1]["progress"] == 100
    assert next_stages[1]["goal"] == completed_goal
    assert next_stages[2]["id"] == stages[2]["id"]
    assert [point["id"] for point in next_stages[2]["knowledge_points"]] == [point_id]
    assert next_stages[2]["knowledge_points"][0]["mastery"] == 64


def test_repeated_course_update_is_idempotent(api_client):
    course = _create_course(api_client, "幂等路线更新")
    first = api_client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"daily_minutes": 55},
    )
    second = api_client.patch(
        f"/api/v1/courses/{course['id']}",
        json={"daily_minutes": 55},
    )

    assert first.status_code == second.status_code == 200
    roadmap = api_client.get(f"/api/v1/courses/{course['id']}/roadmap").json()["data"]
    matching = [
        item
        for item in roadmap["adjustments"]
        if item["trigger_type"] == "course_update"
        and item["details"].get("changed_fields") == ["daily_minutes"]
    ]
    assert len(matching) == 1


def test_failed_course_roadmap_update_rolls_back_course_and_stages(
    api_client,
    two_users,
    monkeypatch,
):
    user, _ = two_users
    course = _create_course(api_client, "路线回滚")
    before = get_learning_roadmap(user["id"], course["id"])
    original = roadmap_repository.update_stage_blueprint
    calls = 0

    def fail_during_update(*args, **kwargs):
        nonlocal calls
        calls += 1
        original(*args, **kwargs)
        if calls == 2:
            raise RuntimeError("模拟路线重算失败")

    monkeypatch.setattr(roadmap_repository, "update_stage_blueprint", fail_during_update)
    with pytest.raises(RuntimeError, match="模拟路线重算失败"):
        update_user_course(
            user["id"],
            course["id"],
            CourseUpdate(goal="不应被保存的新目标"),
        )

    with get_cursor() as cursor:
        cursor.execute("SELECT goal FROM courses WHERE id = %s", (course["id"],))
        assert cursor.fetchone()["goal"] == course["goal"]
    after = get_learning_roadmap(user["id"], course["id"])
    assert [stage["goal"] for stage in after["stages"]] == [
        stage["goal"] for stage in before["stages"]
    ]


def test_overall_progress_prefers_real_session_minutes_and_is_clamped():
    progress = calculate_overall_progress(
        [
            {"progress": 100, "estimated_days": 2, "daily_sessions": []},
            {
                "progress": 50,
                "estimated_days": 10,
                "daily_sessions": [{"estimated_minutes": 120}],
            },
        ],
        daily_minutes=30,
    )
    assert progress == 66.67
    assert calculate_overall_progress(
        [{"progress": -30}, {"progress": 140}],
    ) == 50


def test_course_summary_and_roadmap_share_the_same_overall_progress(api_client):
    course = _create_course(api_client, "统一进度口径")
    with get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE learning_roadmap_stages
            SET progress = CASE position WHEN 1 THEN 100 WHEN 2 THEN 50 ELSE 0 END
            WHERE course_id = %s
            """,
            (course["id"],),
        )

    roadmap = api_client.get(f"/api/v1/courses/{course['id']}/roadmap").json()["data"]
    listed = api_client.get("/api/v1/courses").json()["data"]["items"]
    summary = next(item for item in listed if item["id"] == course["id"])["roadmap_summary"]
    assert summary["overall_progress"] == roadmap["overall_progress"]
