from fastapi import APIRouter, Depends
from pyexpat.errors import messages

from agents.profile_agent import generate_student_profile
from models import StudentProfileGenerateRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/profiles", tags=["profiles"])

@router.post("/generate")
def generate_profile_api(request: StudentProfileGenerateRequest, user=Depends(get_current_user)):
    "根据用户自然语言生成学生画像"
    try:
        profile = generate_student_profile(request.text)
        return success(
            data=profile,
            message="生成学生画像成功"
        )
    except Exception as e:
        return error(
            message="学生画像生成失败",
            code = 500
        )
    except ValueError as e:
        return error(
            message=str(e),
            code=400
        )