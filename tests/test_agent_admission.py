import asyncio

import pytest

from app.core.errors import AppError
from app.modules.agent.admission import AdmissionLimits, AgentAdmissionController


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_admission_limits_concurrent_requests_per_user():
    controller = AgentAdmissionController(
        AdmissionLimits(per_user_concurrency=1, per_user_requests_per_minute=10)
    )
    controller.acquire(7)
    with pytest.raises(AppError) as error:
        controller.acquire(7)
    assert error.value.status_code == 429
    assert error.value.error_code == "AGENT_CONCURRENCY_LIMITED"

    controller.release(7)
    controller.acquire(7)
    controller.release(7)


def test_admission_uses_independent_user_slots():
    controller = AgentAdmissionController(
        AdmissionLimits(per_user_concurrency=1, per_user_requests_per_minute=10)
    )
    controller.acquire(7)
    controller.acquire(8)
    controller.release(7)
    controller.release(8)


def test_admission_rolling_rate_window_expires():
    clock = Clock()
    controller = AgentAdmissionController(
        AdmissionLimits(per_user_concurrency=1, per_user_requests_per_minute=2),
        clock=clock,
    )
    for _ in range(2):
        with controller.slot(7):
            pass

    with pytest.raises(AppError) as error:
        controller.acquire(7)
    assert error.value.error_code == "AGENT_RATE_LIMITED"

    clock.value = 60.0
    with controller.slot(7):
        pass


def test_admission_context_releases_after_failure():
    controller = AgentAdmissionController(
        AdmissionLimits(per_user_concurrency=1, per_user_requests_per_minute=10)
    )
    with pytest.raises(RuntimeError):
        with controller.slot(7):
            raise RuntimeError("boom")

    with controller.slot(7):
        pass


def test_admitted_stream_releases_when_closed_before_first_iteration():
    controller = AgentAdmissionController(
        AdmissionLimits(per_user_concurrency=1, per_user_requests_per_minute=10)
    )

    async def source():
        yield "never started"

    admitted = controller.admit_stream(7, source())
    asyncio.run(admitted.aclose())

    with controller.slot(7):
        pass


def test_admission_prunes_expired_one_time_users():
    clock = Clock()
    controller = AgentAdmissionController(
        AdmissionLimits(per_user_concurrency=1, per_user_requests_per_minute=10),
        clock=clock,
    )
    for user_id in range(1, 101):
        with controller.slot(user_id):
            pass
    assert len(controller._requests) == 100

    clock.value = 60.0
    with controller.slot(999):
        pass

    assert set(controller._requests) == {999}
