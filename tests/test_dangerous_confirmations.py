import pytest

from app.core.database import get_cursor
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course, get_user_course
from routers.agent import _execute_agent_tools


def test_direct_task_delete_requires_confirmation(api_client, two_users):
    user, _ = two_users
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO tasks (user_id, title, description, status, priority)
            VALUES (%s, '需要确认的任务', '', 'todo', 'medium')
            """,
            (user["id"],),
        )
        task_id = cursor.lastrowid

    blocked = api_client.delete(f"/tasks/{task_id}")
    assert blocked.status_code == 409
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE id = %s", (task_id,))
        assert cursor.fetchone()["total"] == 1

    confirmed = api_client.delete(f"/tasks/{task_id}?confirmed=true")
    assert confirmed.status_code == 200
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE id = %s", (task_id,))
        assert cursor.fetchone()["total"] == 0


def test_course_archive_requires_confirmation(api_client, two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="确认归档课程"))

    blocked = api_client.delete(f"/api/v1/courses/{course['id']}")
    assert blocked.status_code == 409
    assert get_user_course(user["id"], course["id"])["status"] == "draft"

    confirmed = api_client.delete(f"/api/v1/courses/{course['id']}?confirmed=true")
    assert confirmed.status_code == 200
    assert get_user_course(user["id"], course["id"])["status"] == "archived"


def test_bulk_ai_command_never_changes_data_without_controlled_confirmation(api_client, two_users):
    user, _ = two_users
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO tasks (user_id, title, description, status, priority)
            VALUES (%s, '批量安全测试', '', 'done', 'medium')
            """,
            (user["id"],),
        )
        task_id = cursor.lastrowid

    response = api_client.post("/ai/command", json={"text": "删除所有done任务"})

    assert response.status_code == 409
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE id = %s", (task_id,))
        assert cursor.fetchone()["total"] == 1


def test_memory_deletion_and_bulk_forget_require_confirmation(api_client):
    delete_response = api_client.delete("/memories/999999")
    forget_response = api_client.post("/memories/forget-old?days=90")

    assert delete_response.status_code == 409
    assert forget_response.status_code == 409


def test_legacy_agent_returns_confirmation_without_touching_cursor():
    class Cursor:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("legacy destructive tool must not execute SQL")

    runner = _execute_agent_tools(
        {
            "tools": ["delete_task"],
            "tool_args": {"delete_task": {"task_id": 12}},
        },
        Cursor(),
        {"id": 7},
        None,
        "删除任务 12",
    )

    event = next(runner)
    assert "二次确认" in event["message"]
    with pytest.raises(StopIteration) as stopped:
        next(runner)
    result = stopped.value.value
    assert result["confirmation_required"]["executed"] is False
