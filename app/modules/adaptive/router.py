"""Public Adaptive Tutor API."""

from fastapi import Depends, File, Header, UploadFile, status

from app.core.responses import V1APIRouter, success
from app.integrations.file_storage import read_limited_upload
from app.modules.adaptive import service
from app.modules.adaptive.schemas import (
    AdaptiveAnswerRequest,
    CurriculumRebuildRequest,
    DiagnosticStartRequest,
    DiagnosticSubmitRequest,
    QuestionBankCreateRequest,
    QuestionImportCommitRequest,
    QuestionObjectiveTagRequest,
    TutorCheckSubmitRequest,
    TutorRequest,
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


@router.post("/courses/{course_id}/question-bank/import", status_code=status.HTTP_202_ACCEPTED)
async def preview_question_bank(
    course_id: int,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
):
    try:
        content = await read_limited_upload(file)
    except ValueError as exc:
        from app.core.errors import AppError

        raise AppError(str(exc), 400, "INVALID_UPLOAD") from exc
    return success(
        data=await service.preview_question_bank_upload(
            user["id"],
            course_id,
            file.filename or "question-bank.txt",
            content,
            idempotency_key,
        ),
        message="题库已解析，等待确认导入",
        code=202,
    )


@router.post("/courses/{course_id}/question-bank/import/commit")
def commit_question_bank(
    course_id: int,
    request: QuestionImportCommitRequest,
    user=Depends(get_current_user),
):
    return success(
        data=service.commit_question_import(user["id"], course_id, request.batch_id),
        message="题库导入完成",
    )


@router.patch("/courses/{course_id}/questions/{question_id}/objectives")
def tag_question(
    course_id: int,
    question_id: int,
    request: QuestionObjectiveTagRequest,
    user=Depends(get_current_user),
):
    return success(
        data=service.tag_question_objectives(
            user["id"], course_id, question_id, request.objective_ids
        ),
        message="题目 Objective 关联已更新",
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


@router.post("/courses/{course_id}/tutor")
def adaptive_tutor(
    course_id: int,
    request: TutorRequest,
    user=Depends(get_current_user),
):
    return success(
        data=service.tutor_chat(
            user["id"],
            course_id,
            message=request.message,
            intent=request.intent,
            action_id=request.action_id,
            objective_id=request.objective_id,
        )
    )


@router.post("/courses/{course_id}/tutor/checks/{check_id}/submit")
def submit_tutor_check(
    course_id: int,
    check_id: int,
    request: TutorCheckSubmitRequest,
    user=Depends(get_current_user),
):
    return success(
        data=service.submit_tutor_check(
            user["id"],
            course_id,
            check_id,
            request.response,
            request.idempotency_key,
        ),
        message="Tutor Check 已评分并写入 Evidence",
    )
