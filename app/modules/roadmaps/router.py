from fastapi import Depends

from app.core.responses import V1APIRouter, success
from app.modules.auth.dependencies import get_current_user
from app.modules.roadmaps.schemas import RoadmapRetryRequest
from app.modules.roadmaps.service import get_learning_roadmap, retry_learning_roadmap

router = V1APIRouter(tags=["learning-roadmaps"])


@router.get("/courses/{course_id}/roadmap")
def course_roadmap(course_id: int, user=Depends(get_current_user)):
    return success(data=get_learning_roadmap(user["id"], course_id))


@router.post("/courses/{course_id}/roadmap/retry")
def retry_course_roadmap(
    course_id: int,
    request: RoadmapRetryRequest,
    user=Depends(get_current_user),
):
    return success(
        data=retry_learning_roadmap(user["id"], course_id, request.reason),
        message="路线图生成任务已重试",
    )
