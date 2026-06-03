import json
from fastapi import APIRouter, Depends
from db import get_conn
from agents.profile_agent import generate_student_profile
from models import StudentProfileGenerateRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/profiles", tags=["profiles"])

@router.post("/generate")
def generate_profile_api(request: StudentProfileGenerateRequest, user=Depends(get_current_user)):
    "根据用户自然语言生成学生画像"
    try:
        profile = generate_student_profile(request.text)
        conn = get_conn()
        cursor = conn.cursor()
        try:
            profile_json = json.dumps(profile,ensure_ascii= False)
            cursor.execute(
                """
                insert into student_profiles (user_id,profile_json)
                values(%s,%s)
                on duplicate key update
                    profile_json = values(profile_json),
                    updated_at = current_timestamp
                """,
                (user["id"],profile_json)
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        return success(
            data=profile,
            message="生成学生画像成功"
        )

    except ValueError as e:
        return error(
            message=str(e),
            code=400
        )

    except Exception as e:
        return error(
            message=f"学生画像生成失败:{str(e)}",
            code = 500
        )

@router.get("/me")
def get_my_profile(user=Depends(get_current_user)):
    "获取当前用户的学生画像"
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            select id,user_id,profile_json,created_at,updated_at
            from student_profiles
            where user_id = %s
            """,
            (user["id"],)
        )
        row = cursor.fetchone()
        if row is None:
            return success(
                data=None,
                message="当前用户没有学生画像"
            )
        profile = json.loads(row["profile_json"])
        if isinstance(profile,str):
            profile = json.loads(profile)
        return success(
            data={
                "id":row["id"],
                "user_id":row["user_id"],
                "profile":profile,
                "created_at":row["created_at"],
                "updated_at":row["updated_at"]
            },
            message="获取学生画像成功"
        )
    except Exception as e:
        return error(
            message=f"获取学生画像失败:{str(e)}",
            code = 500
        )
    finally:
        cursor.close()
        conn.close()
