import pytest

from app.core.errors import AppError
from app.modules.agent.schemas import CourseAgentMemoryPatch, CourseAgentMemoryUpsert
from app.modules.agent.service import (
    delete_chat_memory,
    delete_course_agent_memory,
    get_course_agent_workspace,
    list_course_agent_memories,
    save_course_agent_memory,
    set_course_agent_memory_type_enabled,
    update_chat_memory,
    update_course_agent_memory,
    write_chat_memory,
)
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course


def test_course_memory_crud_source_visibility_and_context_toggle(two_users):
    owner, stranger = two_users
    course = create_user_course(
        owner["id"],
        CourseCreate(name="记忆透明化课程", goal="验证用户可控的长期记忆"),
    )
    stranger_course = create_user_course(
        stranger["id"],
        CourseCreate(name="其他用户课程", goal="验证隔离"),
    )

    created = save_course_agent_memory(
        owner["id"],
        course["id"],
        CourseAgentMemoryUpsert(
            memory_key="preferred_style",
            memory_type="course_preference",
            content={"text": "先给结论，再解释步骤"},
        ),
    )

    assert created["source_type"] == "manual"
    assert created["enabled"] is True
    assert "embedding_json" not in created
    listed = list_course_agent_memories(owner["id"], course["id"])
    assert listed["total"] == 1
    assert listed["items"][0]["content"]["text"] == "先给结论，再解释步骤"
    assert listed["items"][0]["updated_at"] is not None

    disabled = update_course_agent_memory(
        owner["id"],
        course["id"],
        created["id"],
        CourseAgentMemoryPatch(enabled=False),
    )
    assert disabled["enabled"] is False
    assert list_course_agent_memories(owner["id"], course["id"])["total"] == 1
    assert get_course_agent_workspace(owner["id"], course["id"])["memories"] == []

    type_result = set_course_agent_memory_type_enabled(
        owner["id"],
        course["id"],
        "course_preference",
        True,
    )
    assert type_result["affected"] == 1
    assert get_course_agent_workspace(owner["id"], course["id"])["memories"][0]["id"] == created["id"]

    edited = update_course_agent_memory(
        owner["id"],
        course["id"],
        created["id"],
        CourseAgentMemoryPatch(content={"text": "使用短段落"}, memory_type="course_preference"),
    )
    assert edited["source_type"] == "manual_edit"
    assert edited["source_message_id"] is None
    assert edited["content"] == {"text": "使用短段落"}
    assert edited["memory_type"] == "course_preference"

    with pytest.raises(AppError) as invalid_type:
        update_course_agent_memory(
            owner["id"],
            course["id"],
            created["id"],
            CourseAgentMemoryPatch(memory_type="learning_preference"),
        )
    assert invalid_type.value.error_code == "MEMORY_TYPE_INVALID"

    with pytest.raises(AppError) as cross_course:
        update_course_agent_memory(
            stranger["id"],
            stranger_course["id"],
            created["id"],
            CourseAgentMemoryPatch(enabled=False),
        )
    assert cross_course.value.error_code == "COURSE_MEMORY_NOT_FOUND"

    with pytest.raises(AppError) as cross_user:
        list_course_agent_memories(stranger["id"], course["id"])
    assert cross_user.value.error_code == "COURSE_NOT_FOUND"

    delete_course_agent_memory(owner["id"], course["id"], created["id"])
    assert list_course_agent_memories(owner["id"], course["id"])["items"] == []
    assert get_course_agent_workspace(owner["id"], course["id"])["memories"] == []


def test_memory_patch_rejects_empty_updates():
    with pytest.raises(ValueError):
        CourseAgentMemoryPatch()
    with pytest.raises(ValueError):
        CourseAgentMemoryPatch(content=None)


def test_chat_memory_helpers_write_update_and_delete(two_users):
    owner, _ = two_users
    course = create_user_course(
        owner["id"],
        CourseCreate(name="对话记忆工具课程", goal="验证 chat 写入路径"),
    )

    written = write_chat_memory(
        owner["id"],
        course["id"],
        text="我更喜欢先看结论",
        memory_type="course_preference",
        memory_key="style_pref",
    )
    assert written["source_type"] == "chat"
    assert written["content"]["text"] == "我更喜欢先看结论"
    assert written["memory_key"] == "style_pref"

    updated = update_chat_memory(
        owner["id"],
        course["id"],
        written["id"],
        text="使用短段落和列表",
        enabled=True,
    )
    assert updated["source_type"] == "chat"
    assert updated["content"]["text"] == "使用短段落和列表"

    deleted = delete_chat_memory(owner["id"], course["id"], written["id"])
    assert deleted == {"memory_id": written["id"], "deleted": True}
    assert list_course_agent_memories(owner["id"], course["id"])["items"] == []
