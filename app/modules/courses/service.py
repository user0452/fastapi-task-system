from sqlalchemy import update

from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.time_utils import to_utc_naive
from app.models import reflected_model
from app.modules.account.service import get_user_timezone
from app.modules.agent import repository as agent_repository
from app.modules.audit.service import record_audit
from app.modules.courses import repository
from app.modules.courses.schemas import CourseCreate, CourseUpdate
from app.modules.roadmaps import service as roadmap_service

COURSE_STATUS_TRANSITIONS = {
    "draft": {"preparing", "archived"},
    "preparing": {"diagnostic_pending", "archived"},
    "diagnostic_pending": {"active", "archived"},
    "active": {"completed", "archived"},
    "completed": {"archived"},
    "archived": set(),
}

MATERIAL_PROCESSING_STATUS = {
    "draft": {False: "preparing", True: "diagnostic_pending"},
    "preparing": {False: "preparing", True: "diagnostic_pending"},
    "diagnostic_pending": {False: "diagnostic_pending", True: "diagnostic_pending"},
    "active": {False: "active", True: "active"},
    "completed": {False: "completed", True: "completed"},
}


def _ensure_course_accepts_material_processing(course: dict) -> dict:
    if course.get("status") == "archived":
        raise AppError(
            "归档课程禁止上传或处理资料",
            409,
            "ARCHIVED_COURSE_MATERIALS_FORBIDDEN",
        )
    return course


def get_material_writable_course(user_id: int, course_id: int) -> dict:
    with get_cursor() as cursor:
        course = repository.get_course(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        return _ensure_course_accepts_material_processing(course)


def lock_course_for_material_processing(cursor, user_id: int, course_id: int) -> dict:
    course = repository.get_course_for_update(cursor, course_id, user_id)
    if course is None:
        raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
    return _ensure_course_accepts_material_processing(course)


def reconcile_course_after_material_processing(
    cursor,
    user_id: int,
    course_id: int,
    *,
    has_enough_knowledge: bool,
) -> dict:
    course = lock_course_for_material_processing(cursor, user_id, course_id)
    current_status = str(course["status"])
    target_status = MATERIAL_PROCESSING_STATUS[current_status][bool(has_enough_knowledge)]
    if target_status == current_status:
        return course
    updated = repository.transition_course_status(
        cursor,
        course_id,
        user_id,
        target_status,
    )
    if updated is None:
        raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
    record_audit(
        user_id,
        "COURSE_MATERIAL_READINESS_CHANGED",
        "course",
        course_id,
        {"from": current_status, "to": target_status},
        cursor=cursor,
    )
    return updated


def list_user_courses(user_id: int, include_archived: bool = False) -> list[dict]:
    with get_cursor() as cursor:
        courses = repository.list_courses(cursor, user_id, include_archived)
        roadmap_service.attach_summaries(cursor, user_id, courses)
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
        roadmap_service.attach_summary(cursor, user_id, course)
        record_audit(user_id, "COURSE_VIEWED", "course", course_id, cursor=cursor)
        return course


def get_user_current_course(user_id: int) -> dict | None:
    with get_cursor() as cursor:
        course = repository.get_current_course(cursor, user_id)
        if course is not None:
            roadmap_service.attach_summary(cursor, user_id, course)
        record_audit(
            user_id,
            "CURRENT_COURSE_VIEWED",
            "course",
            course["id"] if course else None,
            cursor=cursor,
        )
        return course


def create_user_course(user_id: int, request: CourseCreate) -> dict:
    data = request.model_dump()
    data["exam_at"] = to_utc_naive(data.get("exam_at"), get_user_timezone(user_id))
    with get_cursor() as cursor:
        if not repository.lock_user(cursor, user_id):
            raise AppError("用户不存在", 404, "USER_NOT_FOUND")
        current = repository.get_current_course(cursor, user_id)
        course = repository.create_course(
            cursor,
            user_id,
            data,
            is_current=current is None,
        )
        agent_repository.ensure_course_agent(cursor, user_id, course)
        roadmap_service.initialize_course_roadmap(cursor, user_id, course)
        roadmap_service.attach_summary(cursor, user_id, course)
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
    changes = request.model_dump(exclude_unset=True)
    if "exam_at" in changes:
        changes["exam_at"] = to_utc_naive(
            changes["exam_at"],
            get_user_timezone(user_id),
        )
    with get_cursor() as cursor:
        previous_course = repository.get_course_for_update(cursor, course_id, user_id)
        if previous_course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        changed_fields = {
            field
            for field, value in changes.items()
            if previous_course.get(field) != value
        }
        if changed_fields:
            course = repository.update_course(
                cursor,
                course_id,
                user_id,
                {field: changes[field] for field in changed_fields},
            )
            if course is None:
                raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        else:
            course = previous_course
        agent_repository.ensure_course_agent(cursor, user_id, course)
        roadmap_service.refresh_course_snapshot(
            cursor,
            user_id,
            course,
            changed_fields,
            previous_course,
        )
        roadmap_service.attach_summary(cursor, user_id, course)
        record_audit(
            user_id,
            "COURSE_UPDATED",
            "course",
            course_id,
            {"fields": sorted(changed_fields)},
            cursor=cursor,
        )
        return course


def select_user_course(user_id: int, course_id: int) -> dict:
    with get_cursor() as cursor:
        if not repository.lock_user(cursor, user_id):
            raise AppError("用户不存在", 404, "USER_NOT_FOUND")
        course = repository.set_current_course(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在、已归档或无访问权限", 404, "COURSE_NOT_FOUND")
        agent_repository.ensure_course_agent(cursor, user_id, course)
        roadmap_service.attach_summary(cursor, user_id, course)
        record_audit(user_id, "COURSE_SELECTED", "course", course_id, cursor=cursor)
        return course


def transition_user_course(user_id: int, course_id: int, target_status: str) -> dict:
    if target_status == "archived":
        return archive_user_course(user_id, course_id)
    with get_cursor() as cursor:
        if not repository.lock_user(cursor, user_id):
            raise AppError("用户不存在", 404, "USER_NOT_FOUND")
        course = repository.get_course_for_update(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        current_status = str(course["status"])
        if target_status == current_status:
            return course
        if target_status not in COURSE_STATUS_TRANSITIONS.get(current_status, set()):
            raise AppError(
                f"课程不能从 {current_status} 转换为 {target_status}",
                409,
                "COURSE_STATUS_TRANSITION_INVALID",
            )
        updated = repository.transition_course_status(
            cursor,
            course_id,
            user_id,
            target_status,
        )
        if updated is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        agent_repository.ensure_course_agent(cursor, user_id, updated)
        record_audit(
            user_id,
            "COURSE_STATUS_CHANGED",
            "course",
            course_id,
            {"from": current_status, "to": target_status},
            cursor=cursor,
        )
        return updated


def complete_user_course(user_id: int, course_id: int) -> dict:
    return transition_user_course(user_id, course_id, "completed")


def archive_user_course(user_id: int, course_id: int) -> dict:
    with get_cursor() as cursor:
        if not repository.lock_user(cursor, user_id):
            raise AppError("用户不存在", 404, "USER_NOT_FOUND")
        course = repository.get_course_for_update(cursor, course_id, user_id)
        if course is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        if course["status"] == "archived":
            return course
        archived = repository.transition_course_status(
            cursor,
            course_id,
            user_id,
            "archived",
        )
        if archived is None:
            raise AppError("课程不存在或无访问权限", 404, "COURSE_NOT_FOUND")
        CourseAgent = reflected_model("course_agents")
        cursor.session.execute(
            update(CourseAgent)
            .where(CourseAgent.course_id == course_id, CourseAgent.user_id == user_id)
            .values(status="archived")
        )
        record_audit(user_id, "COURSE_ARCHIVED", "course", course_id, cursor=cursor)
        if course.get("is_current"):
            remaining = repository.list_courses(cursor, user_id)
            if remaining:
                repository.set_current_course(cursor, remaining[0]["id"], user_id)
        return archived
