from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.errors import ApiJSONResponse, error_payload

_settings = get_settings()
SECRET_KEY = _settings.secret_key
ALGORITHM = _settings.algorithm
ACCESS_TOKEN_EXPIRE_HOURS = _settings.access_token_expire_hours
security = HTTPBearer()


def is_valid_status(status: str) -> bool:
    return status in ["todo", "doing", "done"]


def is_valid_priority(priority: str) -> bool:
    return priority in ["low", "medium", "high"]


def success(data=None, message="success"):
    return {
        "code": 200,
        "message": message,
        "data": data
    }


def error(message="error", code: int = 400):
    return ApiJSONResponse(error_payload(message, code), status_code=code)


def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def get_current_user(credentials:HTTPAuthorizationCredentials = Depends( security)):
    token = credentials.credentials

    payload = verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="未登录或token无效")
    return payload


def require_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    payload = get_current_user(credentials=credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="未登录或token无效")
    return payload


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_owned_task(cursor, task_id: int, user_id: int):
    cursor.execute("select * from tasks where id = %s", (task_id,))
    task = cursor.fetchone()

    if task is None:
        return None, error(code=404, message="任务不存在")
    if user_id != task["user_id"]:
        return None, error(code=403, message="无访问权限")
    return task, None

def parse_command(text: str):
    text = text.strip()

    if "把所有todo改成doing" in text:
        return {
            "action": "bulk_update_status",
            "from_status": "todo",
            "to_status": "doing"
        }

    if "删除所有done任务" in text:
        return {
            "action": "bulk_delete_status",
            "status": "done"
        }

    if text.startswith("创建任务："):
        content = text.replace("创建任务：", "", 1).strip()

        priority = "medium"
        if "优先级高" in content:
            priority = "high"
            content = content.replace("，优先级高", "").replace(",优先级高", "")
        elif "优先级低" in content:
            priority = "low"
            content = content.replace("，优先级低", "").replace(",优先级低", "")

        return {
            "action": "create_task",
            "title": content,
            "description": "",
            "status": "todo",
            "priority": priority
        }

    return None


# Keep old imports pointing at the single v1 authentication dependency.
from app.modules.auth.dependencies import get_current_user as get_current_user  # noqa: E402,F811
