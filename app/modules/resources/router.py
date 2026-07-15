from fastapi import Depends

from app.core.responses import V1APIRouter, success
from app.modules.auth.dependencies import get_current_user
from app.modules.resources.schemas import ExternalResourceSearchRequest, ResourceInteractionRequest
from app.modules.resources.service import (
    check_resource_availability,
    list_external_resources,
    record_resource_interaction,
    search_external_resources,
)

router = V1APIRouter(tags=["course-external-resources"])


@router.post("/courses/{course_id}/external-resources/search")
def search_resources(
    course_id: int,
    request: ExternalResourceSearchRequest,
    user=Depends(get_current_user),
):
    return success(data=search_external_resources(user["id"], course_id, request))


@router.get("/courses/{course_id}/external-resources")
def course_resources(course_id: int, user=Depends(get_current_user)):
    return success(data=list_external_resources(user["id"], course_id))


@router.post("/courses/{course_id}/external-resources/{resource_id}/interactions")
def interact_with_resource(
    course_id: int,
    resource_id: int,
    request: ResourceInteractionRequest,
    user=Depends(get_current_user),
):
    return success(
        data=record_resource_interaction(user["id"], course_id, resource_id, request),
        message="资源学习状态已更新",
    )


@router.post("/courses/{course_id}/external-resources/{resource_id}/check")
def check_resource(course_id: int, resource_id: int, user=Depends(get_current_user)):
    return success(data=check_resource_availability(user["id"], course_id, resource_id))
