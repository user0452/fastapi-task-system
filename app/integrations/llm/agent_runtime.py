"""Single create-agent runtime for text, structured output, streaming and tools."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool

from app.core.metrics import inc_counter, observe
from app.integrations.llm.model_provider import get_llm

RiskLevel = str


def _estimated_tokens(value: Any) -> int:
    return max(1, (len(str(value)) + 3) // 4)


def _input_tokens(messages: Sequence[BaseMessage]) -> int:
    return sum(_estimated_tokens(message.content) for message in messages)


def _split_messages(messages: Sequence[BaseMessage]) -> tuple[str | None, list[BaseMessage]]:
    system_messages = [message for message in messages if isinstance(message, SystemMessage)]
    prompt = "\n\n".join(str(message.content) for message in system_messages) or None
    conversation = [message for message in messages if not isinstance(message, SystemMessage)]
    return prompt, conversation


@dataclass(frozen=True)
class ConfirmationRequest:
    """A risky tool call intercepted before any side effect occurs."""

    tool_name: str
    arguments: dict[str, Any]
    risk_level: RiskLevel
    tool_call_id: str


class RiskConfirmationMiddleware(AgentMiddleware):
    """Intercept configured risky tools and record their confirmation payload."""

    def __init__(self, risk_tools: Mapping[str, RiskLevel] | None = None):
        super().__init__()
        self.risk_tools = dict(risk_tools or {})
        self.confirmations: list[ConfirmationRequest] = []

    def intercept(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None,
        tool_call_id: str = "application-request",
    ) -> ConfirmationRequest | None:
        risk_level = self.risk_tools.get(tool_name)
        if not risk_level:
            return None
        confirmation = ConfirmationRequest(
            tool_name=tool_name,
            arguments=dict(arguments or {}),
            risk_level=risk_level,
            tool_call_id=tool_call_id,
        )
        self.confirmations.append(confirmation)
        return confirmation

    def wrap_tool_call(self, request, handler):
        tool_call = request.tool_call
        tool_name = str(tool_call["name"])
        confirmation = self.intercept(
            tool_name,
            tool_call.get("args") or {},
            str(tool_call["id"]),
        )
        if confirmation is not None:
            inc_counter("a3_agent_tool_calls_total", tool=tool_name, status="confirmation_required")
            return ToolMessage(
                tool_call_id=confirmation.tool_call_id,
                content=json.dumps(
                    {
                        "status": "confirmation_required",
                        "tool": confirmation.tool_name,
                        "risk_level": confirmation.risk_level,
                        "arguments": confirmation.arguments,
                    },
                    ensure_ascii=False,
                ),
            )

        started = perf_counter()
        try:
            result = handler(request)
        except Exception:
            inc_counter("a3_agent_tool_calls_total", tool=tool_name, status="failed")
            raise
        else:
            inc_counter("a3_agent_tool_calls_total", tool=tool_name, status="completed")
            return result
        finally:
            observe("a3_agent_tool_duration_seconds", perf_counter() - started, tool=tool_name)


@dataclass
class AgentInvocation:
    message: AIMessage
    confirmations: list[ConfirmationRequest] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)


def invoke_agent_messages(
    messages: Sequence[BaseMessage],
    *,
    tools: Sequence[BaseTool | Callable[..., Any]] | None = None,
    risk_tools: Mapping[str, RiskLevel] | None = None,
    model=None,
) -> AgentInvocation:
    prompt, conversation = _split_messages(messages)
    middleware = RiskConfirmationMiddleware(risk_tools)
    agent = create_agent(
        model or get_llm(),
        tools=list(tools or ()),
        system_prompt=prompt,
        middleware=[middleware],
    )
    started = perf_counter()
    inc_counter("a3_llm_tokens_total", _input_tokens(messages), direction="input", mode="messages")
    try:
        agent_input: Any = {"messages": conversation}
        state = agent.invoke(agent_input)
        message = next(
            (
                item
                for item in reversed(state.get("messages", []))
                if isinstance(item, AIMessage) and item.content
            ),
            None,
        )
        if message is None:
            raise RuntimeError("create_agent 未返回可用的 AI 回复")
        inc_counter(
            "a3_llm_tokens_total",
            _estimated_tokens(message.content),
            direction="output",
            mode="messages",
        )
        inc_counter("a3_llm_requests_total", mode="messages", status="completed")
        return AgentInvocation(message=message, confirmations=middleware.confirmations, state=state)
    except Exception:
        inc_counter("a3_llm_requests_total", mode="messages", status="failed")
        raise
    finally:
        observe("a3_llm_request_duration_seconds", perf_counter() - started, mode="messages")


def stream_agent_content(
    messages: Sequence[BaseMessage],
    *,
    tools: Sequence[BaseTool | Callable[..., Any]] | None = None,
    risk_tools: Mapping[str, RiskLevel] | None = None,
    model=None,
) -> Iterable[str]:
    prompt, conversation = _split_messages(messages)
    middleware = RiskConfirmationMiddleware(risk_tools)
    agent = create_agent(
        model or get_llm(),
        tools=list(tools or ()),
        system_prompt=prompt,
        middleware=[middleware],
    )
    started = perf_counter()
    output_chars = 0
    status = "failed"
    inc_counter("a3_llm_tokens_total", _input_tokens(messages), direction="input", mode="stream")
    try:
        agent_input: Any = {"messages": conversation}
        for message, _metadata in agent.stream(
            agent_input,
            stream_mode="messages",
        ):
            if not isinstance(message, (AIMessageChunk, AIMessage)):
                continue
            content = message.content
            if isinstance(content, str) and content:
                output_chars += len(content)
                yield content
        status = "completed"
    except GeneratorExit:
        status = "cancelled"
        raise
    finally:
        inc_counter("a3_llm_requests_total", mode="stream", status=status)
        if output_chars:
            inc_counter(
                "a3_llm_tokens_total",
                max(1, (output_chars + 3) // 4),
                direction="output",
                mode="stream",
            )
        observe("a3_llm_request_duration_seconds", perf_counter() - started, mode="stream")


def invoke_agent_content(messages: Sequence[BaseMessage], **kwargs: Any) -> str:
    return str(invoke_agent_messages(messages, **kwargs).message.content or "").strip()


def invoke_agent_structured(
    messages: Sequence[BaseMessage],
    schema: type,
    *,
    model=None,
):
    prompt, conversation = _split_messages(messages)
    agent = create_agent(
        model or get_llm(),
        tools=[],
        system_prompt=prompt,
        response_format=schema,
    )
    started = perf_counter()
    inc_counter("a3_llm_tokens_total", _input_tokens(messages), direction="input", mode="structured")
    try:
        agent_input: Any = {"messages": conversation}
        state = agent.invoke(agent_input)
        response = state.get("structured_response")
        if response is None:
            raise RuntimeError("create_agent 未返回结构化结果")
        inc_counter(
            "a3_llm_tokens_total",
            _estimated_tokens(response),
            direction="output",
            mode="structured",
        )
        inc_counter("a3_llm_requests_total", mode="structured", status="completed")
        return response
    except Exception:
        inc_counter("a3_llm_requests_total", mode="structured", status="failed")
        raise
    finally:
        observe("a3_llm_request_duration_seconds", perf_counter() - started, mode="structured")


__all__ = [
    "AgentInvocation",
    "ConfirmationRequest",
    "RiskConfirmationMiddleware",
    "invoke_agent_content",
    "invoke_agent_messages",
    "invoke_agent_structured",
    "stream_agent_content",
]
