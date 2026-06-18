import json
import time
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agents.evaluation_agent import evaluate_quiz_answers
from agents.orchestrator_agent import analyze_user_learning_request
from agents.planner_agent import generate_learning_plan
from agents.profile_agent import generate_student_profile
from agents.quiz_agent import generate_quiz_set
from agents.resource_agent import generate_learning_resource
from db import get_conn
from llm_client import parse_exam_schedule, preview_review_plan
from models import AgentChatRequest
from services.external_resource_service import search_external_learning_resources
from services.rag_service import search_similar_chunks, split_text_to_chunks
from utils import (
    error,
    get_current_user,
    get_owned_task,
    is_valid_priority,
    is_valid_status,
    success,
)

router = APIRouter(prefix="/agent", tags=["agent"])

KNOWN_AGENT_TOOLS = {
    "generate_profile",
    "get_profile",
    "create_material",
    "list_materials",
    "build_material_index",
    "rag_search_materials",
    "generate_resource",
    "list_resources",
    "get_resource",
    "generate_quiz",
    "list_quizzes",
    "get_quiz",
    "generate_plan",
    "import_plan_tasks",
    "search_external_learning_resources",
    "create_task",
    "list_tasks",
    "get_task",
    "update_task",
    "delete_task",
    "bulk_update_tasks_status",
    "bulk_delete_tasks_status",
    "submit_evaluation",
    "list_evaluations",
    "get_evaluation",
    "parse_exam_schedule",
    "preview_review_plan",
    "import_review_plan_tasks",
    "list_operation_logs",
}


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _json_loads(value: Any, default: Any = None) -> Any:
    if value is None:
        return default

    if isinstance(value, (dict, list)):
        return value

    if not isinstance(value, str) or not value.strip():
        return default

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _stream_event(event_type: str, **payload):
    return _json_dumps({"type": event_type, **payload}) + "\n"


def _stream_reply(reply: str):
    text = reply or "处理完成"
    for index in range(0, len(text), 3):
        yield _stream_event("reply_delta", delta=text[index:index + 3])
        time.sleep(0.012)


def _require_text(value: Any, message: str) -> str:
    if value is None:
        raise ValueError(message)

    text = str(value).strip()
    if not text:
        raise ValueError(message)

    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _to_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_size(args: dict, default_size: int = 10) -> tuple[int, int]:
    page = _to_int(args.get("page"), 1) or 1
    size = _to_int(args.get("size"), default_size) or default_size

    if page < 1:
        page = 1

    if size < 1:
        size = default_size

    if size > 100:
        size = 100

    return page, size


def _get_tool_args(plan: dict, tool: str) -> dict:
    tool_args = plan.get("tool_args") or {}

    if not isinstance(tool_args, dict):
        return {}

    nested_args = tool_args.get(tool)
    if isinstance(nested_args, dict):
        return nested_args

    # 兼容单工具时模型直接把参数放在 tool_args 根上的情况。
    if len(plan.get("tools") or []) == 1 and not any(name in tool_args for name in KNOWN_AGENT_TOOLS):
        return tool_args

    return {}


def _course_topic_days(plan: dict, tool: str) -> tuple[str, str, int]:
    args = _get_tool_args(plan, tool)
    course_name = _require_text(
        args.get("course_name") or plan.get("course_name"),
        "缺少课程名，请补充 course_name"
    )
    topic = _require_text(
        args.get("topic") or plan.get("topic"),
        "缺少知识点，请补充 topic"
    )
    days = _to_int(args.get("days") or plan.get("days"), 3) or 3
    days = max(1, min(days, 30))
    return course_name, topic, days


def _load_profile(cursor, user_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT profile_json
        FROM student_profiles
        WHERE user_id = %s
        """,
        (user_id,)
    )
    row = cursor.fetchone()

    if row is None:
        return None

    profile = _json_loads(row["profile_json"], None)
    if isinstance(profile, str):
        profile = _json_loads(profile, None)

    return profile if isinstance(profile, dict) else None


def _load_profile_detail(cursor, user_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, user_id, profile_json, created_at, updated_at
        FROM student_profiles
        WHERE user_id = %s
        """,
        (user_id,)
    )
    row = cursor.fetchone()

    if row is None:
        return None

    profile = _json_loads(row["profile_json"], None)
    if isinstance(profile, str):
        profile = _json_loads(profile, None)

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "profile": profile,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }


def _insert_log(cursor, user_id: int, action: str, target_type: str | None, target_id: int | None, detail: dict):
    cursor.execute(
        """
        INSERT INTO operation_logs
            (user_id, action, target_type, target_id, detail)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            user_id,
            action,
            target_type,
            target_id,
            _json_dumps(detail)
        )
    )


def _insert_chat_message(cursor, user_id: int, role: str, content: str, tool_calls: dict | None = None) -> int:
    cursor.execute(
        """
        INSERT INTO agent_chat_messages
            (user_id, role, content, tool_calls)
        VALUES (%s, %s, %s, %s)
        """,
        (
            user_id,
            role,
            content,
            _json_dumps(tool_calls) if tool_calls is not None else None
        )
    )
    return cursor.lastrowid


def _compact_result_for_history(key: str, value: Any) -> Any:
    if isinstance(value, list):
        return {
            "count": len(value),
            "items": value[:3]
        }

    if not isinstance(value, dict):
        return value

    if key == "learning_plan":
        return {
            "plan_title": value.get("plan_title"),
            "course_name": value.get("course_name"),
            "topic": value.get("topic"),
            "days": value.get("days"),
            "task_count": len(value.get("tasks_preview") or []),
            "can_import": bool(value.get("tasks_preview"))
        }

    if key == "review_plan":
        return {
            "task_count": len(value.get("tasks_preview") or []),
            "can_import": bool(value.get("tasks_preview"))
        }

    if key == "external_resources":
        resources = value.get("resources") or []
        return {
            "course_name": value.get("course_name"),
            "topic": value.get("topic"),
            "learner_level": value.get("learner_level"),
            "total": value.get("total", len(resources)),
            "sources": sorted({
                item.get("source")
                for item in resources
                if item.get("source")
            }),
            "resource_types": sorted({
                item.get("resource_type")
                for item in resources
                if item.get("resource_type")
            }),
            "error": value.get("error")
        }

    if key in {"resource", "quiz_set", "material", "task", "evaluation"}:
        return {
            item_key: value.get(item_key)
            for item_key in [
                "id",
                "title",
                "plan_title",
                "course_name",
                "topic",
                "score",
                "level",
                "status",
                "priority"
            ]
            if item_key in value
        }

    if "list" in value:
        return {
            "total": value.get("total"),
            "page": value.get("page"),
            "size": value.get("size"),
            "list": (value.get("list") or [])[:3]
        }

    if "items" in value:
        return {
            "total": value.get("total"),
            "page": value.get("page"),
            "size": value.get("size"),
            "items": (value.get("items") or [])[:3]
        }

    return value


def _build_agent_summary(plan: dict, tool_results: dict) -> dict:
    external_resources = tool_results.get("external_resources") or {}
    external_items = external_resources.get("resources") or []
    rag_references = []

    for key in ("resource", "quiz_set"):
        item = tool_results.get(key)
        if isinstance(item, dict):
            rag_references.extend(item.get("rag_references") or [])

    return {
        "intent": plan.get("intent"),
        "tools": plan.get("tools") or [],
        "course_name": plan.get("course_name"),
        "topic": plan.get("topic"),
        "resource_id": tool_results.get("resource", {}).get("id"),
        "quiz_set_id": tool_results.get("quiz_set", {}).get("id"),
        "has_learning_plan": "learning_plan" in tool_results,
        "has_external_resources": "external_resources" in tool_results,
        "external_resource_count": len(external_items),
        "external_resource_sources": sorted({
            item.get("source")
            for item in external_items
            if item.get("source")
        }),
        "rag_hit_count": len(rag_references),
        "rag_chunk_ids": sorted({
            item.get("chunk_id")
            for item in rag_references
            if item.get("chunk_id") is not None
        })
    }


def _compact_tool_calls_for_storage(plan: dict, tool_results: dict) -> dict:
    stored_results = {}

    for key, value in tool_results.items():
        if key in {"learning_plan", "review_plan"}:
            stored_results[key] = value
        else:
            stored_results[key] = _compact_result_for_history(key, value)

    return {
        "plan": plan,
        "summary": _build_agent_summary(plan, tool_results),
        "tool_results": stored_results
    }


def _compact_tool_calls_for_history(value: Any) -> Any:
    tool_calls = _json_loads(value, None)
    if not isinstance(tool_calls, dict):
        return None

    plan = tool_calls.get("plan") or {}
    results = tool_calls.get("tool_results") or {}

    return {
        "plan": {
            "intent": plan.get("intent"),
            "course_name": plan.get("course_name"),
            "topic": plan.get("topic"),
            "days": plan.get("days"),
            "tools": plan.get("tools")
        },
        "tool_results": {
            key: _compact_result_for_history(key, value)
            for key, value in results.items()
        }
    }


def _fetch_chat_history(cursor, user_id: int, before_message_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT role, content, tool_calls
        FROM agent_chat_messages
        WHERE user_id = %s
          AND id < %s
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id, before_message_id)
    )
    rows = list(cursor.fetchall())
    rows.reverse()

    history = []
    for row in rows:
        item = {
            "role": row["role"],
            "content": row["content"]
        }
        compact_tool_calls = _compact_tool_calls_for_history(row.get("tool_calls"))
        if compact_tool_calls:
            item["tool_calls"] = compact_tool_calls
        history.append(item)

    return history


def _find_latest_tool_result(cursor, user_id: int, result_key: str) -> dict | None:
    cursor.execute(
        """
        SELECT tool_calls
        FROM agent_chat_messages
        WHERE user_id = %s
          AND role = 'assistant'
          AND tool_calls IS NOT NULL
        ORDER BY id DESC
        LIMIT 20
        """,
        (user_id,)
    )

    for row in cursor.fetchall():
        tool_calls = _json_loads(row.get("tool_calls"), None)
        if not isinstance(tool_calls, dict):
            continue

        tool_results = tool_calls.get("tool_results") or {}
        result = tool_results.get(result_key)
        if isinstance(result, dict):
            return result

    return None


def _get_course_chunks(cursor, user_id: int, course_name: str) -> list[dict]:
    cursor.execute(
        """
        SELECT id, user_id, material_id, course_name, chunk_index, chunk_text, created_at
        FROM course_material_chunks
        WHERE user_id = %s AND course_name = %s
        ORDER BY id ASC
        """,
        (user_id, course_name)
    )
    return cursor.fetchall()


def _build_rag_references(rag_context: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": item["id"],
            "material_id": item["material_id"],
            "chunk_index": item["chunk_index"],
            "score": item["score"],
            "snippet": item["chunk_text"][:200]
        }
        for item in rag_context
    ]


def _save_learning_resource(cursor, user_id: int, course_name: str, topic: str, resource: dict) -> dict:
    resource_json = _json_dumps(resource)
    cursor.execute(
        """
        INSERT INTO learning_resources
            (user_id, course_name, topic, resource_type, title, content, resource_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            course_name,
            topic,
            resource["resource_type"],
            resource["title"],
            resource["content"],
            resource_json
        )
    )
    resource["id"] = cursor.lastrowid
    return resource


def _save_quiz_set(cursor, user_id: int, quiz_set: dict) -> dict:
    quiz_json = _json_dumps(quiz_set)
    cursor.execute(
        """
        INSERT INTO quiz_sets
            (user_id, title, course_name, topic, quiz_json)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            user_id,
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
    return quiz_set


def _create_tasks_from_preview(cursor, user_id: int, tasks_preview: list[dict], source: str) -> dict:
    if not tasks_preview:
        raise ValueError("任务预览不能为空")

    created_count = 0
    task_ids = []
    created_tasks = []

    for task in tasks_preview:
        title = _require_text(task.get("title"), "任务标题不能为空")
        description = str(task.get("description") or "")
        status = task.get("status") or "todo"
        priority = task.get("priority") or "medium"

        if not is_valid_status(status):
            raise ValueError("任务状态不合法")

        if not is_valid_priority(priority):
            raise ValueError("任务优先级不合法")

        cursor.execute(
            """
            INSERT INTO tasks
                (user_id, title, description, status, priority)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user_id,
                title,
                description,
                status,
                priority
            )
        )
        task_id = cursor.lastrowid
        task_ids.append(task_id)
        created_count += 1

        cursor.execute(
            """
            SELECT id, title, description, status, priority, created_at, updated_at
            FROM tasks
            WHERE id = %s AND user_id = %s
            """,
            (task_id, user_id)
        )
        created_tasks.append(cursor.fetchone())

    _insert_log(
        cursor,
        user_id,
        "A3_AGENT_IMPORT_TASKS",
        "task",
        None,
        {
            "source": source,
            "created_count": created_count,
            "task_ids": task_ids,
            "task_titles": [task.get("title") for task in tasks_preview]
        }
    )

    return {
        "created_count": created_count,
        "task_ids": task_ids,
        "items": created_tasks
    }


def _list_tasks(cursor, user_id: int, args: dict) -> dict:
    page, size = _page_size(args)
    status = _optional_text(args.get("status"))

    if status is not None and not is_valid_status(status):
        raise ValueError("status 参数不合法")

    offset = (page - 1) * size

    if status is None:
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM tasks
            WHERE user_id = %s
            """,
            (user_id,)
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT id, title, description, status, priority, created_at, updated_at
            FROM tasks
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, size, offset)
        )
    else:
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM tasks
            WHERE user_id = %s AND status = %s
            """,
            (user_id, status)
        )
        total = cursor.fetchone()["total"]
        cursor.execute(
            """
            SELECT id, title, description, status, priority, created_at, updated_at
            FROM tasks
            WHERE user_id = %s AND status = %s
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, status, size, offset)
        )

    return {
        "list": cursor.fetchall(),
        "total": total,
        "page": page,
        "size": size,
        "status": status
    }


def _load_quiz_questions(cursor, quiz_set_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT id, question_type, question, answer, difficulty, created_at
        FROM quiz_questions
        WHERE quiz_set_id = %s
        ORDER BY id ASC
        """,
        (quiz_set_id,)
    )
    return cursor.fetchall()


def _load_json_list(value):
    data = _json_loads(value, [])
    return data if isinstance(data, list) else []


def _execute_agent_tools(plan: dict, cursor, user: dict, profile: dict | None, original_message: str):
    tool_results = {}
    active_profile = profile

    for tool in plan.get("tools") or []:
        args = _get_tool_args(plan, tool)

        if tool == "generate_profile":
            yield {"type": "status", "message": "正在生成学生画像"}
            text = _require_text(args.get("text") or original_message, "缺少画像描述文本")
            active_profile = generate_student_profile(text)
            cursor.execute(
                """
                INSERT INTO student_profiles (user_id, profile_json)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE
                    profile_json = VALUES(profile_json),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user["id"], _json_dumps(active_profile))
            )
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_GENERATE_PROFILE",
                "student_profile",
                None,
                {
                    "source": "agent_chat",
                    "text_length": len(text)
                }
            )
            tool_results["profile"] = active_profile
            continue

        if tool == "get_profile":
            yield {"type": "status", "message": "正在读取学生画像"}
            tool_results["profile_detail"] = _load_profile_detail(cursor, user["id"])
            continue

        if tool == "create_material":
            yield {"type": "status", "message": "正在保存课程资料"}
            course_name = _require_text(args.get("course_name") or plan.get("course_name"), "缺少课程名")
            title = _require_text(args.get("title"), "缺少资料标题")
            content = _require_text(args.get("content"), "缺少资料内容")
            cursor.execute(
                """
                INSERT INTO course_materials
                    (user_id, course_name, title, content)
                VALUES (%s, %s, %s, %s)
                """,
                (user["id"], course_name, title, content)
            )
            material_id = cursor.lastrowid
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_CREATE_COURSE_MATERIAL",
                "course_material",
                material_id,
                {
                    "course_name": course_name,
                    "title": title,
                    "content_length": len(content)
                }
            )
            tool_results["material"] = {
                "id": material_id,
                "course_name": course_name,
                "title": title,
                "content_preview": content[:300]
            }
            continue

        if tool == "list_materials":
            yield {"type": "status", "message": "正在查询课程资料"}
            page, size = _page_size(args)
            offset = (page - 1) * size
            course_name = _optional_text(args.get("course_name") or plan.get("course_name"))

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

            tool_results["materials"] = {
                "total": total,
                "list": cursor.fetchall(),
                "page": page,
                "size": size,
                "course_name": course_name
            }
            continue

        if tool == "build_material_index":
            yield {"type": "status", "message": "正在构建课程资料索引"}
            material_id = _to_int(args.get("material_id") or args.get("id"))
            if material_id is None:
                raise ValueError("缺少资料 id")

            cursor.execute(
                """
                SELECT id, user_id, course_name, title, content
                FROM course_materials
                WHERE id = %s AND user_id = %s
                """,
                (material_id, user["id"])
            )
            material = cursor.fetchone()
            if material is None:
                raise ValueError("课程资料不存在")

            chunks = split_text_to_chunks(material["content"])
            if not chunks:
                raise ValueError("课程资料内容为空，无法构建索引")

            cursor.execute(
                """
                DELETE FROM course_material_chunks
                WHERE material_id = %s AND user_id = %s
                """,
                (material_id, user["id"])
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

            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_BUILD_MATERIAL_INDEX",
                "course_material",
                material_id,
                {
                    "course_name": material["course_name"],
                    "title": material["title"],
                    "chunk_count": len(chunks)
                }
            )

            tool_results["material_index"] = {
                "material_id": material_id,
                "course_name": material["course_name"],
                "title": material["title"],
                "chunk_count": len(chunks)
            }
            continue

        if tool == "rag_search_materials":
            yield {"type": "status", "message": "正在检索课程资料"}
            course_name, topic, _days = _course_topic_days(plan, tool)
            chunks = _get_course_chunks(cursor, user["id"], course_name)
            results = search_similar_chunks(query=topic, chunks=chunks, top_k=5) if chunks else []
            tool_results["rag_search"] = {
                "total": len(results),
                "list": results,
                "course_name": course_name,
                "topic": topic
            }
            continue

        if tool == "generate_resource":
            yield {"type": "status", "message": "正在生成学习资源"}
            course_name, topic, _days = _course_topic_days(plan, tool)
            chunks = _get_course_chunks(cursor, user["id"], course_name)
            rag_context = search_similar_chunks(query=topic, chunks=chunks, top_k=5) if chunks else []
            resource = generate_learning_resource(
                course_name=course_name,
                topic=topic,
                profile=active_profile,
                rag_context=rag_context
            )
            resource["rag_references"] = _build_rag_references(rag_context)
            resource = _save_learning_resource(cursor, user["id"], course_name, topic, resource)
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_GENERATE_LEARNING_RESOURCE",
                "learning_resource",
                resource["id"],
                {
                    "source": "agent_chat",
                    "course_name": course_name,
                    "topic": topic,
                    "resource_id": resource["id"],
                    "title": resource["title"],
                    "resource_type": resource["resource_type"],
                    "rag_hit_count": len(rag_context),
                    "rag_chunk_ids": [item["id"] for item in rag_context]
                }
            )
            tool_results["resource"] = resource
            continue

        if tool == "list_resources":
            yield {"type": "status", "message": "正在查询学习资源"}
            page, size = _page_size(args)
            offset = (page - 1) * size
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM learning_resources
                WHERE user_id = %s
                """,
                (user["id"],)
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                """
                SELECT id, user_id, course_name, topic, resource_type, title, created_at
                FROM learning_resources
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (user["id"], size, offset)
            )
            tool_results["resources"] = {
                "total": total,
                "list": cursor.fetchall(),
                "page": page,
                "size": size
            }
            continue

        if tool == "get_resource":
            yield {"type": "status", "message": "正在读取学习资源详情"}
            resource_id = _to_int(args.get("resource_id") or args.get("id"))
            if resource_id is None:
                raise ValueError("缺少学习资源 id")

            cursor.execute(
                """
                SELECT id, user_id, course_name, topic, resource_type, title, content,
                       resource_json, created_at
                FROM learning_resources
                WHERE id = %s AND user_id = %s
                """,
                (resource_id, user["id"])
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("学习资源不存在")

            resource = _json_loads(row["resource_json"], {})
            if isinstance(resource, str):
                resource = _json_loads(resource, {})

            tool_results["resource_detail"] = {
                "id": row["id"],
                "user_id": row["user_id"],
                "course_name": row["course_name"],
                "topic": row["topic"],
                "resource_type": row["resource_type"],
                "title": row["title"],
                "content": row["content"],
                "resource": resource,
                "created_at": row["created_at"]
            }
            continue

        if tool == "generate_quiz":
            yield {"type": "status", "message": "正在生成练习题"}
            course_name, topic, _days = _course_topic_days(plan, tool)
            chunks = _get_course_chunks(cursor, user["id"], course_name)
            rag_context = search_similar_chunks(query=topic, chunks=chunks, top_k=5) if chunks else []
            quiz_set = generate_quiz_set(
                course_name=course_name,
                topic=topic,
                profile=active_profile,
                rag_context=rag_context
            )
            quiz_set["rag_references"] = _build_rag_references(rag_context)
            quiz_set = _save_quiz_set(cursor, user["id"], quiz_set)
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_GENERATE_QUIZ_SET",
                "quiz_set",
                quiz_set["id"],
                {
                    "source": "agent_chat",
                    "course_name": course_name,
                    "topic": topic,
                    "quiz_set_id": quiz_set["id"],
                    "title": quiz_set["title"],
                    "question_count": len(quiz_set["questions"]),
                    "rag_hit_count": len(rag_context),
                    "rag_chunk_ids": [item["id"] for item in rag_context]
                }
            )
            tool_results["quiz_set"] = quiz_set
            continue

        if tool == "list_quizzes":
            yield {"type": "status", "message": "正在查询题集"}
            page, size = _page_size(args)
            offset = (page - 1) * size
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM quiz_sets
                WHERE user_id = %s
                """,
                (user["id"],)
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                """
                SELECT id, title, course_name, topic, created_at
                FROM quiz_sets
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (user["id"], size, offset)
            )
            tool_results["quizzes"] = {
                "total": total,
                "list": cursor.fetchall(),
                "page": page,
                "size": size
            }
            continue

        if tool == "get_quiz":
            yield {"type": "status", "message": "正在读取题集详情"}
            quiz_set_id = _to_int(args.get("quiz_set_id") or args.get("id"))
            if quiz_set_id is None:
                raise ValueError("缺少题集 id")

            cursor.execute(
                """
                SELECT id, user_id, title, course_name, topic, quiz_json, created_at
                FROM quiz_sets
                WHERE id = %s AND user_id = %s
                """,
                (quiz_set_id, user["id"])
            )
            quiz_set = cursor.fetchone()
            if quiz_set is None:
                raise ValueError("题集不存在")

            quiz_json = _json_loads(quiz_set["quiz_json"], {})
            if isinstance(quiz_json, str):
                quiz_json = _json_loads(quiz_json, {})

            tool_results["quiz_detail"] = {
                "id": quiz_set["id"],
                "title": quiz_set["title"],
                "course_name": quiz_set["course_name"],
                "topic": quiz_set["topic"],
                "created_at": quiz_set["created_at"],
                "user_id": quiz_set["user_id"],
                "questions": _load_quiz_questions(cursor, quiz_set_id),
                "quiz_json": quiz_json
            }
            continue

        if tool == "generate_plan":
            yield {"type": "status", "message": "正在生成学习计划"}
            course_name, topic, days = _course_topic_days(plan, tool)
            learning_plan = generate_learning_plan(
                course_name=course_name,
                topic=topic,
                days=days,
                profile=active_profile
            )
            tool_results["learning_plan"] = learning_plan
            continue

        if tool == "import_plan_tasks":
            yield {"type": "status", "message": "正在导入学习计划任务"}
            tasks_preview = args.get("tasks_preview")
            if not tasks_preview and isinstance(tool_results.get("learning_plan"), dict):
                tasks_preview = tool_results["learning_plan"].get("tasks_preview")
            if not tasks_preview:
                latest_plan = _find_latest_tool_result(cursor, user["id"], "learning_plan")
                tasks_preview = latest_plan.get("tasks_preview") if latest_plan else None
            if not isinstance(tasks_preview, list):
                raise ValueError("没有找到可导入的学习计划任务")
            tool_results["plan_import"] = _create_tasks_from_preview(
                cursor,
                user["id"],
                tasks_preview,
                "agent_learning_plan"
            )
            continue

        if tool == "search_external_learning_resources":
            yield {"type": "status", "message": "正在联网搜索学习资源"}
            topic = _require_text(args.get("topic") or plan.get("topic"), "缺少知识点")
            course_name = _optional_text(args.get("course_name") or plan.get("course_name")) or ""
            learner_level = _optional_text(args.get("learner_level")) or "beginner"
            max_results = _to_int(args.get("max_results"), 5) or 5
            max_results = max(1, min(max_results, 20))

            try:
                external_resources = search_external_learning_resources(
                    course_name=course_name,
                    topic=topic,
                    learner_level=learner_level,
                    max_results=max_results
                )
            except Exception as e:
                external_resources = {
                    "course_name": course_name,
                    "topic": topic,
                    "learner_level": learner_level,
                    "resources": [],
                    "error": str(e)
                }

            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_SEARCH_EXTERNAL_RESOURCES",
                "external_resources",
                None,
                {
                    "course_name": course_name,
                    "topic": topic,
                    "learner_level": learner_level,
                    "max_results": max_results,
                    "result_count": len(external_resources.get("resources", [])),
                    "error": external_resources.get("error")
                }
            )
            tool_results["external_resources"] = external_resources
            continue

        if tool == "create_task":
            yield {"type": "status", "message": "正在创建任务"}
            title = _require_text(args.get("title"), "缺少任务标题")
            description = str(args.get("description") or "")
            status = args.get("status") or "todo"
            priority = args.get("priority") or "medium"

            if not is_valid_status(status):
                raise ValueError("任务状态不合法")

            if not is_valid_priority(priority):
                raise ValueError("任务优先级不合法")

            cursor.execute(
                """
                INSERT INTO tasks
                    (user_id, title, description, status, priority)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user["id"], title, description, status, priority)
            )
            task_id = cursor.lastrowid
            cursor.execute(
                """
                SELECT id, title, description, status, priority, created_at, updated_at
                FROM tasks
                WHERE id = %s AND user_id = %s
                """,
                (task_id, user["id"])
            )
            task = cursor.fetchone()
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_CREATE_TASK",
                "task",
                task_id,
                {
                    "title": title,
                    "status": status,
                    "priority": priority
                }
            )
            tool_results["task"] = task
            continue

        if tool == "list_tasks":
            yield {"type": "status", "message": "正在查询任务"}
            tool_results["tasks"] = _list_tasks(cursor, user["id"], args)
            continue

        if tool == "get_task":
            yield {"type": "status", "message": "正在读取任务详情"}
            task_id = _to_int(args.get("task_id") or args.get("id"))
            if task_id is None:
                raise ValueError("缺少任务 id")

            task, err = get_owned_task(cursor, task_id, user["id"])
            if err is not None:
                raise ValueError(err["message"])

            task.pop("user_id", None)
            tool_results["task_detail"] = task
            continue

        if tool == "update_task":
            yield {"type": "status", "message": "正在更新任务"}
            task_id = _to_int(args.get("task_id") or args.get("id"))
            if task_id is None:
                raise ValueError("缺少任务 id")

            task, err = get_owned_task(cursor, task_id, user["id"])
            if err is not None:
                raise ValueError(err["message"])

            updates = {
                "title": _optional_text(args.get("title")),
                "description": args.get("description") if args.get("description") is not None else None,
                "status": _optional_text(args.get("status")),
                "priority": _optional_text(args.get("priority")),
            }
            updates = {key: value for key, value in updates.items() if value is not None}

            if not updates:
                raise ValueError("更新参数不能全为空")

            if "status" in updates and not is_valid_status(updates["status"]):
                raise ValueError("任务状态不合法")

            if "priority" in updates and not is_valid_priority(updates["priority"]):
                raise ValueError("任务优先级不合法")

            update_columns = {
                "title": "title",
                "description": "description",
                "status": "status",
                "priority": "priority",
            }
            for field, value in updates.items():
                column = update_columns[field]
                cursor.execute(
                    f"UPDATE tasks SET {column} = %s WHERE id = %s AND user_id = %s",
                    (value, task_id, user["id"])
                )

            cursor.execute(
                """
                SELECT id, title, description, status, priority, created_at, updated_at
                FROM tasks
                WHERE id = %s AND user_id = %s
                """,
                (task_id, user["id"])
            )
            updated_task = cursor.fetchone()
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_UPDATE_TASK",
                "task",
                task_id,
                {
                    "updates": updates
                }
            )
            tool_results["task_update"] = updated_task
            continue

        if tool == "delete_task":
            yield {"type": "status", "message": "正在删除任务"}
            task_id = _to_int(args.get("task_id") or args.get("id"))
            if task_id is None:
                raise ValueError("缺少任务 id")

            task, err = get_owned_task(cursor, task_id, user["id"])
            if err is not None:
                raise ValueError(err["message"])

            cursor.execute(
                """
                DELETE FROM tasks
                WHERE id = %s AND user_id = %s
                """,
                (task_id, user["id"])
            )
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_DELETE_TASK",
                "task",
                task_id,
                {
                    "deleted_title": task.get("title")
                }
            )
            tool_results["task_delete"] = {
                "id": task_id,
                "deleted": True,
                "title": task.get("title")
            }
            continue

        if tool == "bulk_update_tasks_status":
            yield {"type": "status", "message": "正在批量更新任务状态"}
            from_status = _require_text(args.get("from_status"), "缺少源任务状态")
            to_status = _require_text(args.get("to_status"), "缺少目标任务状态")

            if not is_valid_status(from_status) or not is_valid_status(to_status):
                raise ValueError("任务状态不合法")

            cursor.execute(
                """
                UPDATE tasks
                SET status = %s
                WHERE user_id = %s AND status = %s
                """,
                (to_status, user["id"], from_status)
            )
            affected_rows = cursor.rowcount
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_BULK_UPDATE_TASK_STATUS",
                "task",
                None,
                {
                    "from_status": from_status,
                    "to_status": to_status,
                    "affected_rows": affected_rows
                }
            )
            tool_results["bulk_task_update"] = {
                "from_status": from_status,
                "to_status": to_status,
                "affected_rows": affected_rows
            }
            continue

        if tool == "bulk_delete_tasks_status":
            yield {"type": "status", "message": "正在批量删除任务"}
            status = _require_text(args.get("status"), "缺少任务状态")

            if not is_valid_status(status):
                raise ValueError("任务状态不合法")

            cursor.execute(
                """
                DELETE FROM tasks
                WHERE user_id = %s AND status = %s
                """,
                (user["id"], status)
            )
            affected_rows = cursor.rowcount
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_BULK_DELETE_TASK_STATUS",
                "task",
                None,
                {
                    "status": status,
                    "affected_rows": affected_rows
                }
            )
            tool_results["bulk_task_delete"] = {
                "status": status,
                "affected_rows": affected_rows
            }
            continue

        if tool == "submit_evaluation":
            yield {"type": "status", "message": "正在评估练习答案"}
            quiz_set_id = _to_int(args.get("quiz_set_id") or args.get("id"))
            if quiz_set_id is None:
                raise ValueError("缺少题集 id")

            answers = args.get("answers")
            if not isinstance(answers, list) or not answers:
                raise ValueError("缺少可评估的答案")

            cursor.execute(
                """
                SELECT id, title, course_name, topic, quiz_json, created_at
                FROM quiz_sets
                WHERE id = %s AND user_id = %s
                """,
                (quiz_set_id, user["id"])
            )
            quiz_set = cursor.fetchone()
            if quiz_set is None:
                raise ValueError("题集不存在或无访问权限")

            questions = _load_quiz_questions(cursor, quiz_set_id)
            if not questions:
                raise ValueError("该题集下没有可评估的题目")

            normalized_answers = []
            for answer in answers:
                question_id = _to_int(answer.get("question_id"))
                user_answer = _optional_text(answer.get("user_answer"))
                if question_id is None or not user_answer:
                    continue
                normalized_answers.append(
                    {
                        "question_id": question_id,
                        "user_answer": user_answer
                    }
                )

            if not normalized_answers:
                raise ValueError("没有找到有效的题目答案")

            evaluation = evaluate_quiz_answers(
                quiz_set_id=quiz_set["id"],
                quiz_title=quiz_set["title"],
                questions=questions,
                user_answers=normalized_answers,
                profile=active_profile
            )
            cursor.execute(
                """
                INSERT INTO learning_evaluations
                    (user_id, quiz_set_id, score, level, weak_points_json, suggestions_json, evaluation_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user["id"],
                    quiz_set_id,
                    evaluation["score"],
                    evaluation["level"],
                    _json_dumps(evaluation.get("weak_points", [])),
                    _json_dumps(evaluation.get("suggestions", [])),
                    _json_dumps(evaluation)
                )
            )
            evaluation_id = cursor.lastrowid
            evaluation["id"] = evaluation_id
            _insert_log(
                cursor,
                user["id"],
                "A3_AGENT_SUBMIT_LEARNING_EVALUATION",
                "learning_evaluation",
                evaluation_id,
                {
                    "quiz_set_id": quiz_set_id,
                    "score": evaluation["score"],
                    "level": evaluation["level"],
                    "weak_point_count": len(evaluation.get("weak_points", [])),
                    "suggestion_count": len(evaluation.get("suggestions", []))
                }
            )
            tool_results["evaluation"] = evaluation
            continue

        if tool == "list_evaluations":
            yield {"type": "status", "message": "正在查询学习评估记录"}
            page, size = _page_size(args)
            offset = (page - 1) * size
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM learning_evaluations
                WHERE user_id = %s
                """,
                (user["id"],)
            )
            total = cursor.fetchone()["total"]
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
                (user["id"], size, offset)
            )
            items = []
            for row in cursor.fetchall():
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
            tool_results["evaluations"] = {
                "items": items,
                "page": page,
                "size": size,
                "total": total
            }
            continue

        if tool == "get_evaluation":
            yield {"type": "status", "message": "正在读取评估详情"}
            evaluation_id = _to_int(args.get("evaluation_id") or args.get("id"))
            if evaluation_id is None:
                raise ValueError("缺少评估 id")

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
                (evaluation_id, user["id"])
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("学习效果评估记录不存在或无访问权限")

            evaluation_data = _json_loads(row["evaluation_json"], {})
            if not isinstance(evaluation_data, dict):
                raise ValueError("学习效果评估记录格式错误")

            evaluation_data["id"] = row["id"]
            evaluation_data["quiz_set_id"] = row["quiz_set_id"]
            evaluation_data["quiz_title"] = row["quiz_title"]
            evaluation_data["course_name"] = row["course_name"]
            evaluation_data["topic"] = row["topic"]
            evaluation_data["created_at"] = row["created_at"]
            tool_results["evaluation_detail"] = evaluation_data
            continue

        if tool == "parse_exam_schedule":
            yield {"type": "status", "message": "正在解析考试安排"}
            text = _require_text(args.get("text") or original_message, "缺少考试安排文本")
            tool_results["exam_schedule"] = parse_exam_schedule(text)
            continue

        if tool == "preview_review_plan":
            yield {"type": "status", "message": "正在生成复习计划"}
            exams = args.get("exams")
            if not exams and isinstance(tool_results.get("exam_schedule"), dict):
                exams = tool_results["exam_schedule"].get("exams")
            if not isinstance(exams, list) or not exams:
                raise ValueError("缺少考试安排")

            tool_results["review_plan"] = preview_review_plan(exams)
            continue

        if tool == "import_review_plan_tasks":
            yield {"type": "status", "message": "正在导入复习计划任务"}
            tasks_preview = args.get("tasks_preview")
            if not tasks_preview and isinstance(tool_results.get("review_plan"), dict):
                tasks_preview = tool_results["review_plan"].get("tasks_preview")
            if not tasks_preview:
                latest_plan = _find_latest_tool_result(cursor, user["id"], "review_plan")
                tasks_preview = latest_plan.get("tasks_preview") if latest_plan else None
            if not isinstance(tasks_preview, list):
                raise ValueError("没有找到可导入的复习计划任务")
            tool_results["review_import"] = _create_tasks_from_preview(
                cursor,
                user["id"],
                tasks_preview,
                "agent_review_plan"
            )
            continue

        if tool == "list_operation_logs":
            yield {"type": "status", "message": "正在查询操作日志"}
            page, size = _page_size(args)
            offset = (page - 1) * size
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM operation_logs
                WHERE user_id = %s
                """,
                (user["id"],)
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                """
                SELECT id, action, target_type, target_id, detail, created_at
                FROM operation_logs
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (user["id"], size, offset)
            )
            tool_results["operation_logs"] = {
                "list": cursor.fetchall(),
                "total": total,
                "page": page,
                "size": size
            }
            continue

    return tool_results


def _run_agent_chat_events(message: str, user: dict):
    conn = None
    cursor = None

    try:
        conn = get_conn()
        cursor = conn.cursor()

        yield {"type": "status", "message": "正在记录你的问题"}
        user_message_id = _insert_chat_message(
            cursor,
            user["id"],
            "user",
            message,
            None
        )

        profile = _load_profile(cursor, user["id"])
        history_rows = _fetch_chat_history(cursor, user["id"], user_message_id)

        yield {"type": "status", "message": "正在理解学习需求"}
        plan = analyze_user_learning_request(
            message=message,
            profile=profile,
            history=history_rows
        )

        tool_results = {}
        tools = plan.get("tools") or []

        if plan.get("status") == "need_more_info" or not tools:
            reply = plan.get("reply", "请补充学习需求")
            _insert_chat_message(
                cursor,
                user["id"],
                "assistant",
                reply,
                _compact_tool_calls_for_storage(plan, tool_results)
            )
            conn.commit()
            return {
                "plan": plan,
                "tool_results": tool_results
            }

        tool_runner = _execute_agent_tools(
            plan=plan,
            cursor=cursor,
            user=user,
            profile=profile,
            original_message=message
        )

        while True:
            try:
                event = next(tool_runner)
                yield event
            except StopIteration as stop:
                tool_results = stop.value or {}
                break

        _insert_log(
            cursor,
            user["id"],
            "A3_AGENT_CHAT_DISPATCH",
            "agent_chat",
            None,
            {
                **_build_agent_summary(plan, tool_results),
                "days": plan.get("days"),
                "tool_result_keys": list(tool_results.keys())
            }
        )

        reply = plan.get("reply", "已完成学习助手工具调度")
        _insert_chat_message(
            cursor,
            user["id"],
            "assistant",
            reply,
            _compact_tool_calls_for_storage(plan, tool_results)
        )
        conn.commit()

        return {
            "plan": plan,
            "tool_results": tool_results
        }

    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _consume_agent_chat(message: str, user: dict) -> dict:
    runner = _run_agent_chat_events(message, user)

    while True:
        try:
            next(runner)
        except StopIteration as stop:
            return stop.value


@router.post("/chat")
def agent_chat(
        request: AgentChatRequest,
        user=Depends(get_current_user)
):
    """
    AI 学习助手总入口：解析用户自然语言需求，并调度后端工具。
    """
    try:
        result = _consume_agent_chat(request.message, user)
        return success(
            data=result,
            message="AI助手已完成处理"
        )
    except ValueError as e:
        return error(
            message=str(e),
            code=400
        )
    except Exception as e:
        return error(
            message=f"AI助手处理失败：{str(e)}",
            code=500
        )


@router.post("/chat/stream")
def agent_chat_stream(
        request: AgentChatRequest,
        user=Depends(get_current_user)
):
    def event_stream():
        runner = _run_agent_chat_events(request.message, user)

        try:
            while True:
                try:
                    event = next(runner)
                    event_type = event.get("type", "status")
                    payload = {
                        key: value
                        for key, value in event.items()
                        if key != "type"
                    }
                    yield _stream_event(event_type, **payload)
                except StopIteration as stop:
                    result = stop.value or {
                        "plan": {},
                        "tool_results": {}
                    }
                    reply = result.get("plan", {}).get("reply", "处理完成")
                    yield from _stream_reply(reply)
                    yield _stream_event("result", data=result)
                    yield _stream_event("done")
                    return

        except ValueError as e:
            yield _stream_event("error", message=str(e), code=400)
        except Exception as e:
            yield _stream_event("error", message=f"AI助手处理失败：{str(e)}", code=500)

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
