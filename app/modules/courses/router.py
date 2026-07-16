from fastapi import Depends, Query, status

from app.core.errors import AppError
from app.core.responses import V1APIRouter, success
from app.modules.auth.dependencies import get_current_user
from app.modules.courses.schemas import (
    CourseArchiveCommand,
    CourseCreate,
    CourseStatusTransition,
    CourseUpdate,
)
from app.modules.courses.service import (
    archive_user_course,
    complete_user_course,
    create_user_course,
    get_user_course,
    get_user_current_course,
    list_user_courses,
    select_user_course,
    transition_user_course,
    update_user_course,
)

router = V1APIRouter(prefix="/courses", tags=["courses"])


@router.get("")
def list_courses(
    include_archived: bool = Query(default=False),
    user=Depends(get_current_user),
):
    items = list_user_courses(user["id"], include_archived)
    return success(data={"items": items, "total": len(items)})


@router.get("/current")
def current_course(user=Depends(get_current_user)):
    return success(data=get_user_current_course(user["id"]))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_course(request: CourseCreate, user=Depends(get_current_user)):
    return success(data=create_user_course(user["id"], request), message="课程创建成功", code=201)


@router.get("/{course_id}")
def course_detail(course_id: int, user=Depends(get_current_user)):
    return success(data=get_user_course(user["id"], course_id))


@router.patch("/{course_id}")
def update_course(course_id: int, request: CourseUpdate, user=Depends(get_current_user)):
    return success(
        data=update_user_course(user["id"], course_id, request),
        message="课程更新成功",
    )


@router.post("/{course_id}/select")
def select_course(course_id: int, user=Depends(get_current_user)):
    return success(
        data=select_user_course(user["id"], course_id),
        message="当前课程已切换",
    )


@router.post("/{course_id}/status")
def transition_course(
    course_id: int,
    request: CourseStatusTransition,
    user=Depends(get_current_user),
):
    return success(
        data=transition_user_course(user["id"], course_id, request.status),
        message="课程状态已更新",
    )


@router.post("/{course_id}/complete")
def complete_course(course_id: int, user=Depends(get_current_user)):
    return success(
        data=complete_user_course(user["id"], course_id),
        message="课程已完成",
    )


@router.post("/{course_id}/archive")
def archive_course_command(
    course_id: int,
    request: CourseArchiveCommand,
    user=Depends(get_current_user),
):
    if not request.confirmed:
        raise AppError("归档课程需要二次确认", 409, "COURSE_CONFIRMATION_REQUIRED")
    return success(
        data=archive_user_course(user["id"], course_id),
        message="课程已归档",
    )


@router.delete("/{course_id}")
def archive_course(
    course_id: int,
    confirmed: bool = False,
    user=Depends(get_current_user),
):
    if not confirmed:
        raise AppError("归档课程需要二次确认", 409, "COURSE_CONFIRMATION_REQUIRED")
    archive_user_course(user["id"], course_id)
    return success(message="课程已归档")
