import json

from fastapi import APIRouter, Depends
from pyexpat.errors import messages
from services.rag_service import search_similar_chunks
from agents.quiz_agent import generate_quiz_set
from db import get_conn
from models import QuizGenerateRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/quizzes", tags=["quizzes"])
@router.post("/generate")
def generate_quiz_api(request: QuizGenerateRequest, user=Depends(get_current_user)):
    "根据用户输入的课程名和知识点，生成考题"
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            select profile_json
            from student_profiles
            where user_id = %s
            """,
            (user["id"],)
        )
        row = cursor.fetchone()
        if row is None:
            profile =  None
        else:
            profile = json.loads(row["profile_json"])
            if isinstance(profile,str):
                profile = json.loads(profile)
        cursor.execute(
            """
            select id, user_id, material_id, course_name, chunk_index, chunk_text, created_at
            from course_material_chunks
                where user_id = %s and course_name = %s
                order by id asc
            """,
            (user["id"],request.course_name)
        )
        chunks = cursor.fetchall()
        rag_context = search_similar_chunks(
            query=request.topic,
            chunks=chunks,
            top_k=5
        ) if chunks else []
        quiz_set = generate_quiz_set(
            request.course_name,request.topic,profile,rag_context
        )
        quiz_set["rag_references"] = [
            {
                "chunk_id": item["id"],
                "material_id": item["material_id"],
                "chunk_index": item["chunk_index"],
                "score": item["score"],
                "snippet": item["chunk_text"][:200]
            }
            for item in rag_context
        ]
        quiz_json = json.dumps(quiz_set,ensure_ascii=False)
        cursor.execute(
            """
            insert into quiz_sets (user_id,title,course_name,topic,quiz_json)
                values(%s,%s,%s,%s,%s)
            """,
            (
                user["id"],
                quiz_set["title"],
                quiz_set["course_name"],
                quiz_set["topic"],
                quiz_json
            )
        )
        quiz_set_id = cursor.lastrowid
        for question in quiz_set["questions"]:
            cursor.execute(
                """
                insert into quiz_questions (quiz_set_id,question_type,question,answer,difficulty)
                    values (%s,%s,%s,%s,%s)
                """,
                (quiz_set_id,question["question_type"],question["question"],question["answer"],question["difficulty"])
            )
        cursor.execute(
            """
            insert into operation_logs
                (user_id,action,target_type,target_id,detail)
                values (%s,%s,%s,%s,%s)
            """,
            (
            user["id"],
                "A3_GENERATE_QUIZ_SET",
                "quiz_set",
                quiz_set_id,
                json.dumps(
                    {
                        "source":"a3_quiz_agent",
                        "course_name":request.course_name,
                        "topic":request.topic,
                        "quiz_set_id":quiz_set_id,
                        "title":quiz_set["title"],
                        "question_count":len(quiz_set["questions"]),
                        "rag_hit_count": len(rag_context),
                        "rag_chunk_ids": [item["id"] for item in rag_context]
                    },
                    ensure_ascii=False
                )

            )

        )
        conn.commit()

        return success(
            data={
                "id":quiz_set_id,
                "quiz_set":quiz_set
            },
            message="练习题生成并保存成功"
        )
    except ValueError as e:
        conn.rollback()
        return error(message=str(e),code=400)
    except Exception as e:
        conn.rollback()
        return error(message=f"练习题生成失败：{str(e)}",code=500)
    finally:
        cursor.close()
        conn.close()

@router.get("")
def get_my_quizzes(
        user=Depends(get_current_user),
        page:int = 1,
        size:int = 10
):
    """获取我的所有练习题"""
    if page < 1 or size < 1:
        return error(message="页码和每页数量必须大于0",code=400)
    if size > 100:
        return error(message="每页数量不能大于100",code=400)

    conn = get_conn()
    cursor = conn.cursor()
    try:
        offset = (page - 1) * size
        cursor.execute(
             """
             select count(*) as total
             from quiz_sets
             where user_id = %s
             """,
            (user["id"],)
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            """
            select id, title, course_name, topic, created_at
            from quiz_sets
                where user_id = %s
                order by id desc
                limit %s offset %s
            """,
            (user["id"],size,offset)
        )
        items = cursor.fetchall()
        return success(
            data={
                "total":total,
                "list":items,
                "page":page,
                "size":size
            },
            message = "获取题集列表成功"
        )
    except Exception as e:
        return error(message=f"获取题集列表失败：{str(e)}",code=500)
    finally:
         cursor.close()
         conn.close()

@router.get("/{quiz_set_id}")
def get_quiz_set(quiz_set_id:int,user=Depends(get_current_user)):
    """获取指定练习题"""
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            select id,user_id,title,course_name,topic,quiz_json,created_at
            from quiz_sets
                where id = %s
                and user_id = %s
            """,
            (quiz_set_id,user["id"])
        )
        quiz_set = cursor.fetchone()
        if quiz_set is None:
            return error(message="指定的练习题不存在",code=404)
        cursor.execute(
            """
            select id,question_type,question,answer,difficulty,created_at
            from quiz_questions
                where  quiz_set_id = %s

            """,
            (quiz_set_id,)
        )
        questions = cursor.fetchall()
        quiz_json = json.loads(quiz_set["quiz_json"])

        if isinstance(quiz_json,str):
            quiz_json = json.loads(quiz_json)
        return success(
            data={
                "id":quiz_set["id"],
                "title":quiz_set["title"],
                "course_name":quiz_set["course_name"],
                "topic":quiz_set["topic"],
                "created_at":quiz_set["created_at"],
                "user_id":quiz_set["user_id"],
                "questions":questions,
                "quiz_json":quiz_json

            },
            message="获取练习题成功"
        )
    except Exception as e:
        return error(message=f"获取练习题失败：{str(e)}",code=500)
    finally:
        cursor.close()
        conn.close()
