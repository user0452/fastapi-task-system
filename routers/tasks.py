from fastapi import APIRouter, Header
from typing import Annotated
from typing import Optional

from models import TaskCreate, TaskUpdate
from db import get_conn
from utils import (
    is_valid_status,
    is_valid_priority,
    success,
    error,
    get_current_user,
    get_owned_task,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/tasks/{task_id}")
def get_task(task_id: int, authorization: str = Header(None, alias="Authorization")):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        user = get_current_user(authorization)
        if user is None:
            return error(message="未登录", code=401)

        task, err = get_owned_task(cursor, task_id, user["id"])
        if err is not None:
            return err

        return success(data=task)
    finally:
        cursor.close()
        conn.close()


@router.get("/tasks")
def get_tasks(
    page: int = 1,
    size: int = 10,
    status: Optional[str] = None,
    authorization: str = Header(None, alias="Authorization"),
):
    user = get_current_user(authorization)
    if user is None:
        return error(message="未登录", code=401)

    if page <= 0 or size <= 0:
        return error(message="page或size参数不合法")

    if status is not None and not is_valid_status(status):
        return error(message="status参数不合法")

    conn = get_conn()
    cursor = conn.cursor()
    start = (page - 1) * size

    try:
        if status is None:
            cursor.execute(
                "select count(*) from tasks where user_id = %s",
                (user["id"],),
            )
            total = cursor.fetchone().get("count(*)")

            cursor.execute(
                "select * from tasks where user_id = %s limit %s offset %s",
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
                "select * from tasks where status = %s and user_id = %s limit %s offset %s",
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
    finally:
        cursor.close()
        conn.close()


@router.post("/tasks")
def create_task(task: TaskCreate, authorization: str = Header(None, alias="Authorization")):
    user = get_current_user(authorization)
    if user is None:
        return error(message="未登录", code=401)

    if not is_valid_status(task.status):
        return error(message="status参数不合法")

    if not is_valid_priority(task.priority):
        return error(message="priority参数不合法")

    conn = get_conn()
    cursor = conn.cursor()
    try:
        sql = "insert into tasks (user_id,title,description,status,priority) values (%s,%s,%s,%s,%s)"
        cursor.execute(
            sql,
            (user["id"], task.title, task.description, task.status, task.priority),
        )
        conn.commit()
        new_id = cursor.lastrowid

        return success(
            data={
                "id": new_id,
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
            },
            message="创建成功",
        )
    finally:
        cursor.close()
        conn.close()


@router.put("/tasks/{task_id}")
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    authorization: str = Header(None, alias="Authorization"),
):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        user = get_current_user(authorization)
        if user is None:
            return error(message="未登录", code=401)

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

        if task_data.title is not None:
            cursor.execute(
                "update tasks set title = %s where id = %s",
                (task_data.title, task_id),
            )

        if task_data.description is not None:
            cursor.execute(
                "update tasks set description = %s where id = %s",
                (task_data.description, task_id),
            )

        if task_data.status is not None:
            cursor.execute(
                "update tasks set status = %s where id = %s",
                (task_data.status, task_id),
            )

        if task_data.priority is not None:
            cursor.execute(
                "update tasks set priority = %s where id = %s",
                (task_data.priority, task_id),
            )

        conn.commit()

        cursor.execute("select * from tasks where id = %s", (task_id,))
        result = cursor.fetchone()

        return success(data=result, message="更新成功")
    finally:
        cursor.close()
        conn.close()


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, authorization: str = Header(None, alias="Authorization")):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        user = get_current_user(authorization)
        if user is None:
            return error(message="未登录", code=401)

        task, err = get_owned_task(cursor, task_id, user["id"])
        if err is not None:
            return err

        cursor.execute("delete from tasks where id = %s", (task_id,))
        conn.commit()

        return success(message="删除成功")
    finally:
        cursor.close()
        conn.close()