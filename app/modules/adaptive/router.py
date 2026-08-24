"""Public Adaptive Tutor API."""

from fastapi import Depends, status

from app.core.responses import V1APIRouter, success
from app.modules.adaptive import service
from app.modules.adaptive.schemas import (
    AdaptiveAnswerRequest,
    CurriculumRebuildRequest,
    DiagnosticStartRequest,
    DiagnosticSubmitRequest,
    QuestionBankCreateRequest,
)
from app.modules.auth.dependencies import get_current_user

router = V1APIRouter(prefix="/adaptive", tags=["adaptive-tutor"])


@router.get("/courses/{course_id}/overview")
def adaptive_overview(course_id: int, user=Depends(get_current_user)):
    return success(data=service.get_overview(user["id"], course_id))


@router.get("/courses/{course_id}/next-action")
def next_learning_action(course_id: int, user=Depends(get_current_user)):
    return success(data=service.get_next_action(user["id"], course_id))


@router.get("/courses/{course_id}/progress")
def adaptive_progress(course_id: int, user=Depends(get_current_user)):
    return success(data=service.get_progress(user["id"], course_id))


@router.get("/courses/{course_id}/sources")
def adaptive_sources(course_id: int, user=Depends(get_current_user)):
    return success(data=service.get_sources(user["id"], course_id))


@router.get("/courses/{course_id}/objectives/{objective_id}")
def objective_detail(course_id: int, objective_id: int, user=Depends(get_current_user)):
    return success(data=service.get_objective_detail(user["id"], course_id, objective_id))


@router.post("/courses/{course_id}/curriculum/rebuild", status_code=status.HTTP_202_ACCEPTED)
def rebuild_curriculum(
    course_id: int,
    request: CurriculumRebuildRequest,
    user=Depends(get_current_user),
):
    return success(
        data=service.rebuild_curriculum(user["id"], course_id, request.material_id),
        message="Curriculum 已重新构建",
        code=202,
    )


@router.post("/courses/{course_id}/questions", status_code=status.HTTP_201_CREATED)
def add_question_bank(
    course_id: int,
    request: QuestionBankCreateRequest,
    user=Depends(get_current_user),
):
    return success(
        data=service.add_question_bank(
            user["id"],
            course_id,
            [item.model_dump() for item in request.questions],
        ),
        message="题目已加入题库",
        code=201,
    )


@router.post("/courses/{course_id}/diagnostic")
def start_diagnostic(
    course_id: int,
    request: DiagnosticStartRequest,
    user=Depends(get_current_user),
):
    return success(data=service.start_diagnostic(user["id"], course_id, request.question_count))


@router.post("/courses/{course_id}/diagnostic/submit")
def submit_diagnostic(
    course_id: int,
    request: DiagnosticSubmitRequest,
    user=Depends(get_current_user),
):
    return success(
        data=service.submit_diagnostic(
            user["id"],
            course_id,
            [item.model_dump() for item in request.answers],
        ),
        message="诊断证据已写入 Student Model",
    )


@router.post("/actions/{action_id}/start")
def start_action(action_id: int, user=Depends(get_current_user)):
    return success(data=service.start_action(user["id"], action_id))


@router.post("/actions/{action_id}/submit")
def submit_action(
    action_id: int,
    request: AdaptiveAnswerRequest,
    user=Depends(get_current_user),
):
    return success(
        data=service.submit_action(user["id"], action_id, request.model_dump()),
        message="学习证据已记录，下一步动作已重新计算",
    )
