from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.embedding import hybrid_search as hybrid_module
from app.modules.agent.schemas import AgentChatRequest, CourseAgentMemoryUpsert
from app.modules.agent.service import (
    _classify_intent,
    get_course_agent_workspace,
    run_agent_chat,
    save_course_agent_memory,
)
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course
from app.modules.materials.schemas import TextMaterialCreate
from app.modules.materials.service import (
    create_text_material,
    get_course_evidence_context,
    list_course_material_outline,
    process_material,
    read_course_material_section,
    search_course_materials,
)


def _vectors(texts: list[str]):
    rows = []
    for text in texts:
        seed = sum(text.encode("utf-8")) or 1
        row = np.array([(seed % 17) + 1, (seed % 31) + 2, (seed % 43) + 3, 1], dtype="float32")
        rows.append(row / np.linalg.norm(row))
    return np.vstack(rows)


def _points(_course_name, title, chunks):
    return [
        {
            "name": f"{title}知识点{index + 1}",
            "description": chunk["chunk_text"][:120],
            "chunk_indices": [chunk["chunk_index"]],
        }
        for index, chunk in enumerate(chunks[:3])
    ]


def _reply(message, course, profile, mastery, recent_messages, citations, current_time):
    del message, profile, mastery, recent_messages, current_time
    return f"《{course['name']}》课程回答，引用 {len(citations)} 条。"


def test_one_course_has_one_persistent_agent_and_primary_session(two_users):
    user, _ = two_users
    courses = [
        create_user_course(user["id"], CourseCreate(name=f"独立课程 {index}"))
        for index in range(3)
    ]

    workspaces = [get_course_agent_workspace(user["id"], course["id"]) for course in courses]
    restored = [get_course_agent_workspace(user["id"], course["id"]) for course in courses]

    assert len({item["agent"]["id"] for item in workspaces}) == 3
    assert len({item["session"]["id"] for item in workspaces}) == 3
    assert [item["agent"]["id"] for item in restored] == [item["agent"]["id"] for item in workspaces]
    assert [item["session"]["id"] for item in restored] == [item["session"]["id"] for item in workspaces]
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT course_id, COUNT(*) AS total FROM course_agents WHERE user_id = %s GROUP BY course_id",
            (user["id"],),
        )
        assert all(row["total"] == 1 for row in cursor.fetchall())


def test_one_hundred_course_retrievals_never_cross_course(two_users, monkeypatch):
    user, _ = two_users
    monkeypatch.setattr(hybrid_module, "embed_texts", _vectors)
    material_by_course = {}
    courses = []
    for index in range(3):
        course = create_user_course(user["id"], CourseCreate(name=f"隔离检索课程 {index}"))
        content = "。".join(
            [
                f"课程{index}专属概念{part}包含唯一标识C{index}P{part}和应用说明"
                for part in range(1, 5)
            ]
        )
        material = create_text_material(
            user["id"],
            course["id"],
            TextMaterialCreate(title=f"课程{index}讲义", content=content),
        )
        process_material(
            user["id"],
            material["id"],
            embedding_provider=_vectors,
            knowledge_provider=_points,
        )
        courses.append(course)
        material_by_course[course["id"]] = material["id"]

    for index in range(100):
        course = courses[index % len(courses)]
        result = search_course_materials(user["id"], course["id"], f"课程{index % 3}专属概念", 5)
        assert result["citations"]
        assert {item["material_id"] for item in result["citations"]} == {
            material_by_course[course["id"]]
        }


def test_material_reindex_reuses_unchanged_chunk_and_point_vectors(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="增量索引课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(
            title="增量讲义",
            content="第一部分解释基础概念。第二部分给出典型案例。第三部分总结常见错误。" * 20,
        ),
    )
    calls = []

    def counted_vectors(texts):
        calls.append(len(texts))
        return _vectors(texts)

    first = process_material(
        user["id"],
        material["id"],
        embedding_provider=counted_vectors,
        knowledge_provider=_points,
    )
    first_calls = list(calls)
    calls.clear()
    second = process_material(
        user["id"],
        material["id"],
        embedding_provider=counted_vectors,
        knowledge_provider=_points,
    )

    assert first_calls
    assert calls == []
    assert second["reused_chunk_embeddings"] == first["chunk_count"]
    assert second["reused_knowledge_point_embeddings"] == first["knowledge_point_count"]


def test_material_reindex_embeds_only_changed_chunks_and_points(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="局部增量索引课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="局部变化讲义", content="A" * 2000 + "B" * 1600),
    )
    calls = []

    def counted_vectors(texts):
        calls.append(list(texts))
        return _vectors(texts)

    first = process_material(
        user["id"],
        material["id"],
        embedding_provider=counted_vectors,
        knowledge_provider=_points,
    )
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE course_materials SET content = %s WHERE id = %s AND user_id = %s",
            ("A" * 2000 + "C" * 1600, material["id"], user["id"]),
        )
    calls.clear()
    changed = process_material(
        user["id"],
        material["id"],
        embedding_provider=counted_vectors,
        knowledge_provider=_points,
    )

    assert calls
    assert 0 < changed["reused_chunk_embeddings"] < first["chunk_count"]
    assert 0 < changed["reused_knowledge_point_embeddings"] < first["knowledge_point_count"]
    assert changed["chunk_count"] == first["chunk_count"]


def test_agentic_rag_expands_neighbors_and_reads_sections(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="Agentic RAG 课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(
            title="结构化长讲义",
            content=(
                "# 基础概念\n\n"
                + "基础定义、适用条件与限制。" * 140
                + "\n\n# 典型案例\n\n"
                + "案例过程、判断依据与最终结论。" * 140
            ),
        ),
    )
    process_material(
        user["id"],
        material["id"],
        embedding_provider=_vectors,
        knowledge_provider=_points,
    )
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, chunk_index FROM course_material_chunks WHERE material_id = %s ORDER BY chunk_index",
            (material["id"],),
        )
        stored = list(cursor.fetchall())

    assert len(stored) >= 4
    anchor_id = stored[1]["id"]
    evidence = get_course_evidence_context(
        user["id"], course["id"], [anchor_id], neighbor_window=1, max_tokens=3_000
    )
    assert anchor_id in evidence["anchor_chunk_ids"]
    assert len(evidence["included_chunk_ids"]) >= 2
    assert evidence["used_tokens"] <= 3_000
    assert f"[chunk_id={anchor_id}]" in "\n".join(
        block["evidence_text"] for block in evidence["evidence_blocks"]
    )

    outline = list_course_material_outline(user["id"], course["id"], material["id"])
    headings = [section["heading_path"] for section in outline["materials"][0]["sections"]]
    assert "基础概念" in headings
    assert "典型案例" in headings

    section = read_course_material_section(
        user["id"], course["id"], material["id"], "典型案例", max_tokens=4_000
    )
    assert section["matched_headings"] == ["典型案例"]
    assert section["evidence_blocks"]
    assert all(block["heading_path"] == "典型案例" for block in section["evidence_blocks"])


def test_agent_external_turn_persists_run_and_tool_calls(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="Agent 工具审计课程"))

    def search_provider(_user_id, _course_id, _query, _top_k):
        return {
            "citations": [
                {
                    "chunk_id": 1,
                    "material_id": 2,
                    "material_title": "课程讲义",
                    "filename": None,
                    "page_number": 1,
                    "chunk_index": 0,
                    "score": 0.92,
                    "snippet": "课程内部资料片段",
                }
            ]
        }

    def external_provider(_user_id, course_id, _request):
        return {
            "course_id": course_id,
            "resources": [
                {
                    "id": index,
                    "provider": "bilibili",
                    "resource_type": "video",
                    "canonical_url": f"https://bilibili.com/video/BV1TEST{index}",
                    "title": f"外部视频 {index}",
                    "interaction": {},
                }
                for index in range(1, 5)
            ],
        }

    result = run_agent_chat(
        user["id"],
        AgentChatRequest(message="帮我找网上的视频讲解", course_id=course["id"]),
        reply_provider=_reply,
        search_provider=search_provider,
        external_search_provider=external_provider,
    )

    assert result["intent"] == "search_external_resources"
    assert len(result["resources"]) == 4
    assert result["run_id"]
    with get_cursor() as cursor:
        cursor.execute("SELECT status, course_id FROM agent_runs WHERE id = %s", (result["run_id"],))
        run = cursor.fetchone()
        assert run == {"status": "completed", "course_id": course["id"]}
        cursor.execute(
            "SELECT tool_name, status FROM agent_tool_calls WHERE run_id = %s ORDER BY id",
            (result["run_id"],),
        )
        calls = cursor.fetchall()
    assert [item["tool_name"] for item in calls] == [
        "search_course_knowledge",
        "search_external_videos",
    ]
    assert all(item["status"] == "completed" for item in calls)


def test_ten_concurrent_course_turns_keep_every_message_and_run(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="并发课程助手"))

    def ask(index: int):
        return run_agent_chat(
            user["id"],
            AgentChatRequest(message=f"并发问题 {index}", course_id=course["id"]),
            reply_provider=_reply,
            search_provider=lambda *_args: {"citations": []},
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(ask, range(10)))

    assert len({item["run_id"] for item in results}) == 10
    assert all(item["message"]["id"] for item in results)
    session_id = results[0]["session"]["id"]
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT role, COUNT(*) AS total
            FROM agent_chat_messages
            WHERE user_id = %s AND session_id = %s
            GROUP BY role
            """,
            (user["id"], session_id),
        )
        message_counts = {row["role"]: row["total"] for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM agent_runs
            WHERE user_id = %s AND course_id = %s
            GROUP BY status
            """,
            (user["id"], course["id"]),
        )
        run_counts = {row["status"]: row["total"] for row in cursor.fetchall()}

    assert message_counts == {"assistant": 10, "user": 10}
    assert run_counts == {"completed": 10}


def test_course_agent_rejects_cross_owner_and_cross_course_session(two_users):
    user, other_user = two_users
    course_a = create_user_course(user["id"], CourseCreate(name="权限课程 A"))
    course_b = create_user_course(user["id"], CourseCreate(name="权限课程 B"))
    workspace = get_course_agent_workspace(user["id"], course_a["id"])

    with pytest.raises(AppError) as ownership_error:
        get_course_agent_workspace(other_user["id"], course_a["id"])
    assert ownership_error.value.status_code == 404
    assert ownership_error.value.error_code == "COURSE_NOT_FOUND"

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM agent_chat_messages WHERE session_id = %s",
            (workspace["session"]["id"],),
        )
        before = cursor.fetchone()["total"]

    with pytest.raises(AppError) as mismatch_error:
        run_agent_chat(
            user["id"],
            AgentChatRequest(
                message="不能写入另一门课程",
                session_id=workspace["session"]["id"],
                course_id=course_b["id"],
            ),
        )
    assert mismatch_error.value.status_code == 409
    assert mismatch_error.value.error_code == "SESSION_COURSE_MISMATCH"

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM agent_chat_messages WHERE session_id = %s",
            (workspace["session"]["id"],),
        )
        assert cursor.fetchone()["total"] == before
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM operation_logs
            WHERE user_id = %s AND action = 'COURSE_AGENT_WORKSPACE_VIEWED'
              AND target_id = %s
            """,
            (user["id"], workspace["agent"]["id"]),
        )
        assert cursor.fetchone()["total"] >= 1


def test_three_courses_isolate_messages_memories_and_mastery(two_users):
    user, _ = two_users
    courses = [
        create_user_course(user["id"], CourseCreate(name=f"长期课程 {index}"))
        for index in range(3)
    ]
    markers = [f"course-marker-{index}" for index in range(3)]
    mastery_values = [24.0, 58.0, 91.0]

    for course, marker, mastery in zip(courses, markers, mastery_values, strict=True):
        save_course_agent_memory(
            user["id"],
            course["id"],
            CourseAgentMemoryUpsert(
                memory_key="learning.preference",
                content={"marker": marker},
            ),
        )
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO knowledge_points
                    (user_id, course_id, name, description, source_chunk_ids, sort_order)
                VALUES (%s, %s, %s, %s, '[]', 0)
                """,
                (user["id"], course["id"], f"{marker}-point", marker),
            )
            point_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO mastery_records
                    (user_id, course_id, knowledge_point_id, mastery)
                VALUES (%s, %s, %s, %s)
                """,
                (user["id"], course["id"], point_id, mastery),
            )
        run_agent_chat(
            user["id"],
            AgentChatRequest(message=marker, course_id=course["id"]),
            reply_provider=_reply,
            search_provider=lambda *_args: {"citations": []},
        )

    for index, course in enumerate(courses):
        workspace = get_course_agent_workspace(user["id"], course["id"])
        contents = [message["content"] for message in workspace["messages"]]
        assert markers[index] in contents
        assert all(marker not in contents for marker in markers if marker != markers[index])
        assert len(workspace["memories"]) == 1
        assert workspace["memories"][0]["memory_key"] == "learning.preference"
        assert workspace["memories"][0]["content"] == {"marker": markers[index]}
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT point.name, mastery.mastery
                FROM mastery_records mastery
                JOIN knowledge_points point ON point.id = mastery.knowledge_point_id
                WHERE mastery.user_id = %s AND mastery.course_id = %s
                """,
                (user["id"], course["id"]),
            )
            rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == f"{markers[index]}-point"
        assert float(rows[0]["mastery"]) == mastery_values[index]


def test_explicit_practice_request_wins_over_video_words():
    assert _classify_intent("我已经看完视频，请围绕这个知识点给我出 3 道题") == (
        "generate_practice",
        "generate",
    )
