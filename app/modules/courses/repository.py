"""Course persistence implemented with SQLAlchemy ORM expressions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Course, model_as_dict, reflected_model


def _session(cursor: Any) -> Session:
    return cursor.session


def _course_dict(course: Course | None) -> dict | None:
    return model_as_dict(course) if course is not None else None


def list_courses(cursor, user_id: int, include_archived: bool = False) -> list[dict]:
    statement = select(Course).where(Course.user_id == user_id)
    if not include_archived:
        statement = statement.where(Course.status != "archived")
    statement = statement.order_by(Course.is_current.desc(), Course.updated_at.desc(), Course.id.desc())
    return [model_as_dict(course) for course in _session(cursor).scalars(statement)]


def get_course(cursor, course_id: int, user_id: int) -> dict | None:
    course = _session(cursor).scalar(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    return _course_dict(course)


def get_course_for_update(cursor, course_id: int, user_id: int) -> dict | None:
    course = _session(cursor).scalar(
        select(Course)
        .where(Course.id == course_id, Course.user_id == user_id)
        .with_for_update()
    )
    return _course_dict(course)


def get_current_course(cursor, user_id: int) -> dict | None:
    course = _session(cursor).scalar(
        select(Course)
        .where(
            Course.user_id == user_id,
            Course.is_current.is_(True),
            Course.status != "archived",
        )
        .order_by(Course.updated_at.desc())
        .limit(1)
    )
    return _course_dict(course)


def lock_user(cursor, user_id: int) -> bool:
    User = reflected_model("users")
    user = _session(cursor).scalar(
        select(User.id).where(User.id == user_id).with_for_update()
    )
    return user is not None


def create_course(cursor, user_id: int, data: dict, is_current: bool) -> dict:
    session = _session(cursor)
    course = Course(
        user_id=user_id,
        name=data["name"],
        goal=data.get("goal", ""),
        exam_at=data.get("exam_at"),
        daily_minutes=data.get("daily_minutes", 30),
        status="draft",
        is_current=is_current,
    )
    session.add(course)
    session.flush()
    session.refresh(course)
    return model_as_dict(course)


def update_course(cursor, course_id: int, user_id: int, changes: dict) -> dict | None:
    session = _session(cursor)
    course = session.scalar(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    if course is None:
        return None
    for field, value in changes.items():
        if field in {"name", "goal", "exam_at", "daily_minutes"}:
            setattr(course, field, value)
    session.flush()
    session.refresh(course)
    return model_as_dict(course)


def set_current_course(cursor, course_id: int, user_id: int) -> dict | None:
    session = _session(cursor)
    course = session.scalar(
        select(Course)
        .where(Course.id == course_id, Course.user_id == user_id, Course.status != "archived")
        .with_for_update()
    )
    if course is None:
        return None
    session.execute(update(Course).where(Course.user_id == user_id).values(is_current=False))
    course.is_current = True
    session.flush()
    session.refresh(course)
    return model_as_dict(course)


def transition_course_status(
    cursor,
    course_id: int,
    user_id: int,
    status: str,
) -> dict | None:
    session = _session(cursor)
    course = session.scalar(
        select(Course).where(Course.id == course_id, Course.user_id == user_id).with_for_update()
    )
    if course is None:
        return None
    course.status = status
    if status == "archived":
        course.is_current = False
    session.flush()
    session.refresh(course)
    return model_as_dict(course)
