from fastapi import BackgroundTasks, Depends, File, Form, UploadFile, status

from app.core.errors import AppError
from app.core.responses import V1APIRouter, success
from app.integrations.file_storage import save_upload
from app.jobs.material_index_job import enqueue_material_processing_job, run_material_processing_job
from app.modules.auth.dependencies import get_current_user
from app.modules.courses.service import get_material_writable_course
from app.modules.materials.schemas import MaterialSearchRequest, TextMaterialCreate
from app.modules.materials.service import (
    create_text_material,
    create_uploaded_material,
    delete_user_material,
    get_course_knowledge_graph,
    get_course_material_chunk,
    get_user_material,
    list_course_knowledge_points,
    list_user_course_materials,
    material_public_view,
    request_material_retry,
    search_course_materials,
)

router = V1APIRouter(tags=["course-materials"])


@router.get("/courses/{course_id}/materials")
def list_materials(course_id: int, user=Depends(get_current_user)):
    items = list_user_course_materials(user["id"], course_id)
    return success(data={"items": items, "total": len(items)})


@router.post(
    "/courses/{course_id}/materials/text",
    status_code=status.HTTP_202_ACCEPTED,
)
def add_text_material(
    course_id: int,
    request: TextMaterialCreate,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    material = create_text_material(user["id"], course_id, request)
    enqueue_material_processing_job(user["id"], course_id, material["id"])
    background_tasks.add_task(run_material_processing_job, user["id"], material["id"])
    return success(data=material_public_view(material), message="资料已保存，正在自动构建索引", code=202)


@router.post(
    "/courses/{course_id}/materials/upload",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_material(
    course_id: int,
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    get_material_writable_course(user["id"], course_id)
    try:
        upload = await save_upload(file, user["id"])
    except ValueError as exc:
        # File validation errors are expected user input errors (unsupported
        # suffix, empty file, or size limit), not an internal server failure.
        raise AppError(str(exc), 400, "INVALID_UPLOAD") from exc
    material = create_uploaded_material(user["id"], course_id, title, upload)
    enqueue_material_processing_job(user["id"], course_id, material["id"])
    background_tasks.add_task(run_material_processing_job, user["id"], material["id"])
    return success(data=material_public_view(material), message="文件已上传，正在自动解析和构建索引", code=202)


@router.get("/materials/{material_id}")
def material_status(material_id: int, user=Depends(get_current_user)):
    return success(data=material_public_view(get_user_material(user["id"], material_id)))


@router.delete("/materials/{material_id}")
def delete_material(material_id: int, user=Depends(get_current_user)):
    return success(data=delete_user_material(user["id"], material_id), message="资料已删除")


@router.post("/materials/{material_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_material(
    material_id: int,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    material = request_material_retry(user["id"], material_id)
    enqueue_material_processing_job(user["id"], material["course_id"], material_id)
    background_tasks.add_task(run_material_processing_job, user["id"], material_id)
    return success(data=material_public_view(material), message="已重新提交资料处理", code=202)


@router.get("/courses/{course_id}/knowledge-points")
def knowledge_points(course_id: int, user=Depends(get_current_user)):
    items = list_course_knowledge_points(user["id"], course_id)
    return success(data={"items": items, "total": len(items)})


@router.get("/courses/{course_id}/materials/chunks/{chunk_id}")
def material_chunk(course_id: int, chunk_id: int, user=Depends(get_current_user)):
    return success(data=get_course_material_chunk(user["id"], course_id, chunk_id))


@router.get("/courses/{course_id}/knowledge-graph")
def knowledge_graph(course_id: int, user=Depends(get_current_user)):
    return success(data=get_course_knowledge_graph(user["id"], course_id))


@router.post("/courses/{course_id}/materials/search")
def search_materials(
    course_id: int,
    request: MaterialSearchRequest,
    user=Depends(get_current_user),
):
    return success(
        data=search_course_materials(
            user["id"],
            course_id,
            request.query,
            request.top_k,
        )
    )
