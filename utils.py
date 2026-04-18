from datetime import datetime, timedelta
from fastapi import Header
from jose import jwt, JWTError
from passlib.context import CryptContext

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    return {
        "code": code,
        "message": message,
        "data": None
    }


def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=2)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def get_current_user(authorization: str = Header(None)):
    print("authorization =", authorization)

    if authorization is None:
        return None

    token = authorization.replace("Bearer ", "")
    print("token =", token)

    payload = verify_token(token)
    print("payload =", payload)

    return payload


def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


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