import json
import time
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pyexpat.errors import messages
from agents.resource_agent import generate_learning_resource
from agents.quiz_agent import generate_quiz_set
from agents.planner_agent import generate_learning_plan
from agents.orchestrator_agent import analyze_user_learning_request
from db import get_conn
from services.rag_service import search_similar_chunks
from models import AgentChatRequest
from utils import success, error, get_current_user
from services.external_resource_service import search_external_learning_resources

router = APIRouter(prefix="/agent", tags=["agent"])


def _stream_event(event_type: str, **payload):
    return json.dumps(
        {"type": event_type, **payload},
        ensure_ascii=False
    ) + "\n"


def _stream_reply(reply: str):
    text = reply or "处理完成"
    for index in range(0, len(text), 3):
        yield _stream_event("reply_delta", delta=text[index:index + 3])
        time.sleep(0.012)

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
        history_rows = list(cursor.fetchall())
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
        if plan.get("status") == "need_more_info":
            cursor.execute(
                """
                INSERT INTO agent_chat_messages
                    (user_id, role, content, tool_calls)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user["id"],
                    "assistant",
                    plan.get("reply", "请补充学习需求"),
                    json.dumps(
                        {
                            "plan": plan,
                            "tool_results": {}
                        },
                        ensure_ascii=False
                    )
                )
            )

            conn.commit()

            return success(
                data={
                    "plan": plan,
                    "tool_results": tool_results
                },
                message="AI助手需要补充信息"
            )

        # update_profile 和 qa 意图不需要 course_name 和 topic
        if plan.get("intent") in ("update_profile", "qa", "unknown"):
            cursor.execute(
                """
                INSERT INTO agent_chat_messages
                    (user_id, role, content, tool_calls)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user["id"],
                    "assistant",
                    plan.get("reply", "已完成"),
                    json.dumps(
                        {
                            "plan": plan,
                            "tool_results": {}
                        },
                        ensure_ascii=False
                    )
                )
            )
            conn.commit()

            return success(
                data={
                    "plan": plan,
                    "tool_results": tool_results
                },
                message="AI助手已回复"
            )

        content_tools = {"generate_resource", "generate_quiz", "generate_plan"}
        needs_course_context = bool(content_tools.intersection(tools))

        if needs_course_context and (not course_name or not topic):
            return success(
                data={
                    "tool_results":tool_results,
                    "plan": plan
                },
                message="AI助手已理解学生需求，但缺少课程名或知识点"
            )

        if "search_external_learning_resources" in tools and not topic:
            return success(
                data={
                    "tool_results":tool_results,
                    "plan": plan
                },
                message="AI助手已理解学生需求，但缺少知识点"
            )
        rag_context = []

        cursor.execute(
            """
            SELECT id, user_id, material_id, course_name, chunk_index, chunk_text, created_at
            FROM course_material_chunks
            WHERE user_id = %s AND course_name = %s
            ORDER BY id ASC
            """,
            (
                user["id"],
                course_name
            )
        )

        chunks = cursor.fetchall()

        rag_context = search_similar_chunks(
            query=topic,
            chunks=chunks,
            top_k=5
        ) if chunks else []
        if "generate_resource" in tools:
            resource = generate_learning_resource(
                course_name=course_name,
                topic=topic,
                profile=profile,
                rag_context=rag_context
            )
            resource["rag_references"] = [
                {
                    "chunk_id": item["id"],
                    "material_id": item["material_id"],
                    "chunk_index": item["chunk_index"],
                    "score": item["score"],
                    "snippet": item["chunk_text"][:200]
                }
                for item in rag_context
            ]
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
                profile=profile,
                rag_context=rag_context
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

        if "search_external_learning_resources" in tools:
            try:
                external_resources = search_external_learning_resources(
                    course_name=course_name or "",
                    topic=topic,
                    learner_level="beginner",
                    max_results=5
                )
                tool_results["external_resources"] = external_resources
            except Exception as e:
                tool_results["external_resources"] = {
                    "course_name": course_name,
                    "topic": topic,
                    "resources": [],
                    "error": str(e)
                }

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
                        "has_learning_plan": "learning_plan" in tool_results,
                        "rag_hit_count": len(rag_context),
                        "rag_chunk_ids": [item["id"] for item in rag_context]
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
                            "has_learning_plan": "learning_plan" in tool_results,
                            "rag_hit_count": len(rag_context),
                            "rag_chunk_ids": [item["id"] for item in rag_context]
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


@router.post("/chat/stream")
def agent_chat_stream(
        request: AgentChatRequest,
        user=Depends(get_current_user)
):
    def event_stream():
        conn = None
        cursor = None
        try:
            conn = get_conn()
            cursor = conn.cursor()

            yield _stream_event("status", message="正在记录你的问题")
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
                if isinstance(profile, str):
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
                (user["id"], user_message_id)
            )
            history_rows = list(cursor.fetchall())
            history_rows.reverse()

            yield _stream_event("status", message="正在理解学习需求")
            plan = analyze_user_learning_request(
                message=request.message,
                profile=profile,
                history=history_rows
            )

            tool_results = {}
            course_name = plan.get("course_name")
            topic = plan.get("topic")
            days = plan.get("days", 3)
            tools = plan.get("tools", [])

            if plan.get("status") == "need_more_info":
                reply = plan.get("reply", "请补充学习需求")
                cursor.execute(
                    """
                    INSERT INTO agent_chat_messages
                        (user_id, role, content, tool_calls)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        user["id"],
                        "assistant",
                        reply,
                        json.dumps(
                            {
                                "plan": plan,
                                "tool_results": {}
                            },
                            ensure_ascii=False
                        )
                    )
                )
                conn.commit()
                yield from _stream_reply(reply)
                yield _stream_event(
                    "result",
                    data={
                        "plan": plan,
                        "tool_results": tool_results
                    }
                )
                yield _stream_event("done")
                return

            if plan.get("intent") in ("update_profile", "qa", "unknown"):
                reply = plan.get("reply", "已完成")
                cursor.execute(
                    """
                    INSERT INTO agent_chat_messages
                        (user_id, role, content, tool_calls)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        user["id"],
                        "assistant",
                        reply,
                        json.dumps(
                            {
                                "plan": plan,
                                "tool_results": {}
                            },
                            ensure_ascii=False
                        )
                    )
                )
                conn.commit()
                yield from _stream_reply(reply)
                yield _stream_event(
                    "result",
                    data={
                        "plan": plan,
                        "tool_results": tool_results
                    }
                )
                yield _stream_event("done")
                return

            content_tools = {"generate_resource", "generate_quiz", "generate_plan"}
            needs_course_context = bool(content_tools.intersection(tools))

            if needs_course_context and (not course_name or not topic):
                reply = plan.get("reply", "我已理解需求，但还缺少课程名或知识点。")
                cursor.execute(
                    """
                    INSERT INTO agent_chat_messages
                        (user_id, role, content, tool_calls)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        user["id"],
                        "assistant",
                        reply,
                        json.dumps(
                            {
                                "plan": plan,
                                "tool_results": {}
                            },
                            ensure_ascii=False
                        )
                    )
                )
                conn.commit()
                yield from _stream_reply(reply)
                yield _stream_event(
                    "result",
                    data={
                        "plan": plan,
                        "tool_results": tool_results
                    }
                )
                yield _stream_event("done")
                return

            if "search_external_learning_resources" in tools and not topic:
                reply = plan.get("reply", "我已理解需求，但还缺少知识点。")
                cursor.execute(
                    """
                    INSERT INTO agent_chat_messages
                        (user_id, role, content, tool_calls)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        user["id"],
                        "assistant",
                        reply,
                        json.dumps(
                            {
                                "plan": plan,
                                "tool_results": {}
                            },
                            ensure_ascii=False
                        )
                    )
                )
                conn.commit()
                yield from _stream_reply(reply)
                yield _stream_event(
                    "result",
                    data={
                        "plan": plan,
                        "tool_results": tool_results
                    }
                )
                yield _stream_event("done")
                return

            yield _stream_event("status", message="正在检索课程知识库")
            cursor.execute(
                """
                SELECT id, user_id, material_id, course_name, chunk_index, chunk_text, created_at
                FROM course_material_chunks
                WHERE user_id = %s AND course_name = %s
                ORDER BY id ASC
                """,
                (
                    user["id"],
                    course_name
                )
            )

            chunks = cursor.fetchall()
            rag_context = search_similar_chunks(
                query=topic,
                chunks=chunks,
                top_k=5
            ) if chunks else []

            if "generate_resource" in tools:
                yield _stream_event("status", message="正在生成学习资源")
                resource = generate_learning_resource(
                    course_name=course_name,
                    topic=topic,
                    profile=profile,
                    rag_context=rag_context
                )
                resource["rag_references"] = [
                    {
                        "chunk_id": item["id"],
                        "material_id": item["material_id"],
                        "chunk_index": item["chunk_index"],
                        "score": item["score"],
                        "snippet": item["chunk_text"][:200]
                    }
                    for item in rag_context
                ]
                resource_json = json.dumps(resource, ensure_ascii=False)
                cursor.execute(
                    """
                    insert into learning_resources
                        (user_id,course_name,topic,resource_type,title,content,resource_json)
                        values(%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (user["id"], course_name, topic, resource["resource_type"], resource["title"], resource["content"], resource_json)
                )
                resource_id = cursor.lastrowid
                resource["id"] = resource_id
                tool_results["resource"] = resource

            if "generate_quiz" in tools:
                yield _stream_event("status", message="正在生成练习题")
                quiz_set = generate_quiz_set(
                    course_name=course_name,
                    topic=topic,
                    profile=profile,
                    rag_context=rag_context
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
                yield _stream_event("status", message="正在生成学习计划")
                learning_plan = generate_learning_plan(
                    course_name=course_name,
                    topic=topic,
                    days=days,
                    profile=profile
                )
                tool_results["learning_plan"] = learning_plan

            if "search_external_learning_resources" in tools:
                yield _stream_event("status", message="正在联网搜索学习资源")
                try:
                    external_resources = search_external_learning_resources(
                        course_name=course_name or "",
                        topic=topic,
                        learner_level="beginner",
                        max_results=5
                    )
                    tool_results["external_resources"] = external_resources
                except Exception as e:
                    tool_results["external_resources"] = {
                        "course_name": course_name,
                        "topic": topic,
                        "resources": [],
                        "error": str(e)
                    }

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
                            "has_learning_plan": "learning_plan" in tool_results,
                            "rag_hit_count": len(rag_context),
                            "rag_chunk_ids": [item["id"] for item in rag_context]
                        },
                        ensure_ascii=False
                    )
                )
            )

            reply = plan.get("reply", "已完成学习助手工具调度")
            cursor.execute(
                """
                INSERT INTO agent_chat_messages
                    (user_id, role, content, tool_calls)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user["id"],
                    "assistant",
                    reply,
                    json.dumps(
                        {
                            "plan": plan,
                            "tool_results": {
                                "resource_id": tool_results.get("resource", {}).get("id"),
                                "quiz_set_id": tool_results.get("quiz_set", {}).get("id"),
                                "has_learning_plan": "learning_plan" in tool_results,
                                "rag_hit_count": len(rag_context),
                                "rag_chunk_ids": [item["id"] for item in rag_context]
                            }
                        },
                        ensure_ascii=False
                    )
                )
            )
            conn.commit()

            yield from _stream_reply(reply)
            yield _stream_event(
                "result",
                data={
                    "plan": plan,
                    "tool_results": tool_results
                }
            )
            yield _stream_event("done")

        except ValueError as e:
            if conn:
                conn.rollback()
            yield _stream_event("error", message=str(e), code=400)
        except Exception as e:
            if conn:
                conn.rollback()
            yield _stream_event("error", message=f"AI助手处理失败：{str(e)}", code=500)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
