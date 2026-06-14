import json

from fastapi import APIRouter, Depends
from services.rag_service import split_text_to_chunks,search_similar_chunks
from db import get_conn
from models import MaterialCreateRequest,MaterialSearchRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/materials", tags=["materials"])

@router.post("")
def create_material(request: MaterialCreateRequest, user=Depends(get_current_user)):
    """
    保存当前用户课程资料，第一版只支持手动粘贴文本创建
    :param request:
    :param user:
    :return:
    """
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            insert into course_materials
                (user_id,course_name,title,content)
            values (%s,%s,%s,%s)
            """,
            (user["id"],request.course_name,request.title,request.content)
        )
        material_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO operation_logs
                (user_id, action, target_type, target_id, detail)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user["id"],
                "A3_UPLOAD_COURSE_MATERIAL",
                "course_material",
                material_id,
                json.dumps(
                    {
                        "course_name": request.course_name,
                        "title": request.title,
                        "content_length": len(request.content)
                    },
                    ensure_ascii=False
                )
            )
        )
        conn.commit()
        return success(
            data={
                "id": material_id,
                "course_name": request.course_name,
                "title": request.title
            },
            message="课程资料保存成功"
        )

    except Exception as e:
        conn.rollback()
        return error(
            message=f"课程资料保存失败：{str(e)}",
            code=500
        )

    finally:
        cursor.close()
        conn.close()

@router.get("")
def get_materials(
        course_name: str | None = None,
        page: int = 1,
        size: int = 10,
        user=Depends(get_current_user)
):
    """
    获取当前用户保存的课程资料列表。
    """
    if page < 1 or size < 1:
        return error(message="page 和 size 必须大于 0", code=400)

    if size > 100:
        return error(message="size 不能大于 100", code=400)

    conn = get_conn()
    cursor = conn.cursor()

    try:
        offset = (page - 1) * size

        if course_name:
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM course_materials
                WHERE user_id = %s AND course_name = %s
                """,
                (user["id"], course_name)
            )
            total = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT id, user_id, course_name, title, created_at
                FROM course_materials
                WHERE user_id = %s AND course_name = %s
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (user["id"], course_name, size, offset)
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM course_materials
                WHERE user_id = %s
                """,
                (user["id"],)
            )
            total = cursor.fetchone()["total"]

            cursor.execute(
                """
                SELECT id, user_id, course_name, title, created_at
                FROM course_materials
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (user["id"], size, offset)
            )

        items = cursor.fetchall()

        return success(
            data={
                "total": total,
                "list": items,
                "page": page,
                "size": size
            },
            message="获取课程资料成功"
        )

    except Exception as e:
        return error(
            message=f"获取课程资料失败：{str(e)}",
            code=500
        )

    finally:
        cursor.close()
        conn.close()


@router.post("/{material_id}/build-index")
def build_material_index(
        material_id: int,
        user=Depends(get_current_user)
):
    """
    为某一份课程资料构建 RAG chunks。
    第一版只做文本切分并保存到 course_material_chunks。
    """
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, user_id, course_name, title, content
            FROM course_materials
            WHERE id = %s AND user_id = %s
            """,
            (
                material_id,
                user["id"]
            )
        )

        material = cursor.fetchone()

        if material is None:
            return error(message="课程资料不存在", code=404)

        chunks = split_text_to_chunks(material["content"])

        if not chunks:
            return error(message="课程资料内容为空，无法构建索引", code=400)

        cursor.execute(
            """
            DELETE FROM course_material_chunks
            WHERE material_id = %s AND user_id = %s
            """,
            (
                material_id,
                user["id"]
            )
        )

        for index, chunk_text in enumerate(chunks):
            cursor.execute(
                """
                INSERT INTO course_material_chunks
                    (user_id, material_id, course_name, chunk_index, chunk_text)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    user["id"],
                    material_id,
                    material["course_name"],
                    index,
                    chunk_text
                )
            )

        cursor.execute(
            """
            INSERT INTO operation_logs
                (user_id, action, target_type, target_id, detail)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user["id"],
                "A3_BUILD_MATERIAL_INDEX",
                "course_material",
                material_id,
                json.dumps(
                    {
                        "course_name": material["course_name"],
                        "title": material["title"],
                        "chunk_count": len(chunks)
                    },
                    ensure_ascii=False
                )
            )
        )

        conn.commit()

        return success(
            data={
                "material_id": material_id,
                "course_name": material["course_name"],
                "title": material["title"],
                "chunk_count": len(chunks)
            },
            message="课程资料索引构建成功"
        )

    except Exception as e:
        conn.rollback()
        return error(
            message=f"课程资料索引构建失败：{str(e)}",
            code=500
        )

    finally:
        cursor.close()
        conn.close()



@router.post("/rag-search")
def rag_search_materials(
        request: MaterialSearchRequest,
        user=Depends(get_current_user)
):
    """
    真正的 RAG 向量检索：
    从 course_material_chunks 中取出课程资料片段，
    使用 embedding + FAISS 检索与 topic 最相关的片段。
    """
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, user_id, material_id, course_name, chunk_index, chunk_text, created_at
            FROM course_material_chunks
            WHERE user_id = %s AND course_name = %s
            ORDER BY id ASC
            """,
            (
                user["id"],
                request.course_name
            )
        )

        chunks = cursor.fetchall()

        if not chunks:
            return success(
                data={
                    "total": 0,
                    "list": [],
                    "course_name": request.course_name,
                    "topic": request.topic
                },
                message="没有可检索的课程资料片段，请先构建课程资料索引"
            )

        results = search_similar_chunks(
            query=request.topic,
            chunks=chunks,
            top_k=5
        )

        return success(
            data={
                "total": len(results),
                "list": results,
                "course_name": request.course_name,
                "topic": request.topic
            },
            message="RAG 向量检索成功"
        )

    except Exception as e:
        return error(
            message=f"RAG 向量检索失败：{str(e)}",
            code=500
        )

    finally:
        cursor.close()
        conn.close()