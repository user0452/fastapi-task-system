from fastapi import APIRouter, Depends
import json

from pyexpat.errors import messages

from models import AICommandRequest,ExamScheduleParseRequest,ReviewPlanPreviewRequest
from db import get_conn
from utils import success, error, get_current_user, parse_command
from llm_client import parse_exam_shedule,preview_review_plan
from models import ConfirmReviewPlanRequest
router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/command")
def ai_command(command: AICommandRequest, user=Depends(get_current_user)):

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

@router.post("/confirm-review-plan")
def confirm_review_plan_api(
        request: ConfirmReviewPlanRequest,
        user=Depends(get_current_user)
):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        created_tasks = []

        for task in request.tasks_preview:
            cursor.execute(
                """insert into tasks (user_id,title,description,status,priority)
                values (%s,%s,%s,%s,%s)""",
                (user["id"],task.title,task.description,task.status,task.priority)
            )
            task_id = cursor.lastrowid
            cursor.execute(
                """
                select id, title, description, status, priority, created_at, updated_at
                from tasks
                where id = %s
                """,
                (task_id,),
            )
            created_tasks.append(cursor.fetchone())

        log_detail = {
            "source":"ai_review_plan",
            "created_count":len(created_tasks),
            "task_ids":[task["id"] for task in created_tasks],
        }
        cursor.execute(
            """
            insert into operation_logs (user_id, action, target_type, target_id, detail)
                values (%s,%s,%s,%s,%s)
            """,
            (
                user["id"],
                "AI_CONFIRM_REVIEW_PLAN",
                "task",
                None,
                json.dumps(log_detail, ensure_ascii=False),
            )
        )


        conn.commit()
        return success(
            data={
                "created_count": len(created_tasks),
                "items": created_tasks,
            },
            message="复习任务创建成功",
        )

    except Exception as e:
        conn.rollback()
        return error(message=f"创建复习任务失败：{str(e)}",code= 500)
    finally:
        cursor.close()
        conn.close()

@router.get("/operation_logs")
def ger_operation_logs(
        page: int = 1,
        size: int = 10,
        user=Depends(get_current_user)
):
    if page <= 0 or size <= 0:
        return error(message="page或size参数不合法",code = 400)
    if size > 100:
        return error(message="page_size参数不能大于100",code = 400)
    conn = get_conn()
    cursor = conn.cursor()
    try:
        offset = (page - 1) * size
        cursor.execute(
            """
            select count(*) as total from operation_logs where user_id = %s
            """
            , (user["id"],)
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            """
            select id, action, target_type, target_id, detail, created_at
            from operation_logs
            where user_id = %s
            order by id desc
            limit %s offset %s
            """,
            (user["id"],size,offset)
        )
        logs = cursor.fetchall()
        return success(
            data={
                "list": logs,
                "total": total,
                "page": page,
                "size": size,
            },
            message="获取操作日志成功"
        )
    finally:
        cursor.close()
        conn.close()