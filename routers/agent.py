import json
from fastapi import APIRouter, Depends
from pyexpat.errors import messages
from agents.resource_agent import generate_learning_resource
from agents.quiz_agent import generate_quiz_set
from agents.planner_agent import generate_learning_plan
from agents.orchestrator_agent import analyze_user_learning_request
from db import get_conn
from models import AgentChatRequest
from utils import success, error, get_current_user

router = APIRouter(prefix="/agent", tags=["agent"])

@router.post("/chat")
def agent_chat(
        request: AgentChatRequest,
        user=Depends(get_current_user)
):
    """
        AI 学习助手总入口第一版：
        先解析用户自然语言学习需求，规划后续工具调用。
        """
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO agent_chat_messages
                (user_id, role, content, tool_calls)
            VALUES (%s, %s, %s, %s)
            """,
            (
                user["id"],
                "user",
                request.message,
                None
            )
        )
        user_message_id = cursor.lastrowid
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
            profile = None
        else:
            profile = json.loads(row["profile_json"])
            if isinstance(profile,str):
                profile = json.loads(profile)
        cursor.execute(
            """
            select role,content
            from agent_chat_messages
                where user_id = %s
                and id < %s
                order by id desc
                limit 8
            """,
            (user["id"],user_message_id)

        )
        history_rows = cursor.fetchall()
        history_rows.reverse()
        plan = analyze_user_learning_request(
            message=request.message,
            profile=profile,
            history = history_rows
        )
        tool_results = {}
        course_name = plan.get("course_name")
        topic = plan.get("topic")
        days = plan.get("days",3)
        tools = plan.get("tools", [])
        if not course_name or not topic:
            return success(
                data={
                    "tool_results":tool_results,
                    "plan": plan
                },
                message="AI助手已理解学生需求，但缺少课程名或知识点"
            )
        if "generate_resource" in tools:
            resource = generate_learning_resource(
                course_name=course_name,
                topic=topic,
                profile=profile
            )
            resource_json = json.dumps(resource,ensure_ascii=False)
            cursor.execute(
                """
                insert into learning_resources
                    (user_id,course_name,topic,resource_type,title,content,resource_json)
                    values(%s,%s,%s,%s,%s,%s,%s)
                """,
                (user["id"],course_name,topic,resource["resource_type"],resource["title"],resource["content"],resource_json)
            )
            resource_id = cursor.lastrowid
            resource["id"] = resource_id
            tool_results["resource"] = resource


        if "generate_quiz" in tools:
            quiz_set = generate_quiz_set(
                course_name=course_name,
                topic=topic,
                profile=profile
            )

            quiz_json = json.dumps(quiz_set, ensure_ascii=False)

            cursor.execute(
                """
                INSERT INTO quiz_sets
                    (user_id, title, course_name, topic, quiz_json)
                VALUES (%s, %s, %s, %s, %s)
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
                    INSERT INTO quiz_questions
                        (quiz_set_id, question_type, question, answer, difficulty)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        quiz_set_id,
                        question["question_type"],
                        question["question"],
                        question["answer"],
                        question["difficulty"]
                    )
                )

            quiz_set["id"] = quiz_set_id
            tool_results["quiz_set"] = quiz_set

        if "generate_plan" in tools:
            learning_plan = generate_learning_plan(
                course_name=course_name,
                topic=topic,
                days=days,
                profile=profile
            )
            tool_results["learning_plan"] = learning_plan

        cursor.execute(
            """
            INSERT INTO operation_logs
                (user_id, action, target_type, target_id, detail)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user["id"],
                "A3_AGENT_CHAT_DISPATCH",
                "agent_chat",
                None,
                json.dumps(
                    {
                        "intent": plan.get("intent"),
                        "course_name": course_name,
                        "topic": topic,
                        "days": days,
                        "tools": tools,
                        "resource_id": tool_results.get("resource", {}).get("id"),
                        "quiz_set_id": tool_results.get("quiz_set", {}).get("id"),
                        "has_learning_plan": "learning_plan" in tool_results
                    },
                    ensure_ascii=False
                )
            )
        )

        cursor.execute(
            """
            INSERT INTO agent_chat_messages
                (user_id, role, content, tool_calls)
            VALUES (%s, %s, %s, %s)
            """,
            (
                user["id"],
                "assistant",
                plan.get("reply", "已完成学习助手工具调度"),
                json.dumps(
                    {
                        "plan": plan,
                        "tool_results": {
                            "resource_id": tool_results.get("resource", {}).get("id"),
                            "quiz_set_id": tool_results.get("quiz_set", {}).get("id"),
                            "has_learning_plan": "learning_plan" in tool_results
                        }
                    },
                    ensure_ascii=False
                )
            )
        )
        user_message_id = cursor.lastrowid
        conn.commit()

        return success(
            data={
                "plan": plan,
                "tool_results":tool_results
            },
            message = "AI助手已理解学生需求并完成工具调度"
        )

    except ValueError as e:
        conn.rollback()
        return error(
            message=str(e),
            code=400
        )
    except Exception as e:
        conn.rollback()
        return error(
            message=f"AI助手处理失败：{str(e)}",
            code=500
        )
    finally:
        cursor.close()
        conn.close()