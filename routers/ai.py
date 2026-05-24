from fastapi import APIRouter, Depends

from models import AICommandRequest,ExamScheduleParseRequest,ReviewPlanPreviewRequest
from db import get_conn
from utils import success, error, get_current_user, parse_command
from llm_client import parse_exam_shedule,preview_review_plan

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/command")
def ai_command(command: AICommandRequest, user=Depends(get_current_user)):
    if user is None:
        return error(message="未登录", code=401)

    parsed = parse_command(command.text)
    if parsed is None:
        return error(message="暂不支持这条指令", code=400)

    conn = get_conn()
    cursor = conn.cursor()

    try:
        if parsed["action"] == "bulk_update_status":
            cursor.execute(
                "update tasks set status = %s where user_id = %s and status = %s",
                (parsed["to_status"], user["id"], parsed["from_status"])
            )
            conn.commit()
            return success(
                message="批量更新成功",
                data={
                    "affected_rows": cursor.rowcount,
                    "parsed": parsed
                }
            )

        if parsed["action"] == "bulk_delete_status":
            cursor.execute(
                "delete from tasks where user_id = %s and status = %s",
                (user["id"], parsed["status"])
            )
            conn.commit()
            return success(
                message="批量删除成功",
                data={
                    "affected_rows": cursor.rowcount,
                    "parsed": parsed
                }
            )

        if parsed["action"] == "create_task":
            cursor.execute(
                "insert into tasks (user_id, title, description, status, priority) values (%s, %s, %s, %s, %s)",
                (
                    user["id"],
                    parsed["title"],
                    parsed["description"],
                    parsed["status"],
                    parsed["priority"]
                )
            )
            conn.commit()
            new_id = cursor.lastrowid

            return success(
                message="创建任务成功",
                data={
                    "id": new_id,
                    "title": parsed["title"],
                    "description": parsed["description"],
                    "status": parsed["status"],
                    "priority": parsed["priority"],
                    "parsed": parsed
                }
            )

        return error(message="未知操作类型", code=400)

    finally:
        cursor.close()
        conn.close()

@router.post("/parse-exam-shedule")
def parse_exam_shedule_api(
        request: ExamScheduleParseRequest,
        user=Depends(get_current_user)
):
    try:
        result = parse_exam_shedule(request.text)
        return success(data=result,message='解析成功')
    except ValueError as e:
        return error(message=str(e),code = 400)
    except Exception as e:
        return error(message = f"AI解析失败：{str(e)}",code= 500)

@router.post("/preview-review-plan")
def preview_review_plan_api(
        request: ReviewPlanPreviewRequest,
        user=Depends(get_current_user)
):
     try:
         exams = [exam.model_dump() for exam in request.exams]
         result = preview_review_plan(exams)
         return success(data=result,message='生成预览成功')
     except ValueError as e:
         return error(message=str(e),code = 400)
     except Exception as e:
         return error(message = f"AI生成预览失败：{str(e)}",code= 500)