from langchain_core.messages import HumanMessage, ToolMessage

from app.integrations.llm.mock_course_model import MockCourseChatModel


def test_offline_model_emits_native_tool_calls_and_finishes_from_tool_results():
    model = MockCourseChatModel()

    search = model.invoke([HumanMessage(content="根据课程资料讲解边界值分析")])
    practice = model.invoke([HumanMessage(content="给我出 5 道题")])
    destructive = model.invoke([HumanMessage(content="删除任务 42")])
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

    assert search.tool_calls[0]["name"] == "search_course_knowledge"
    assert practice.tool_calls[0]["args"]["question_count"] == 5
    assert destructive.tool_calls[0] == {
        "name": "delete_task",
        "args": {"task_id": 42},
        "id": destructive.tool_calls[0]["id"],
        "type": "tool_call",
    }
    assert "3 个相关片段" in str(final.content)
    assert deleted.content == "任务已删除。"
