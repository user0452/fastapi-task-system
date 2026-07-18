from __future__ import annotations

import ast
import ctypes
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import Any, Callable

from app.core.errors import AppError


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    category: str
    risk_level: str = "read"
    timeout_seconds: float | None = None
    requires_course: bool = True
    confirmation_required: bool = False
    availability: str = "available"
    display_name: str | None = None
    maturity: str = "stable"
    isolation_level: str | None = None
    public_untrusted_access_allowed: bool | None = None

    def public(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ToolExecutionContext:
    user_id: int
    course_id: int | None
    request_id: str | None = None
    confirmation_granted: bool = False

    @property
    def has_course(self) -> bool:
        return self.course_id is not None


@dataclass(frozen=True)
class ToolExecutionResult:
    value: Any
    record: dict[str, Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"工具已注册：{definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise AppError("工具未注册", 400, "TOOL_NOT_REGISTERED") from exc

    def list(self) -> list[ToolDefinition]:
        return sorted(self._definitions.values(), key=lambda item: (item.category, item.name))


class PolicyGuard:
    MAX_ARGUMENT_BYTES = 32_000

    def validate(
        self,
        definition: ToolDefinition,
        *,
        requested_risk: str,
        arguments: dict,
        execution_context: ToolExecutionContext,
    ) -> None:
        if definition.availability != "available":
            raise AppError("工具当前不可用", 409, "TOOL_UNAVAILABLE")
        if definition.risk_level != requested_risk:
            raise AppError("工具风险级别与注册策略不一致", 409, "TOOL_POLICY_MISMATCH")
        if definition.requires_course and not execution_context.has_course:
            raise AppError("请先选择课程后再使用该工具", 409, "TOOL_COURSE_REQUIRED")
        if definition.confirmation_required and not execution_context.confirmation_granted:
            raise AppError("该工具必须先获得用户确认", 409, "TOOL_CONFIRMATION_REQUIRED")
        payload = json.dumps(arguments, ensure_ascii=False, default=str).encode("utf-8")
        if len(payload) > self.MAX_ARGUMENT_BYTES:
            raise AppError("工具参数过大", 413, "TOOL_ARGUMENTS_TOO_LARGE")


class ToolTimeoutError(AppError):
    def __init__(self, tool_name: str, timeout_seconds: float):
        super().__init__(
            f"工具 {tool_name} 超过 {timeout_seconds:g} 秒执行时限",
            504,
            "TOOL_TIMEOUT",
        )


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, guard: PolicyGuard | None = None):
        self.registry = registry
        self.guard = guard or PolicyGuard()

    @staticmethod
    def _with_timeout(
        definition: ToolDefinition,
        callback: Callable[[], Any],
    ) -> Any:
        if definition.timeout_seconds is None:
            return callback()
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{definition.name}")
        future = pool.submit(callback)
        timed_out = False
        try:
            return future.result(timeout=definition.timeout_seconds)
        except FutureTimeoutError as exc:
            timed_out = True
            future.cancel()
            raise ToolTimeoutError(definition.name, definition.timeout_seconds) from exc
        finally:
            pool.shutdown(wait=not timed_out, cancel_futures=True)

    def execute(
        self,
        *,
        name: str,
        requested_risk: str,
        arguments: dict,
        execution_context: ToolExecutionContext,
        callback: Callable[[], Any],
        durable_execute: Callable[[str, str, dict, Callable[[], Any]], Any],
        record_sink: Callable[[dict], None] | None = None,
    ) -> ToolExecutionResult:
        definition = self.registry.get(name)
        self.guard.validate(
            definition,
            requested_risk=requested_risk,
            arguments=arguments,
            execution_context=execution_context,
        )
        started = perf_counter()
        record: dict[str, Any] = {
            "name": definition.name,
            "category": definition.category,
            "risk_level": definition.risk_level,
            "status": "failed",
        }
        try:
            result = durable_execute(
                definition.name,
                definition.risk_level,
                arguments,
                lambda: self._with_timeout(definition, callback),
            )
        except AppError as exc:
            record["status"] = "timeout" if exc.error_code == "TOOL_TIMEOUT" else "failed"
            record["error_code"] = exc.error_code
            raise
        except Exception:
            record["status"] = "failed"
            record["error_code"] = "TOOL_EXECUTION_FAILED"
            raise
        else:
            record["status"] = "completed"
            if isinstance(result, dict) and result.get("status") in {
                "available", "unconfigured", "misconfigured",
                "configured_not_implemented", "disabled",
            }:
                record["result_status"] = result["status"]
            return ToolExecutionResult(value=result, record=record)
        finally:
            record["duration_ms"] = round((perf_counter() - started) * 1000, 2)
            if record_sink is not None:
                record_sink(dict(record))


_ALLOWED_BINARY = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}
_ALLOWED_UNARY = {ast.UAdd: lambda value: value, ast.USub: lambda value: -value}


def _evaluate_math(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate_math(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY:
        left = _evaluate_math(node.left)
        right = _evaluate_math(node.right)
        if isinstance(node.op, ast.Pow) and abs(float(right)) > 12:
            raise ValueError("指数绝对值不能超过 12")
        value = _ALLOWED_BINARY[type(node.op)](left, right)
        if abs(float(value)) > 1e100:
            raise ValueError("计算结果超出范围")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return _ALLOWED_UNARY[type(node.op)](_evaluate_math(node.operand))
    raise ValueError("表达式仅允许数字、括号和基础算术运算")


def calculate_expression(expression: str) -> dict:
    value = str(expression or "").strip()
    if not value or len(value) > 500:
        raise AppError("计算表达式不能为空且不能超过 500 字符", 422, "CALCULATOR_INPUT_INVALID")
    try:
        parsed = ast.parse(value, mode="eval")
        result = _evaluate_math(parsed)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise AppError(str(exc), 422, "CALCULATOR_EXPRESSION_INVALID") from exc
    return {"expression": value, "result": result}


class SandboxExecutor:
    MAX_CODE_LENGTH = 8_000
    MAX_OUTPUT_BYTES = 8_192
    MAX_MEMORY_BYTES = 128 * 1024 * 1024
    FORBIDDEN_NODES = (
        ast.Import,
        ast.ImportFrom,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.Lambda,
        ast.Global,
        ast.Nonlocal,
    )
    FORBIDDEN_NAMES = {
        "open", "exec", "eval", "compile", "input", "__import__", "breakpoint",
        "globals", "locals", "vars", "getattr", "setattr", "delattr", "help",
        "memoryview", "classmethod", "staticmethod",
    }

    def __init__(
        self,
        root: Path | None = None,
        timeout_seconds: float = 4.0,
        memory_limit_bytes: int = MAX_MEMORY_BYTES,
    ):
        self.root = root or Path(tempfile.gettempdir()) / "a3-python-sandbox"
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 8.0))
        self.memory_limit_bytes = max(48 * 1024 * 1024, min(int(memory_limit_bytes), 256 * 1024 * 1024))

    @staticmethod
    def _process_memory_bytes(process_id: int) -> int:
        if os.name != "nt":
            status_path = Path(f"/proc/{process_id}/status")
            try:
                for line in status_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
            except (FileNotFoundError, OSError, ValueError, IndexError):
                return 0
            return 0

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        process_query_information = 0x0400
        process_vm_read = 0x0010
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return 0
        kernel32 = windll.kernel32
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        psapi = windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        handle = kernel32.OpenProcess(
            process_query_information | process_vm_read,
            False,
            process_id,
        )
        if not handle:
            return 0
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        try:
            if not psapi.GetProcessMemoryInfo(
                handle,
                ctypes.byref(counters),
                counters.cb,
            ):
                return 0
            return int(max(counters.WorkingSetSize, counters.PagefileUsage))
        finally:
            kernel32.CloseHandle(handle)

    def _validate(self, code: str) -> None:
        if not code.strip() or len(code) > self.MAX_CODE_LENGTH:
            raise AppError("Python 代码不能为空且不能超过 8000 字符", 422, "SANDBOX_CODE_INVALID")
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            raise AppError(f"Python 语法错误：{exc.msg}", 422, "SANDBOX_CODE_INVALID") from exc
        for node in ast.walk(tree):
            if isinstance(node, self.FORBIDDEN_NODES):
                raise AppError("受限 Python 执行器禁止导入、文件上下文、函数/类定义和异常捕获", 422, "SANDBOX_POLICY_BLOCKED")
            if isinstance(node, ast.Name) and node.id in self.FORBIDDEN_NAMES:
                raise AppError(f"受限 Python 执行器禁止调用 {node.id}", 422, "SANDBOX_POLICY_BLOCKED")
            if isinstance(node, ast.Attribute) and str(node.attr).startswith("__"):
                raise AppError("受限 Python 执行器禁止访问双下划线属性", 422, "SANDBOX_POLICY_BLOCKED")

    def execute(self, code: str, *, user_id: int, course_id: int) -> dict:
        self._validate(code)
        self.root.mkdir(parents=True, exist_ok=True)
        started = perf_counter()
        with tempfile.TemporaryDirectory(
            prefix=f"u{user_id}-c{course_id}-",
            dir=self.root,
        ) as directory:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            python_executable = Path(getattr(sys, "_base_executable", sys.executable))
            env = {
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "PATH": str(python_executable.parent),
            }
            stdout_path = Path(directory) / "stdout.txt"
            stderr_path = Path(directory) / "stderr.txt"
            limit_error: AppError | None = None
            with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
                process_context = subprocess.Popen(
                    [str(python_executable), "-I", "-S", "-c", code],
                    cwd=directory,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    creationflags=creationflags,
                )
                with process_context as process:
                    while process.poll() is None:
                        elapsed = perf_counter() - started
                        if elapsed > self.timeout_seconds:
                            limit_error = ToolTimeoutError("python_sandbox", self.timeout_seconds)
                        elif self._process_memory_bytes(process.pid) > self.memory_limit_bytes:
                            limit_error = AppError(
                                "受限 Python 执行器超过内存限制",
                                422,
                                "SANDBOX_MEMORY_LIMIT",
                            )
                        elif (
                            stdout_path.stat().st_size > self.MAX_OUTPUT_BYTES
                            or stderr_path.stat().st_size > self.MAX_OUTPUT_BYTES
                        ):
                            limit_error = AppError(
                                "受限 Python 执行器输出超过限制",
                                422,
                                "SANDBOX_OUTPUT_LIMIT",
                            )
                        if limit_error is not None:
                            process.kill()
                            process.wait(timeout=2)
                            break
                        sleep(0.02)
                    return_code = process.returncode
                if limit_error is not None and os.name == "nt":
                    sleep(0.05)
            stdout_bytes = stdout_path.read_bytes()
            stderr_bytes = stderr_path.read_bytes()
            if limit_error is None and (
                len(stdout_bytes) > self.MAX_OUTPUT_BYTES
                or len(stderr_bytes) > self.MAX_OUTPUT_BYTES
            ):
                limit_error = AppError(
                    "受限 Python 执行器输出超过限制",
                    422,
                    "SANDBOX_OUTPUT_LIMIT",
                )
            if limit_error is not None:
                raise limit_error
        stdout = stdout_bytes[: self.MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        stderr = stderr_bytes[: self.MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        return {
            "status": "completed" if return_code == 0 else "failed",
            "exit_code": return_code,
            "stdout": stdout,
            "stderr": stderr,
            "output_truncated": False,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
            "maturity": "experimental",
            "isolation_level": "application",
            "public_untrusted_access_allowed": False,
            "security_notice": (
                "仅提供应用级限制，不是容器、cgroup、seccomp 或独立虚拟机隔离。"
            ),
            "restrictions": [
                "no_imports", "no_files", "no_network", "no_subprocesses",
                "separate_process", f"memory_{self.memory_limit_bytes // (1024 * 1024)}mb",
            ],
        }


def _integration_item(
    enabled_key: str,
    endpoint_key: str,
    *,
    adapter_implemented: bool = False,
) -> dict:
    raw_enabled = os.getenv(enabled_key)
    endpoint = os.getenv(endpoint_key, "").strip()
    if raw_enabled is None or not raw_enabled.strip():
        return {"status": "unconfigured", "configured": False}
    enabled = raw_enabled.strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return {"status": "disabled", "configured": False}
    if enabled not in {"1", "true", "yes", "on"}:
        return {"status": "misconfigured", "configured": False}
    if not endpoint:
        return {"status": "misconfigured", "configured": False}
    if not adapter_implemented:
        return {
            "status": "configured_not_implemented",
            "configured": True,
            "endpoint_configured": True,
            "adapter_implemented": False,
        }
    return {
        "status": "available",
        "configured": True,
        "endpoint_configured": True,
        "adapter_implemented": True,
    }


def integration_status() -> dict:
    return {
        "status": "available",
        "integrations": {
            "mcp": _integration_item("A3_MCP_ENABLED", "A3_MCP_ENDPOINT"),
            "image": _integration_item("A3_IMAGE_TOOL_ENABLED", "A3_IMAGE_TOOL_ENDPOINT"),
        },
        "message": "未接入真实执行适配器的外部能力不可调用，也不会返回模拟成功结果。",
    }


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    definitions = [
        ToolDefinition("get_today_learning", "读取今日学习单元", "course", "read", 20),
        ToolDefinition("get_course_progress", "读取课程进度与掌握度", "course", "read", 20),
        ToolDefinition("get_study_plan", "读取每日学习计划", "course", "read", 20),
        ToolDefinition("get_wrong_answers", "读取错题摘要", "course", "read", 20),
        ToolDefinition("search_course_knowledge", "检索课程资料", "rag", "read", 25),
        ToolDefinition("read_course_evidence", "读取课程证据片段", "rag", "read", 25),
        ToolDefinition("list_course_material_outline", "列出课程文件与章节", "files", "read", 20),
        ToolDefinition("list_course_files", "列出课程文件", "files", "read", 20),
        ToolDefinition("read_course_section", "读取课程文件章节", "files", "read", 25),
        ToolDefinition("search_external_resources", "搜索外部学习资源", "external", "read", 30),
        ToolDefinition("generate_practice", "生成针对性练习", "learning", "generate"),
        ToolDefinition("get_or_generate_diagnostic", "读取或生成课程诊断", "learning", "generate"),
        ToolDefinition("calculator", "执行受限算术计算", "compute", "read", 3, False),
        ToolDefinition(
            "python_sandbox",
            "执行受限 Python 代码；仅提供应用级隔离",
            "compute",
            "sandboxed",
            6,
            display_name="受限 Python 执行器",
            maturity="experimental",
            isolation_level="application",
            public_untrusted_access_allowed=False,
        ),
        ToolDefinition("integration_status", "读取 MCP 与外部工具配置状态", "integration", "read", 3, False),
        ToolDefinition("delete_task", "永久删除本人任务", "write", "destructive", None, False, True),
    ]
    for definition in definitions:
        registry.register(definition)
    return registry
