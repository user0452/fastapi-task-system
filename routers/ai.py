from fastapi import APIRouter, Header

from models import AICommandRequest
from db import get_conn
from utils import success, error, get_current_user, parse_command

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/command")
def ai_command(command: AICommandRequest, authorization: str = Header(None)):
    user = get_current_user(authorization)
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