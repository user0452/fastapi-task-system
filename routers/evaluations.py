import json

from fastapi import APIRouter, Depends

from agents.evaluation_agent import evaluate_quiz_answers
from db import get_cursor
from models import EvaluationSubmitRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


def _load_json_list(value):
    if not value:
        return []

    try:
        data = json.loads(value)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        return []


@router.post("/submit")
def submit_learning_evaluation(
        request: EvaluationSubmitRequest,
        user=Depends(get_current_user)
):
    """
    提交练习题答案，并生成学习效果评估。
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT profile_json
                FROM student_profiles
                WHERE user_id = %s
                """,
                (user["id"],)
            )
            profile_row = cursor.fetchone()

            if profile_row is None:
                profile = None
            else:
                profile = json.loads(profile_row["profile_json"])
                if isinstance(profile, str):
                    profile = json.loads(profile)

            cursor.execute(
                """
                SELECT id, title, course_name, topic, quiz_json, created_at
                FROM quiz_sets
                WHERE id = %s AND user_id = %s
                """,
                (
                    request.quiz_set_id,
                    user["id"]
                )
            )

            quiz_set = cursor.fetchone()

            if quiz_set is None:
                return error(message="题集不存在或无访问权限", code=404)

            cursor.execute(
                """
                SELECT id, question_type, question, answer, difficulty, created_at
                FROM quiz_questions
                WHERE quiz_set_id = %s
                ORDER BY id ASC
                """,
                (request.quiz_set_id,)
            )

            questions = cursor.fetchall()

            if not questions:
                return error(message="该题集下没有可评估的题目", code=400)

            user_answers = [
                answer.model_dump()
                for answer in request.answers
            ]

            evaluation = evaluate_quiz_answers(
                quiz_set_id=quiz_set["id"],
                quiz_title=quiz_set["title"],
                questions=questions,
                user_answers=user_answers,
                profile=profile
            )

            evaluation_json = json.dumps(evaluation, ensure_ascii=False)

            cursor.execute(
                """
                INSERT INTO learning_evaluations
                    (user_id, quiz_set_id, score, level, weak_points_json, suggestions_json, evaluation_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user["id"],
                    request.quiz_set_id,
                    evaluation["score"],
                    evaluation["level"],
                    json.dumps(evaluation.get("weak_points", []), ensure_ascii=False),
                    json.dumps(evaluation.get("suggestions", []), ensure_ascii=False),
                    evaluation_json
                )
            )

            evaluation_id = cursor.lastrowid
            evaluation["id"] = evaluation_id

            cursor.execute(
                """
                INSERT INTO operation_logs
                    (user_id, action, target_type, target_id, detail)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    user["id"],
                    "A3_SUBMIT_LEARNING_EVALUATION",
                    "learning_evaluation",
                    evaluation_id,
                    json.dumps(
                        {
                            "quiz_set_id": request.quiz_set_id,
                            "score": evaluation["score"],
                            "level": evaluation["level"],
                            "weak_point_count": len(evaluation.get("weak_points", [])),
                            "suggestion_count": len(evaluation.get("suggestions", []))
                        },
                        ensure_ascii=False
                    )
                )
            )

            return success(
                data=evaluation,
                message="学习效果评估完成"
            )

    except ValueError as e:
        return error(message=str(e), code=400)

    except Exception as e:
        return error(message=f"学习效果评估失败：{str(e)}", code=500)


@router.get("")
def list_learning_evaluations(
        page: int = 1,
        size: int = 10,
        user=Depends(get_current_user)
):
    """
    查看当前用户的学习效果评估记录列表。
    """
    if page < 1:
        return error(message="page 必须大于等于 1", code=400)

    if size < 1 or size > 100:
        return error(message="size 必须在 1 到 100 之间", code=400)

    offset = (page - 1) * size

    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM learning_evaluations
                WHERE user_id = %s
                """,
                (user["id"],)
            )
            total_row = cursor.fetchone()
            total = total_row["total"]

            cursor.execute(
                """
                SELECT
                    le.id,
                    le.quiz_set_id,
                    le.score,
                    le.level,
                    le.weak_points_json,
                    le.suggestions_json,
                    le.created_at,
                    qs.title AS quiz_title,
                    qs.course_name,
                    qs.topic
                FROM learning_evaluations le
                LEFT JOIN quiz_sets qs ON le.quiz_set_id = qs.id
                WHERE le.user_id = %s
                ORDER BY le.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (
                    user["id"],
                    size,
                    offset
                )
            )

            rows = cursor.fetchall()

            items = []

            for row in rows:
                items.append(
                    {
                        "id": row["id"],
                        "quiz_set_id": row["quiz_set_id"],
                        "quiz_title": row["quiz_title"],
                        "course_name": row["course_name"],
                        "topic": row["topic"],
                        "score": row["score"],
                        "level": row["level"],
                        "weak_points": _load_json_list(row["weak_points_json"]),
                        "suggestions": _load_json_list(row["suggestions_json"]),
                        "created_at": row["created_at"]
                    }
                )

            return success(
                data={
                    "items": items,
                    "page": page,
                    "size": size,
                    "total": total
                },
                message="获取学习效果评估记录成功"
            )

    except Exception as e:
        return error(message=f"获取学习效果评估记录失败：{str(e)}", code=500)


@router.get("/{evaluation_id}")
def get_learning_evaluation_detail(
        evaluation_id: int,
        user=Depends(get_current_user)
):
    """
    查看某一次学习效果评估的详细结果。
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    le.id,
                    le.user_id,
                    le.quiz_set_id,
                    le.score,
                    le.level,
                    le.weak_points_json,
                    le.suggestions_json,
                    le.evaluation_json,
                    le.created_at,
                    qs.title AS quiz_title,
                    qs.course_name,
                    qs.topic
                FROM learning_evaluations le
                LEFT JOIN quiz_sets qs ON le.quiz_set_id = qs.id
                WHERE le.id = %s AND le.user_id = %s
                """,
                (
                    evaluation_id,
                    user["id"]
                )
            )

            row = cursor.fetchone()

            if row is None:
                return error(message="学习效果评估记录不存在或无访问权限", code=404)

            try:
                evaluation_data = json.loads(row["evaluation_json"])
            except json.JSONDecodeError:
                return error(message="学习效果评估记录格式错误", code=500)

            evaluation_data["id"] = row["id"]
            evaluation_data["quiz_set_id"] = row["quiz_set_id"]
            evaluation_data["quiz_title"] = row["quiz_title"]
            evaluation_data["course_name"] = row["course_name"]
            evaluation_data["topic"] = row["topic"]
            evaluation_data["created_at"] = row["created_at"]

            return success(
                data=evaluation_data,
                message="获取学习效果评估详情成功"
            )

    except Exception as e:
        return error(message=f"获取学习效果评估详情失败：{str(e)}", code=500)
