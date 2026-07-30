from fastapi import Depends, Query, status

from app.core.responses import V1APIRouter, success
from app.modules.auth.dependencies import get_current_user
from app.modules.learning.schemas import (
    DiagnosticGenerateRequest,
    DiagnosticSubmitRequest,
    PracticeGenerateRequest,
    PracticeSubmitRequest,
    SessionRescheduleRequest,
    SessionSubmitRequest,
)
from app.modules.learning.service import (
    generate_diagnostic,
    generate_practice,
    get_course_progress,
    get_course_workspace_overview,
    get_diagnostic,
    get_latest_course_diagnostic,
    get_practice,
    get_practice_statistics,
    get_study_plan,
    get_today_learning,
    get_today_overview,
    get_wrong_answers,
    reschedule_learning_session,
    start_learning_session,
    submit_diagnostic,
    submit_learning_session,
    submit_practice,
)

router = V1APIRouter(tags=["adaptive-learning"])


@router.post("/courses/{course_id}/diagnostic", status_code=status.HTTP_201_CREATED)
def create_diagnostic(
    course_id: int,
    request: DiagnosticGenerateRequest,
    user=Depends(get_current_user),
):
    return success(
        data=generate_diagnostic(user["id"], course_id, request.question_count),
        message="诊断题已生成",
        code=201,
    )


@router.get("/courses/{course_id}/diagnostic")
def latest_diagnostic(course_id: int, user=Depends(get_current_user)):
    return success(data=get_latest_course_diagnostic(user["id"], course_id))


@router.get("/diagnostics/{quiz_set_id}")
def diagnostic_detail(quiz_set_id: int, user=Depends(get_current_user)):
    return success(data=get_diagnostic(user["id"], quiz_set_id))


@router.post("/diagnostics/{quiz_set_id}/submit")
def evaluate_diagnostic(
    quiz_set_id: int,
    request: DiagnosticSubmitRequest,
    user=Depends(get_current_user),
):
    return success(
        data=submit_diagnostic(
            user["id"],
            quiz_set_id,
            [item.model_dump() for item in request.answers],
        ),
        message="诊断完成，已生成学习计划",
    )


@router.get("/study/today")
def today_learning(course_id: int, user=Depends(get_current_user)):
    return success(data=get_today_learning(user["id"], course_id))


@router.get("/study/today-overview")
def today_overview(
    available_minutes: int = Query(default=90, ge=10, le=480),
    user=Depends(get_current_user),
):
    return success(data=get_today_overview(user["id"], available_minutes))


@router.post("/study/sessions/{session_id}/start")
def start_session(session_id: int, user=Depends(get_current_user)):
    return success(data=start_learning_session(user["id"], session_id))


@router.post("/study/sessions/{session_id}/submit")
def submit_session(
    session_id: int,
    request: SessionSubmitRequest,
    user=Depends(get_current_user),
):
    return success(
        data=submit_learning_session(
            user["id"],
            session_id,
            [item.model_dump() for item in request.answers],
            request.actual_minutes,
        ),
        message="今日学习已完成，后续计划已调整",
    )


@router.get("/courses/{course_id}/progress")
def course_progress(course_id: int, user=Depends(get_current_user)):
    return success(data=get_course_progress(user["id"], course_id))


@router.get("/courses/{course_id}/workspace-overview")
def course_workspace_overview(course_id: int, user=Depends(get_current_user)):
    return success(data=get_course_workspace_overview(user["id"], course_id))


@router.post("/courses/{course_id}/practice", status_code=status.HTTP_201_CREATED)
def create_practice(
    course_id: int,
    request: PracticeGenerateRequest,
    user=Depends(get_current_user),
):
    return success(
        data=generate_practice(
            user["id"],
            course_id,
            request.question_count,
            request.knowledge_point_id,
            request.difficulty,
        ),
        message="针对性练习已生成",
        code=201,
    )


@router.get("/practices/{quiz_set_id}")
def practice_detail(quiz_set_id: int, user=Depends(get_current_user)):
    return success(data=get_practice(user["id"], quiz_set_id))


@router.post("/practices/{quiz_set_id}/submit")
def evaluate_practice(
    quiz_set_id: int,
    request: PracticeSubmitRequest,
    user=Depends(get_current_user),
):
    return success(
        data=submit_practice(
            user["id"],
            quiz_set_id,
            [item.model_dump() for item in request.answers],
        ),
        message="练习已批改，掌握度与后续计划已更新",
    )


@router.get("/courses/{course_id}/practice-stats")
def practice_stats(course_id: int, user=Depends(get_current_user)):
    return success(data=get_practice_statistics(user["id"], course_id))


@router.get("/courses/{course_id}/wrong-answers")
def wrong_answers(course_id: int, user=Depends(get_current_user)):
    return success(data=get_wrong_answers(user["id"], course_id))


@router.get("/courses/{course_id}/study-plan")
def study_plan(course_id: int, user=Depends(get_current_user)):
    return success(data=get_study_plan(user["id"], course_id))


@router.patch("/study/sessions/{session_id}/schedule")
def reschedule_session(
    session_id: int,
    request: SessionRescheduleRequest,
    user=Depends(get_current_user),
):
    return success(
        data=reschedule_learning_session(
            user["id"],
            session_id,
            request.scheduled_date,
            request.estimated_minutes,
        ),
        message="学习单元时间已调整",
    )
