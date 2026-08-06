"""Verify _prepare_context treats duplicate client_request_id by run status.

These tests call _prepare_context directly with all database/repository
dependencies replaced by mocks, so they run without a real DB.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.modules.agent.schemas import AgentChatRequest


def _make_request(
    message: str = "hello",
    course_id: int | None = 5,
    session_id: int | None = 10,
) -> tuple[str, AgentChatRequest]:
    """Return (raw_uuid, request) ready for _prepare_context."""
    rid = uuid4()
    raw_id = str(rid)
    return raw_id, AgentChatRequest(
        message=message,
        client_request_id=rid,
        course_id=course_id,
        session_id=session_id,
    )


def _base_run(**overrides) -> dict:
    """Build a minimal agent_runs row dict."""
    base = {
        "id": 999,
        "status": "running",
        "user_message_id": 1,
        "assistant_message_id": None,
        "input_hash": None,  # filled per-test
        "session_id": 10,
        "course_id": 5,
        "request_id": "fake-req-id",
        "intent": "native_tool_agent",
        "risk_level": "mixed",
    }
    base.update(overrides)
    return base


def _compute_input_hash(user_id, session_id, course_id, message, intent, risk_level):
    """Mirror the production hash so tests verify the right comparison."""
    from app.modules.agent.service import _agent_input_hash

    return _agent_input_hash(user_id, session_id, course_id, message, intent, risk_level)


@pytest.fixture()
def _patches():
    """Provide a dict of all Patches needed to drive _prepare_context
    through a duplicate-request path without a real database.

    Returns a factory so each test can customize the `run` row and messages.
    """

    def _factory(
        *,
        run: dict,
        assistant_message: dict | None = None,
        user_message: dict | None = None,
    ):
        cursor = MagicMock()

        @contextmanager
        def fake_get_cursor():
            yield cursor

        def _get_message(_cursor, mid, _uid):
            if mid == run.get("user_message_id") and mid is not None:
                return user_message or {
                    "id": mid,
                    "role": "user",
                    "content": "question",
                }
            if mid == run.get("assistant_message_id") and mid is not None:
                return assistant_message
            return None

        return {
            "get_cursor": patch(
                "app.modules.agent.service.get_cursor", fake_get_cursor
            ),
            "get_user_server_time": patch(
                "app.modules.agent.service.get_user_server_time",
                return_value="2025-01-01T00:00:00Z",
            ),
            "get_session": patch(
                "app.modules.agent.service.repository.get_session",
                return_value={"id": 10, "course_id": 5},
            ),
            "get_course": patch(
                "app.modules.agent.service.course_repository.get_course",
                return_value={"id": 5},
            ),
            "get_current_course": patch(
                "app.modules.agent.service.course_repository.get_current_course",
                return_value={"id": 5},
            ),
            "ensure_course_agent": patch(
                "app.modules.agent.service.repository.ensure_course_agent",
                return_value={
                    "id": 1,
                    "primary_session": {"id": 10, "course_id": 5},
                },
            ),
            "list_course_memories": patch(
                "app.modules.agent.service.repository.list_course_memories",
                return_value=[],
            ),
            "claim_agent_run": patch(
                "app.modules.agent.service.repository.claim_agent_run",
                return_value=(run, False),
            ),
            "get_message": patch(
                "app.modules.agent.service.repository.get_message",
                side_effect=_get_message,
            ),
            "load_profile": patch(
                "app.modules.agent.service.repository.load_profile",
                return_value=None,
            ),
            "get_memory_settings": patch(
                "app.modules.agent.service.repository.get_memory_settings",
                return_value={},
            ),
            "get_user_learning_profile": patch(
                "app.modules.agent.service.repository.get_user_learning_profile",
                return_value=None,
            ),
            "list_points_with_mastery": patch(
                "app.modules.agent.service.learning_repository.list_points_with_mastery",
                return_value=[],
            ),
        }

    return _factory


def _run_prepare(request_id: str, request: AgentChatRequest, patches: dict):
    """Start all patches, call _prepare_context, stop patches."""
    from app.modules.agent.service import _prepare_context

    active = list(patches.values())
    for p in active:
        p.start()
    try:
        return _prepare_context(1, request, "native_tool_agent", "mixed")
    finally:
        for p in reversed(active):
            p.stop()


# ── completed + assistant_message → duplicate_request: True ─────────────


def test_completed_with_assistant_returns_duplicate(_patches):
    assistant = {"id": 2, "role": "assistant", "content": "cached answer"}
    run = _base_run(status="completed", assistant_message_id=2)
    # Compute the real input_hash so the mismatch check passes
    run["input_hash"] = _compute_input_hash(1, 10, 5, "hello", "native_tool_agent", "mixed")
    patches = _patches(run=run, assistant_message=assistant)
    rid, req = _make_request()
    result = _run_prepare(rid, req, patches)
    assert result["duplicate_request"] is True
    assert result["existing_assistant_message"] == assistant


# ── waiting_confirmation + assistant_message → duplicate_request: True ──


def test_waiting_confirmation_with_assistant_returns_duplicate(_patches):
    assistant = {"id": 2, "role": "assistant", "content": "needs confirm"}
    run = _base_run(status="waiting_confirmation", assistant_message_id=2)
    run["input_hash"] = _compute_input_hash(1, 10, 5, "hello", "native_tool_agent", "mixed")
    patches = _patches(run=run, assistant_message=assistant)
    rid, req = _make_request()
    result = _run_prepare(rid, req, patches)
    assert result["duplicate_request"] is True
    assert result["existing_assistant_message"] == assistant


# ── running → AGENT_REQUEST_IN_PROGRESS ─────────────────────────────────


def test_running_raises_in_progress(_patches):
    run = _base_run(status="running")
    run["input_hash"] = _compute_input_hash(1, 10, 5, "hello", "native_tool_agent", "mixed")
    patches = _patches(run=run)
    rid, req = _make_request()
    with pytest.raises(AppError) as exc:
        _run_prepare(rid, req, patches)
    assert exc.value.error_code == "AGENT_REQUEST_IN_PROGRESS"
    assert exc.value.status_code == 409


# ── failed → AGENT_PREVIOUS_REQUEST_FAILED ──────────────────────────────


def test_failed_raises_previous_failed(_patches):
    run = _base_run(status="failed")
    run["input_hash"] = _compute_input_hash(1, 10, 5, "hello", "native_tool_agent", "mixed")
    patches = _patches(run=run)
    rid, req = _make_request()
    with pytest.raises(AppError) as exc:
        _run_prepare(rid, req, patches)
    assert exc.value.error_code == "AGENT_PREVIOUS_REQUEST_FAILED"
    assert exc.value.status_code == 409


# ── cancelled → AGENT_PREVIOUS_REQUEST_CANCELLED ────────────────────────


def test_cancelled_raises_previous_cancelled(_patches):
    run = _base_run(status="cancelled")
    run["input_hash"] = _compute_input_hash(1, 10, 5, "hello", "native_tool_agent", "mixed")
    patches = _patches(run=run)
    rid, req = _make_request()
    with pytest.raises(AppError) as exc:
        _run_prepare(rid, req, patches)
    assert exc.value.error_code == "AGENT_PREVIOUS_REQUEST_CANCELLED"
    assert exc.value.status_code == 409


# ── completed but no assistant_message → AGENT_RESULT_INCOMPLETE ────────


def test_completed_without_assistant_raises_incomplete(_patches):
    run = _base_run(status="completed", assistant_message_id=None)
    run["input_hash"] = _compute_input_hash(1, 10, 5, "hello", "native_tool_agent", "mixed")
    patches = _patches(run=run, assistant_message=None)
    rid, req = _make_request()
    with pytest.raises(AppError) as exc:
        _run_prepare(rid, req, patches)
    assert exc.value.error_code == "AGENT_RESULT_INCOMPLETE"
    assert exc.value.status_code == 409


# ── unknown status → AGENT_REQUEST_STATE_INVALID ────────────────────────


def test_unknown_status_raises_state_invalid(_patches):
    run = _base_run(status="some_weird_status")
    run["input_hash"] = _compute_input_hash(1, 10, 5, "hello", "native_tool_agent", "mixed")
    patches = _patches(run=run)
    rid, req = _make_request()
    with pytest.raises(AppError) as exc:
        _run_prepare(rid, req, patches)
    assert exc.value.error_code == "AGENT_REQUEST_STATE_INVALID"
    assert exc.value.status_code == 409


# ── input_hash mismatch → CLIENT_REQUEST_ID_CONFLICT (unchanged) ────────


def test_input_hash_mismatch_raises_conflict(_patches):
    assistant = {"id": 2, "role": "assistant", "content": "prev"}
    run = _base_run(
        status="completed",
        assistant_message_id=2,
        input_hash="deliberately_wrong_hash",
    )
    patches = _patches(run=run, assistant_message=assistant)
    rid, req = _make_request()
    with pytest.raises(AppError) as exc:
        _run_prepare(rid, req, patches)
    assert exc.value.error_code == "CLIENT_REQUEST_ID_CONFLICT"
    assert exc.value.status_code == 409
