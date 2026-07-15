from app.core.database import get_cursor
from app.core.errors import AppError
from app.modules.agent import repository as agent_repository
from app.modules.audit.service import record_audit
from app.modules.courses import repository
from app.modules.courses.schemas import CourseCreate, CourseUpdate


def list_user_courses(user_id: int, include_archived: bool = False) -> list[dict]:
    with get_cursor() as cursor:
        courses = repository.list_courses(cursor, user_id, include_archived)
        record_audit(
            user_id,
            "COURSES_LISTED",
            "course",
            detail={"count": len(courses), "include_archived": include_archived},
            cursor=cursor,
        )
        return courses


def get_user_course(user_id: int, course_id: int) -> dict:
    with get_cursor() as cursor:
        course = repository.get_course(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        record_audit(user_id, "COURSE_VIEWED", "course", course_id, cursor=cursor)
        return course


def get_user_current_course(user_id: int) -> dict | None:
    with get_cursor() as cursor:
        course = repository.get_current_course(cursor, user_id)
        record_audit(
            user_id,
            "CURRENT_COURSE_VIEWED",
            "course",
            course["id"] if course else None,
            cursor=cursor,
        )
        return course


def create_user_course(user_id: int, request: CourseCreate) -> dict:
    with get_cursor() as cursor:
        current = repository.get_current_course(cursor, user_id)
        course = repository.create_course(
            cursor,
            user_id,
            request.model_dump(),
            is_current=current is None,
        )
        agent_repository.ensure_course_agent(cursor, user_id, course)
        record_audit(
            user_id,
            "COURSE_CREATED",
            "course",
            course["id"],
            {"name": course["name"]},
            cursor=cursor,
        )
        return course


def update_user_course(user_id: int, course_id: int, request: CourseUpdate) -> dict:
    with get_cursor() as cursor:
        if repository.get_course(cursor, course_id, user_id) is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        course = repository.update_course(
            cursor,
            course_id,
            user_id,
            request.model_dump(exclude_unset=True),
        )
        if course is None:
            raise AppError("璇剧▼涓嶅瓨鍦ㄦ垨鏃犺闂潈闄?", 404, "COURSE_NOT_FOUND")
        agent_repository.ensure_course_agent(cursor, user_id, course)
        record_audit(
            user_id,
            "COURSE_UPDATED",
            "course",
            course_id,
            {"fields": sorted(request.model_fields_set)},
            cursor=cursor,
        )
        return course


def select_user_course(user_id: int, course_id: int) -> dict:
    with get_cursor() as cursor:
        course = repository.set_current_course(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在、已归档或无访问权限", 404, "COURSE_NOT_FOUND")
        agent_repository.ensure_course_agent(cursor, user_id, course)
        record_audit(user_id, "COURSE_SELECTED", "course", course_id, cursor=cursor)
        return course


def archive_user_course(user_id: int, course_id: int) -> None:
    with get_cursor() as cursor:
        course = repository.get_course(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        repository.archive_course(cursor, course_id, user_id)
        cursor.execute(
            "UPDATE course_agents SET status = 'archived' WHERE course_id = %s AND user_id = %s",
            (course_id, user_id),
        )
        record_audit(user_id, "COURSE_ARCHIVED", "course", course_id, cursor=cursor)
        if course.get("is_current"):
            remaining = repository.list_courses(cursor, user_id)
            if remaining:
                repository.set_current_course(cursor, remaining[0]["id"], user_id)
