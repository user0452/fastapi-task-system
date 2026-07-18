from langchain_core.messages import HumanMessage, ToolMessage

from app.integrations.llm.mock_course_model import MockCourseChatModel


def test_offline_model_emits_native_tool_calls_and_finishes_from_tool_results():
    model = MockCourseChatModel()

    search = model.invoke([HumanMessage(content="根据课程资料讲解边界值分析")])
    practice = model.invoke([HumanMessage(content="给我出 5 道题")])
    destructive = model.invoke([HumanMessage(content="删除任务 42")])
    write_memory = model.invoke([HumanMessage(content="记住我更喜欢先看结论")])
    write_memory_alt = model.invoke(
        [HumanMessage(content="请写入一条长期记忆：每周二复盘")]
    )
    list_memory = model.invoke([HumanMessage(content="查看记忆")])
    update_memory = model.invoke([HumanMessage(content="修改记忆 7 为 使用短段落")])
    delete_memory = model.invoke([HumanMessage(content="删除记忆 7")])
    final = model.invoke(
        [
            HumanMessage(content="根据课程资料讲解边界值分析"),
            ToolMessage(
                content='{"total": 3, "anchors": []}',
                name="search_course_knowledge",
                tool_call_id="mock-search",
            ),
        ]
    )
    deleted = model.invoke(
        [
            HumanMessage(content="删除任务 42"),
            ToolMessage(
                content='{"task_id": 42, "deleted": true}',
                name="delete_task",
                tool_call_id="mock-delete",
            ),
        ]
    )
    memory_written = model.invoke(
        [
            HumanMessage(content="记住我更喜欢先看结论"),
            ToolMessage(
                content='{"memory": {"id": 8, "content": {"text": "我更喜欢先看结论"}}}',
                name="write_course_memory",
                tool_call_id="mock-write-memory",
            ),
        ]
    )

    assert search.tool_calls[0]["name"] == "search_course_knowledge"
    assert practice.tool_calls[0]["args"]["question_count"] == 5
    assert destructive.tool_calls[0] == {
        "name": "delete_task",
        "args": {"task_id": 42},
        "id": destructive.tool_calls[0]["id"],
        "type": "tool_call",
    }
    assert write_memory.tool_calls[0]["name"] == "write_course_memory"
    assert write_memory.tool_calls[0]["args"]["text"] == "我更喜欢先看结论"
    assert write_memory.tool_calls[0]["args"]["memory_type"] == "course_preference"
    assert write_memory_alt.tool_calls[0]["name"] == "write_course_memory"
    assert write_memory_alt.tool_calls[0]["args"]["text"] == "每周二复盘"
    assert list_memory.tool_calls[0]["name"] == "list_course_memories"
    assert update_memory.tool_calls[0] == {
        "name": "update_course_memory",
        "args": {"memory_id": 7, "text": "使用短段落"},
        "id": update_memory.tool_calls[0]["id"],
        "type": "tool_call",
    }
    assert delete_memory.tool_calls[0]["name"] == "delete_course_memory"
    assert delete_memory.tool_calls[0]["args"]["memory_id"] == 7
    assert "3 个相关片段" in str(final.content)
    assert deleted.content == "任务已删除。"
    assert "已写入长期记忆" in str(memory_written.content)
