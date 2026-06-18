import json

from fastapi import APIRouter, Depends

from db import get_conn
from models import ExternalResourceSearchRequest
from services.external_resource_service import search_external_learning_resources
from utils import success, error, get_current_user

router = APIRouter(prefix="/external-resources", tags=["external_resources"])


@router.post("/search")
def search_external_resources(
        request: ExternalResourceSearchRequest,
        user=Depends(get_current_user)
):
    """
    联网检索外部学习资源。
    """
    try:
        result = search_external_learning_resources(
            course_name=request.course_name,
            topic=request.topic,
            learner_level=request.learner_level or "beginner",
            max_results=request.max_results
        )

    except ValueError as e:
        return error(message=str(e), code=400)

    except Exception as e:
        return error(message=f"外部学习资源检索失败：{str(e)}", code=500)

    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO operation_logs
                (user_id, action, target_type, target_id, detail)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user["id"],
                "A3_SEARCH_EXTERNAL_RESOURCES",
                "external_resources",
                None,
                json.dumps(
                    {
                        "course_name": request.course_name,
                        "topic": request.topic,
                        "learner_level": request.learner_level,
                        "max_results": request.max_results,
                        "result_count": len(result.get("resources", [])),
                        "queries": result.get("queries", [])
                    },
                    ensure_ascii=False
                )
            )
        )

        conn.commit()

    except Exception:
        conn.rollback()

    finally:
        cursor.close()
        conn.close()

    return success(
        data=result,
        message="外部学习资源检索成功"
    )