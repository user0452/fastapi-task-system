from datetime import datetime, timezone

from app.core.database import get_cursor
from app.modules.account.service import (
    get_user_local_date,
    update_user_timezone,
)
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course


def test_account_timezone_can_be_read_and_updated(api_client, two_users):
    user, _ = two_users

    current = api_client.get("/api/v1/account/settings")
    assert current.status_code == 200
    assert current.json()["data"]["timezone"] == "Asia/Shanghai"

    invalid = api_client.patch(
        "/api/v1/account/settings",
        json={"timezone": "Mars/Olympus"},
    )
    assert invalid.status_code == 422

    updated = api_client.patch(
        "/api/v1/account/settings",
        json={"timezone": "America/Los_Angeles"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["timezone"] == "America/Los_Angeles"

    with get_cursor() as cursor:
        cursor.execute("SELECT timezone FROM users WHERE id = %s", (user["id"],))
        assert cursor.fetchone()["timezone"] == "America/Los_Angeles"


def test_user_local_date_uses_iana_timezone(two_users):
    user, _ = two_users
    instant = datetime(2026, 7, 16, 16, 30, tzinfo=timezone.utc)

    update_user_timezone(user["id"], "Asia/Shanghai")
    assert get_user_local_date(user["id"], instant).isoformat() == "2026-07-17"

    update_user_timezone(user["id"], "America/Los_Angeles")
    assert get_user_local_date(user["id"], instant).isoformat() == "2026-07-16"


def test_naive_exam_time_is_stored_as_utc(two_users):
    user, _ = two_users
    update_user_timezone(user["id"], "America/Los_Angeles")

    course = create_user_course(
        user["id"],
        CourseCreate(
            name="UTC 考试课程",
            exam_at=datetime(2026, 7, 20, 0, 30),
        ),
    )

    assert course["exam_at"] == datetime(2026, 7, 20, 7, 30)


def test_database_sessions_are_utc():
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT @@session.time_zone AS timezone_name,
                   TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW()) AS utc_delta
            """
        )
        row = cursor.fetchone()

    assert row["timezone_name"] == "+00:00"
    assert abs(int(row["utc_delta"])) <= 1


def test_malformed_profile_json_returns_controlled_error(api_client, two_users):
    user, _ = two_users
    with get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO student_profiles (user_id, profile_json) VALUES (%s, %s)",
            (user["id"], "{not-json"),
        )

    response = api_client.get("/api/v1/account/profile")

    assert response.status_code == 422
    assert response.json()["error_code"] == "PROFILE_DATA_INVALID"
