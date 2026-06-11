import json

from fastapi import APIRouter, Depends

from agents.planner_agent import generate_learning_plan
from db import get_conn
from models import PlanPreviewRequest, PlanConfirmRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/plans", tags=["plans"])

@router.post("/preview")
def preview_learning_plan(
        request: PlanPreviewRequest,
        user=Depends(get_current_user)
):
    """
    根据课程名、知识点、计划天数和当前用户画像生成学习计划预览。
    第一版只返回预览，不写入任务表。
    """
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            select profile_json
            from student_profiles
                where user_id = %s
            """,
            (user["id"],)
        )
        row = cursor.fetchone()
        if row is None:
            profile =  None
        else:
            profile = json.loads(row["profile_json"])
            if isinstance(profile,str):
                profile = json.loads(profile)
        plan = generate_learning_plan(
            course_name=request.course_name,
            topic=request.topic,
            days=request.days,
            profile=profile
        )
        return success(
            data=plan,
            message="生成学习计划预览成功"
        )
    except ValueError as e:
        return error(
            code = 400,
            message=str(e)
        )
    except Exception as e:
        return error(
            code = 500,
            message=f"生成学习计划预览失败:{str(e)}"
        )
    finally:
        cursor.close()
        conn.close()

@router.post("/confirm")
def confirm_learning_plan(
        request: PlanConfirmRequest,
        user=Depends(get_current_user)
):
    """
    将学习计划预览导入tasks表
    """
    if not request.tasks_preview:
        return error(message="任务预览不能为空", code=400)
    conn = get_conn()
    cursor = conn.cursor()
    try:
        created_count = 0
        task_ids = []
        for task in request.tasks_preview:
            cursor.execute(
                """
                insert into tasks(
                user_id,title,description,status,priority
                )values
                    (%s,%s,%s,%s,%s)

                """,
                (
                    user["id"],
                    task.title,
                    task.description,
                    task.status,
                    task.priority
                )
            )
            created_count+=1
            task_ids.append(cursor.lastrowid)
        cursor.execute(
            """
            insert into operation_logs
             (user_id,action,target_type,target_id,detail)
             values(%s,%s,%s,%s,%s)

             """,
             (
                 user["id"],
                 "A3_CONFIRM_LEARNING_PLAN",
                 "task",
                  None,
                 json.dumps(
                     {
                         "source":"a3_learning_plan",
                         "created_count":created_count,
                         "task_ids":task_ids,
                         "task_titles":[task.title for task in request.tasks_preview]
                     },ensure_ascii= False
                 )

             )
         )

        conn.commit()
        return success(
            message=f"成功创建{created_count}个任务",
            data={
                "created_count": created_count,
                "task_ids": task_ids
            }
        )
    except Exception as e:
        conn.rollback()
        return error(
            message=f"创建任务失败：{str(e)}",
            code=500
        )
    finally:
        cursor.close()
        conn.close()
