from pathlib import Path
from threading import Event

import pytest

from app.core.errors import AppError
from app.modules.agent.service import _execution_summary, list_agent_tools
from app.modules.agent.tools import (
    PolicyGuard,
    SandboxExecutor,
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutor,
    ToolRegistry,
    build_default_tool_registry,
    calculate_expression,
    integration_status,
)


def test_default_registry_exposes_real_risk_and_confirmation_metadata():
    registry = build_default_tool_registry()

    assert registry.get("calculator").risk_level == "read"
    assert registry.get("python_sandbox").risk_level == "sandboxed"
    assert registry.get("python_sandbox").display_name == "受限 Python 执行器"
    assert registry.get("python_sandbox").maturity == "experimental"
    assert registry.get("python_sandbox").isolation_level == "application"
    assert registry.get("python_sandbox").public_untrusted_access_allowed is False
    deletion = registry.get("delete_task")
    assert deletion.risk_level == "destructive"
    assert deletion.confirmation_required is True
    assert {"list_course_files", "integration_status"}.issubset(
        {item.name for item in registry.list()}
    )


def test_registry_rejects_duplicates_and_policy_rejects_risk_downgrade():
    registry = ToolRegistry()
    definition = ToolDefinition("write", "write", "test", "destructive", None, False, True)
    registry.register(definition)
    with pytest.raises(ValueError):
        registry.register(definition)
    with pytest.raises(AppError) as error:
        PolicyGuard().validate(
            definition,
            requested_risk="read",
            arguments={},
            execution_context=ToolExecutionContext(user_id=1, course_id=1),
        )
    assert error.value.error_code == "TOOL_POLICY_MISMATCH"


def test_tool_executor_applies_timeout_and_records_verifiable_status():
    registry = ToolRegistry()
    registry.register(ToolDefinition("slow", "slow read", "test", "read", 0.02, False))
    records = []
    release = Event()
    executor = ToolExecutor(registry)

    with pytest.raises(AppError) as error:
        executor.execute(
            name="slow",
            requested_risk="read",
            arguments={},
            execution_context=ToolExecutionContext(user_id=1, course_id=None),
            callback=lambda: release.wait(0.2),
            durable_execute=lambda _name, _risk, _args, callback: callback(),
            record_sink=records.append,
        )
    release.set()

    assert error.value.error_code == "TOOL_TIMEOUT"
    assert records[0]["status"] == "timeout"
    assert records[0]["duration_ms"] >= 10


def test_policy_rejects_confirmation_bypass():
    definition = ToolDefinition(
        "delete", "delete", "write", "destructive", None, False, True
    )

    with pytest.raises(AppError) as error:
        PolicyGuard().validate(
            definition,
            requested_risk="destructive",
            arguments={"id": 1},
            execution_context=ToolExecutionContext(user_id=1, course_id=None),
        )

    assert error.value.error_code == "TOOL_CONFIRMATION_REQUIRED"

    PolicyGuard().validate(
        definition,
        requested_risk="destructive",
        arguments={"id": 1},
        execution_context=ToolExecutionContext(
            user_id=1,
            course_id=None,
            confirmation_granted=True,
        ),
    )


def test_calculator_allows_arithmetic_and_rejects_code():
    assert calculate_expression("(12 + 3) * 4 / 2")["result"] == 30
    with pytest.raises(AppError) as error:
        calculate_expression("__import__('os').getcwd()")
    assert error.value.error_code == "CALCULATOR_EXPRESSION_INVALID"


def test_restricted_python_executor_reports_application_boundary_and_blocks_access(tmp_path: Path):
    sandbox = SandboxExecutor(root=tmp_path, timeout_seconds=2)
    result = sandbox.execute(
        "values = [1, 2, 3]\nprint(sum(values))",
        user_id=7,
        course_id=9,
    )
    assert result["status"] == "completed"
    assert result["stdout"].strip() == "6"
    assert "no_network" in result["restrictions"]
    assert result["maturity"] == "experimental"
    assert result["isolation_level"] == "application"
    assert result["public_untrusted_access_allowed"] is False
    assert "容器" in result["security_notice"]

    with pytest.raises(AppError) as import_error:
        sandbox.execute("import socket", user_id=7, course_id=9)
    assert import_error.value.error_code == "SANDBOX_POLICY_BLOCKED"
    with pytest.raises(AppError) as file_error:
        sandbox.execute("open('x.txt', 'w')", user_id=7, course_id=9)
    assert file_error.value.error_code == "SANDBOX_POLICY_BLOCKED"
    assert list(tmp_path.rglob("x.txt")) == []


def test_python_sandbox_enforces_output_and_memory_limits(tmp_path: Path):
    sandbox = SandboxExecutor(
        root=tmp_path,
        timeout_seconds=2,
        memory_limit_bytes=48 * 1024 * 1024,
    )
    with pytest.raises(AppError) as output_error:
        sandbox.execute("print('x' * 9000)", user_id=7, course_id=9)
    assert output_error.value.error_code == "SANDBOX_OUTPUT_LIMIT"

    with pytest.raises(AppError) as memory_error:
        sandbox.execute(
            "values = bytearray(80 * 1024 * 1024)\nwhile True:\n    pass",
            user_id=7,
            course_id=9,
        )
    assert memory_error.value.error_code == "SANDBOX_MEMORY_LIMIT"


def test_unconfigured_integrations_never_report_fake_success(monkeypatch):
    for key in (
        "A3_MCP_ENABLED",
        "A3_MCP_ENDPOINT",
        "A3_IMAGE_TOOL_ENABLED",
        "A3_IMAGE_TOOL_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)

    status = integration_status()
    assert status["integrations"]["mcp"] == {
        "status": "unconfigured",
        "configured": False,
    }
    assert status["integrations"]["image"]["status"] == "unconfigured"
    catalog = list_agent_tools()
    assert catalog["integrations"] == status["integrations"]


def test_integration_states_distinguish_disabled_misconfigured_and_missing_adapter(monkeypatch):
    monkeypatch.setenv("A3_MCP_ENABLED", "false")
    monkeypatch.setenv("A3_MCP_ENDPOINT", "https://mcp.example.test")
    monkeypatch.setenv("A3_IMAGE_TOOL_ENABLED", "true")
    monkeypatch.delenv("A3_IMAGE_TOOL_ENDPOINT", raising=False)

    status = integration_status()
    assert status["integrations"]["mcp"]["status"] == "disabled"
    assert status["integrations"]["image"]["status"] == "misconfigured"

    monkeypatch.setenv("A3_MCP_ENABLED", "true")
    status = integration_status()
    assert status["integrations"]["mcp"] == {
        "status": "configured_not_implemented",
        "configured": True,
        "endpoint_configured": True,
        "adapter_implemented": False,
    }
    assert status["integrations"]["mcp"]["status"] != "available"


def test_policy_rejects_configured_but_unimplemented_tool():
    definition = ToolDefinition(
        "future_adapter",
        "not executable",
        "integration",
        availability="configured_not_implemented",
    )
    with pytest.raises(AppError) as error:
        PolicyGuard().validate(
            definition,
            requested_risk="read",
            arguments={},
            execution_context=ToolExecutionContext(user_id=1, course_id=1),
        )
    assert error.value.error_code == "TOOL_UNAVAILABLE"


def test_execution_summary_contains_sources_and_tool_states_but_no_reasoning():
    summary = _execution_summary(
        {
            "tool_executions": [
                {
                    "name": "search_course_knowledge",
                    "status": "completed",
                    "risk_level": "read",
                    "duration_ms": 12.5,
                }
            ],
            "context_report": {"memory_count": 2, "weak_point_count": 3, "recent_turns": 4},
        },
        [{"chunk_id": 11, "material_title": "课程讲义"}],
        [{"id": 5, "title": "外部文章", "url": "https://example.com"}],
    )

    assert summary["tools"][0]["status"] == "completed"
    assert summary["internal_sources"] == [{"chunk_id": 11, "material_title": "课程讲义"}]
    assert summary["external_sources"][0]["title"] == "外部文章"
    assert summary["context_used"]["memory_count"] == 2
    assert "推理过程" in summary["note"]
    assert "chain" not in str(summary).lower()
