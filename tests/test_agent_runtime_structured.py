from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.integrations.llm import agent_runtime


class _ResultSchema(BaseModel):
    objective: str
    confidence: float


class _ThinkingCompatibleModel:
    def __init__(self):
        self.model_copy_update = None

    def model_copy(self, *, update):
        self.model_copy_update = update
        return self


class _ToolChoiceRejectedAgent:
    @staticmethod
    def invoke(_input):
        raise RuntimeError("Thinking mode does not support this tool_choice")


def test_structured_runtime_retries_without_thinking_when_tool_choice_is_rejected(monkeypatch):
    model = _ThinkingCompatibleModel()
    agents = iter(
        [
            _ToolChoiceRejectedAgent(),
            type("StructuredAgent", (), {"invoke": staticmethod(lambda _input: {"structured_response": _ResultSchema(objective="能够判断当前状态", confidence=0.8)})})(),
        ]
    )
    monkeypatch.setattr(agent_runtime, "create_agent", lambda *_args, **_kwargs: next(agents))

    result = agent_runtime.invoke_agent_structured(
        [
            SystemMessage(content="提取课程目标"),
            HumanMessage(content="TCP 拥塞控制资料"),
        ],
        _ResultSchema,
        model=model,
    )

    assert result == _ResultSchema(objective="能够判断当前状态", confidence=0.8)
    assert model.model_copy_update == {"extra_body": {"thinking": {"type": "disabled"}}}


def test_structured_runtime_does_not_hide_other_provider_failures(monkeypatch):
    class FailingAgent:
        @staticmethod
        def invoke(_input):
            raise RuntimeError("authentication failed")

    monkeypatch.setattr(agent_runtime, "create_agent", lambda *_args, **_kwargs: FailingAgent())

    try:
        agent_runtime.invoke_agent_structured(
            [HumanMessage(content="测试")],
            _ResultSchema,
            model=_ThinkingCompatibleModel(),
        )
    except RuntimeError as exc:
        assert str(exc) == "authentication failed"
    else:
        raise AssertionError("普通模型错误不应触发 JSON 兼容兜底")
