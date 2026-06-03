import json

from fastapi import APIRouter, Depends

from agents.resource_agent import generate_learning_resource
from db import get_conn
from models import LearningResourceGenerateRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/resources", tags=["resources"])
@router.post("/generate")
def generate_resource_api(request: LearningResourceGenerateRequest, user=Depends(get_current_user)):
    "根据用户输入的课程名和知识点，生成学习资源"
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            select profile_json from student_profiles where user_id = %s
            """,
            (user["id"],)
        )
        row = cursor.fetchone()
        print( row)
        if row is None:
            return error(
                message="当前用户没有学生画像",
                code=400
            )
        else:
            profile = json.loads(row["profile_json"])
            if isinstance(profile,str):
                profile = json.loads(profile)
            resource = generate_learning_resource(
                course_name=request.course_name,
                topic=request.topic,
                profile=profile
            )
            return success(
                data=resource,
                message="生成学习资源成功"
            )
    except ValueError as e:
        return error(
            message=str(e),
            code = 400
        )
    except Exception as e:
        return error(
            message=f"生成学习资源失败:{str(e)}",
            code = 500
        )
    finally:
        cursor.close()
        conn.close()
