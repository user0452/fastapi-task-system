"""
公共数据库操作函数
从 agent.py 和其他路由中提取的重复逻辑
"""

import json
from typing import Any


def json_dumps(data: Any) -> str:
    """JSON 序列化"""
    return json.dumps(data, ensure_ascii=False, default=str)


def json_loads(value: Any, default: Any = None) -> Any:
    """JSON 反序列化，兼容多种输入类型"""
    if value is None:
        return default

    if isinstance(value, (dict, list)):
        return value

    if not isinstance(value, str) or not value.strip():
        return default

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def load_json_list(value) -> list:
    """解析 JSON 列表字段"""
    data = json_loads(value, [])
    return data if isinstance(data, list) else []


def load_profile(cursor, user_id: int) -> dict | None:
    """加载学生画像"""
    cursor.execute(
        """
        SELECT profile_json
        FROM student_profiles
        WHERE user_id = %s
        """,
        (user_id,)
    )
    row = cursor.fetchone()

    if row is None:
        return None

    profile = json_loads(row["profile_json"], None)
    if isinstance(profile, str):
        profile = json_loads(profile, None)

    return profile if isinstance(profile, dict) else None


def load_profile_detail(cursor, user_id: int) -> dict | None:
    """加载学生画像详情"""
    cursor.execute(
        """
        SELECT id, user_id, profile_json, created_at, updated_at
        FROM student_profiles
        WHERE user_id = %s
        """,
        (user_id,)
    )
    row = cursor.fetchone()

    if row is None:
        return None

    profile = json_loads(row["profile_json"], None)
    if isinstance(profile, str):
        profile = json_loads(profile, None)

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "profile": profile,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }


def insert_log(cursor, user_id: int, action: str, target_type: str | None, target_id: int | None, detail: dict):
    """插入操作日志"""
    cursor.execute(
        """
        INSERT INTO operation_logs
            (user_id, action, target_type, target_id, detail)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            user_id,
            action,
            target_type,
            target_id,
            json_dumps(detail)
        )
    )


def insert_chat_message(cursor, user_id: int, role: str, content: str, tool_calls: dict | None = None) -> int:
    """插入聊天消息"""
    cursor.execute(
        """
        INSERT INTO agent_chat_messages
            (user_id, role, content, tool_calls)
        VALUES (%s, %s, %s, %s)
        """,
        (
            user_id,
            role,
            content,
            json_dumps(tool_calls) if tool_calls is not None else None
        )
    )
    return cursor.lastrowid


def get_course_chunks(cursor, user_id: int, course_name: str) -> list[dict]:
    """获取课程资料分块"""
    cursor.execute(
        """
        SELECT id, user_id, material_id, course_name, chunk_index, chunk_text, created_at
        FROM course_material_chunks
        WHERE user_id = %s AND course_name = %s
        ORDER BY id ASC
        """,
        (user_id, course_name)
    )
    return cursor.fetchall()


def require_text(value: Any, message: str) -> str:
    """要求非空文本"""
    if value is None:
        raise ValueError(message)

    text = str(value).strip()
    if not text:
        raise ValueError(message)

    return text


def optional_text(value: Any) -> str | None:
    """可选文本"""
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def to_int(value: Any, default: int | None = None) -> int | None:
    """转换为整数"""
    if value is None or value == "":
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def page_size(args: dict, default_size: int = 10) -> tuple[int, int]:
    """解析分页参数"""
    page = to_int(args.get("page"), 1) or 1
    size = to_int(args.get("size"), default_size) or default_size

    if page < 1:
        page = 1

    if size < 1:
        size = default_size

    if size > 100:
        size = 100

    return page, size


def is_valid_status(status: str) -> bool:
    """验证任务状态"""
    return status in ["todo", "doing", "done"]


def is_valid_priority(priority: str) -> bool:
    """验证任务优先级"""
    return priority in ["low", "medium", "high"]
