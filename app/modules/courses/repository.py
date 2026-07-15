from typing import Any

COURSE_COLUMNS = """
    id, user_id, name, goal, exam_at, daily_minutes,
    status, is_current, created_at, updated_at
"""


def list_courses(cursor, user_id: int, include_archived: bool = False) -> list[dict]:
    sql = f"SELECT {COURSE_COLUMNS} FROM courses WHERE user_id = %s"
    params: list[Any] = [user_id]
    if not include_archived:
        sql += " AND status <> %s"
        params.append("archived")
    sql += " ORDER BY is_current DESC, updated_at DESC, id DESC"
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def get_course(cursor, course_id: int, user_id: int) -> dict | None:
    cursor.execute(
        f"SELECT {COURSE_COLUMNS} FROM courses WHERE id = %s AND user_id = %s",
        (course_id, user_id),
    )
    return cursor.fetchone()


def get_current_course(cursor, user_id: int) -> dict | None:
    cursor.execute(
        f"""
        SELECT {COURSE_COLUMNS}
        FROM courses
        WHERE user_id = %s AND is_current = TRUE AND status <> 'archived'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (user_id,),
    )
    return cursor.fetchone()


def create_course(cursor, user_id: int, data: dict, is_current: bool) -> dict:
    cursor.execute(
        """
        INSERT INTO courses
            (user_id, name, goal, exam_at, daily_minutes, status, is_current)
        VALUES (%s, %s, %s, %s, %s, 'draft', %s)
        """,
        (
            user_id,
            data["name"],
            data.get("goal", ""),
            data.get("exam_at"),
            data.get("daily_minutes", 30),
            is_current,
        ),
    )
    course = get_course(cursor, cursor.lastrowid, user_id)
    if course is None:
        raise RuntimeError("course insert succeeded but the row could not be reloaded")
    return course


def update_course(cursor, course_id: int, user_id: int, changes: dict) -> dict | None:
    allowed = {"name", "goal", "exam_at", "daily_minutes", "status"}
    updates = []
    values = []
    for field, value in changes.items():
        if field in allowed:
            updates.append(f"{field} = %s")
            values.append(value)
    if not updates:
        return get_course(cursor, course_id, user_id)
    values.extend([course_id, user_id])
    cursor.execute(
        f"UPDATE courses SET {', '.join(updates)} WHERE id = %s AND user_id = %s",
        values,
    )
    return get_course(cursor, course_id, user_id)


def set_current_course(cursor, course_id: int, user_id: int) -> dict | None:
    cursor.execute("UPDATE courses SET is_current = FALSE WHERE user_id = %s", (user_id,))
    cursor.execute(
        """
        UPDATE courses
        SET is_current = TRUE
        WHERE id = %s AND user_id = %s AND status <> 'archived'
        """,
        (course_id, user_id),
    )
    if cursor.rowcount == 0:
        return None
    return get_course(cursor, course_id, user_id)


def archive_course(cursor, course_id: int, user_id: int) -> bool:
    cursor.execute(
        """
        UPDATE courses
        SET status = 'archived', is_current = FALSE
        WHERE id = %s AND user_id = %s
        """,
        (course_id, user_id),
    )
    return cursor.rowcount > 0
