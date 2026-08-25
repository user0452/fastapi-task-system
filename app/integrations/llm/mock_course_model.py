"""Deterministic offline model for the Adaptive Tutor interaction layer."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool


def _latest_user_text(messages: list[BaseMessage]) -> str:
    return next(
        (
            str(message.content)
            for message in reversed(messages)
            if isinstance(message, HumanMessage)
        ),
        "",
    )


def _tutor_reply(text: str) -> str:
    lowered = text.casefold()
    if "why_this_action" in lowered or "为什么" in text:
        return "这一步针对当前证据最薄弱的 Learning Objective；完成后会写入新的 Evidence，再重新计算下一动作。"
    if "example" in lowered or "例子" in text:
        return "举个场景：如果接收端缓存快满，应该先看 rwnd；如果网络路径出现拥塞信号，则应该看 cwnd。两者都可能限制发送窗口，但原因不同。"
    if "hint" in lowered or "提示" in text:
        return "先问自己：这个变化来自接收端处理能力，还是来自网络路径承载能力？前者对应 rwnd，后者对应 cwnd。"
    if "reframe" in lowered or "换" in text:
        return "换个角度：rwnd 是接收端对发送方说‘我还能接多少’，cwnd 是发送方根据网络状态判断‘现在适合发多少’。"
    if "break_down" in lowered or "拆" in text:
        return "可以拆成三步：先识别控制对象，再找到窗口或 ACK 证据，最后说明这个证据支持的结论。"
    return "先用课程资料中的定义定位控制对象，再说明场景证据和结论。这次对话只用于解释，不会直接改变 Student Model。"


class MockCourseChatModel(BaseChatModel):
    """A no-tool model that makes local Tutor tests deterministic."""

    @property
    def _llm_type(self) -> str:
        return "a3-offline-adaptive-tutor"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        # The Tutor runtime intentionally exposes no business tools. Keep the
        # method for LangChain's ChatModel interface, but never emit tool calls.
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        text = _latest_user_text(messages)
        content = _tutor_reply(text) if "intent=" in text or "学生请求" in text else f"已收到你的问题：{text}"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


__all__ = ["MockCourseChatModel"]
