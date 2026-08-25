from langchain_core.messages import HumanMessage

from app.integrations.llm.mock_course_model import MockCourseChatModel


def test_offline_model_is_a_no_tool_tutor_interaction_layer():
    model = MockCourseChatModel()

    response = model.invoke(
        [
            HumanMessage(
                content='intent=example\n学生请求：请给我一个 cwnd 和 rwnd 的例子。'
            )
        ]
    )

    assert response.tool_calls == []
    assert "rwnd" in str(response.content)
    assert "cwnd" in str(response.content)
