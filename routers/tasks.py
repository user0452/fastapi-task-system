from fastapi import APIRouter, Depends
from typing import Optional

from models import TaskCreate, TaskUpdate
from db import get_cursor
from utils import (
    is_valid_status,
    is_valid_priority,
    success,
    error,
    get_current_user,
    get_owned_task,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}")
def get_task(task_id: int, user=Depends(get_current_user)):
    with get_cursor() as cursor:
        task, err = get_owned_task(cursor, task_id, user["id"])
        if err is not None:
            return err
        task.pop("user_id", None)
        return success(data=task)


@router.get("")
def get_tasks(
    page: int = 1,
    size: int = 10,
    status: Optional[str] = None,
    user=Depends(get_current_user),
):
    if page <= 0 or size <= 0:
        return error(message="page或size参数不合法")
    if size > 100:
        return error(message="size不能大于100", code=400)

    if status is not None and not is_valid_status(status):
        return error(message="status参数不合法")

    with get_cursor() as cursor:
        start = (page - 1) * size

        if status is None:
            cursor.execute(
                "select count(*) from tasks where user_id = %s",
                (user["id"],),
            )
            total = cursor.fetchone().get("count(*)")

            cursor.execute(
                "select id, title, description, status, priority, created_at, updated_at from tasks where user_id = %s limit %s offset %s",
                (user["id"], size, start),
            )
            result = cursor.fetchall()
        else:
            cursor.execute(
                "select count(*) from tasks where status = %s and user_id = %s",
                (status, user["id"]),
            )
            total = cursor.fetchone().get("count(*)")

            cursor.execute(
                "select id, title, description, status, priority, created_at, updated_at from tasks where status = %s and user_id = %s limit %s offset %s",
                (status, user["id"], size, start),
            )
            result = cursor.fetchall()

        return success(
            data={
                "list": result,
                "total": total,
                "page": page,
                "size": size,
            }
        )


@router.post("")
def create_task(task: TaskCreate, user=Depends(get_current_user)):

    if not is_valid_status(task.status):
        return error(message="status参数不合法")

    if not is_valid_priority(task.priority):
        return error(message="priority参数不合法")

    with get_cursor() as cursor:
        sql = "insert into tasks (user_id,title,description,status,priority) values (%s,%s,%s,%s,%s)"
        cursor.execute(
            sql,
            (user["id"], task.title, task.description, task.status, task.priority),
        )
        new_id = cursor.lastrowid
        cursor.execute("select id, title, description, status, priority,created_at,updated_at from tasks where id = %s", (new_id,))
        result = cursor.fetchone()
        return success(
            data=result,
            message="创建成功",
        )


@router.put("/{task_id}")
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    user=Depends(get_current_user),
):
    with get_cursor() as cursor:
        task, err = get_owned_task(cursor, task_id, user["id"])
        if err is not None:
            return err

        if all(
            [
                task_data.title is None,
                task_data.description is None,
                task_data.status is None,
                task_data.priority is None,
            ]
        ):
            return error(message="参数不能全为空")

        if task_data.status is not None and not is_valid_status(task_data.status):
            return error(message="status参数不合法")

        if task_data.priority is not None and not is_valid_priority(task_data.priority):
            return error(message="priority参数不合法")

        # 合并为单条 UPDATE 语句
        update_fields = []
        update_values = []

        if task_data.title is not None:
            update_fields.append("title = %s")
            update_values.append(task_data.title)

        if task_data.description is not None:
            update_fields.append("description = %s")
            update_values.append(task_data.description)

        if task_data.status is not None:
            update_fields.append("status = %s")
            update_values.append(task_data.status)

        if task_data.priority is not None:
            update_fields.append("priority = %s")
            update_values.append(task_data.priority)

        update_values.append(task_id)
        sql = f"update tasks set {', '.join(update_fields)} where id = %s"
        cursor.execute(sql, update_values)

        cursor.execute("select id, title, description, status, priority,created_at,updated_at from tasks where id = %s", (task_id,))
        result = cursor.fetchone()

        return success(data=result, message="更新成功")


@router.delete("/{task_id}")
def delete_task(task_id: int, confirmed: bool = False, user=Depends(get_current_user)):
    if not confirmed:
        return error(message="删除任务需要二次确认", code=409)
    with get_cursor() as cursor:
        task, err = get_owned_task(cursor, task_id, user["id"])
        if err is not None:
            return err

        cursor.execute("delete from tasks where id = %s", (task_id,))

        return success(message="删除成功")
