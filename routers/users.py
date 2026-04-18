from fastapi import APIRouter

from models import UserRegister, UserLogin
from db import get_conn
from utils import success, error, hash_password, verify_password, create_token

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register")
def register(user: UserRegister):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        sql = "select * from users where username = %s"
        cursor.execute(sql, (user.username,))
        result = cursor.fetchone()

        if result is not None:
            return error(message="用户名已存在", code=400)

        cursor.execute(
            "insert into users (username, password) values (%s, %s)",
            (user.username, hash_password(user.password))
        )
        conn.commit()
        new_id = cursor.lastrowid

        return success(
            message="注册成功",
            data={
                "id": new_id,
                "username": user.username
            }
        )
    finally:
        cursor.close()
        conn.close()


@router.post("/login")
def login(user: UserLogin):
    conn = get_conn()
    cursor = conn.cursor()
    try:
        sql = "select * from users where username = %s"
        cursor.execute(sql, (user.username,))
        result = cursor.fetchone()

        if result is None:
            return error(code=404, message="用户不存在")

        if not verify_password(user.password, result["password"]):
            return error(message="密码错误")

        token = create_token({
            "id": result["id"],
            "username": result["username"]
        })

        return success(
            data={"token": token},
            message="登录成功"
        )
    finally:
        cursor.close()
        conn.close()