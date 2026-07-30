"""Process-local admission control for expensive Agent requests."""

from __future__ import annotations

import os
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable, Generic, Iterator, TypeVar
from weakref import finalize

from app.core.errors import AppError
from app.core.metrics import add_gauge, inc_counter


@dataclass(frozen=True)
class AdmissionLimits:
    per_user_concurrency: int = 2
    per_user_requests_per_minute: int = 30

    @classmethod
    def from_env(cls) -> "AdmissionLimits":
        return cls(
            per_user_concurrency=max(
                1,
                min(int(os.getenv("AGENT_MAX_CONCURRENT_STREAMS_PER_USER", "2")), 16),
            ),
            per_user_requests_per_minute=max(
                1,
                min(int(os.getenv("AGENT_REQUESTS_PER_MINUTE", "30")), 600),
            ),
        )


_T = TypeVar("_T")


class AdmittedAsyncIterator(AsyncIterator[_T], Generic[_T]):
    """Release an admission slot even when a response body is closed before iteration."""

    def __init__(
        self,
        iterator: AsyncIterator[_T],
        controller: "AgentAdmissionController",
        user_id: int,
    ) -> None:
        self._iterator = iterator
        self._controller = controller
        self._user_id = int(user_id)
        self._released = False
        self._finalizer = finalize(self, controller.release, self._user_id)

    def __aiter__(self) -> "AdmittedAsyncIterator[_T]":
        return self

    def _release(self) -> None:
        if self._released:
            return
        self._released = True
        self._finalizer.detach()
        self._controller.release(self._user_id)

    async def __anext__(self) -> _T:
        try:
            return await self._iterator.__anext__()
        except StopAsyncIteration:
            self._release()
            raise
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        self._release()
        closer = getattr(self._iterator, "aclose", None)
        if closer is not None:
            await closer()


class AgentAdmissionController:
    """Bound concurrent and rolling-window requests for each authenticated user."""

    def __init__(
        self,
        limits: AdmissionLimits | None = None,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.limits = limits or AdmissionLimits.from_env()
        self._clock = clock
        self._lock = Lock()
        self._active: dict[int, int] = defaultdict(int)
        self._requests: dict[int, deque[float]] = defaultdict(deque)
        self._last_cleanup = self._clock()

    def _cleanup_expired_locked(self, now: float) -> None:
        if now - self._last_cleanup < 60.0:
            return
        for tracked_user_id, timestamps in list(self._requests.items()):
            while timestamps and now - timestamps[0] >= 60.0:
                timestamps.popleft()
            if not timestamps and self._active.get(tracked_user_id, 0) == 0:
                self._requests.pop(tracked_user_id, None)
        self._last_cleanup = now

    def acquire(self, user_id: int) -> None:
        normalized_user_id = int(user_id)
        now = self._clock()
        with self._lock:
            self._cleanup_expired_locked(now)
            timestamps = self._requests[normalized_user_id]
            while timestamps and now - timestamps[0] >= 60.0:
                timestamps.popleft()
            if self._active[normalized_user_id] >= self.limits.per_user_concurrency:
                inc_counter("a3_agent_admission_rejected_total", reason="concurrency")
                raise AppError(
                    "当前已有学习助手请求正在处理，请等待完成后再试",
                    429,
                    "AGENT_CONCURRENCY_LIMITED",
                )
            if len(timestamps) >= self.limits.per_user_requests_per_minute:
                inc_counter("a3_agent_admission_rejected_total", reason="rate")
                raise AppError(
                    "学习助手请求过于频繁，请稍后再试",
                    429,
                    "AGENT_RATE_LIMITED",
                )
            timestamps.append(now)
            self._active[normalized_user_id] += 1
            add_gauge("a3_agent_active_requests", 1)
            inc_counter("a3_agent_admission_total", status="accepted")

    def release(self, user_id: int) -> None:
        normalized_user_id = int(user_id)
        with self._lock:
            active = self._active.get(normalized_user_id, 0)
            if active > 0:
                self._active[normalized_user_id] = active - 1
                add_gauge("a3_agent_active_requests", -1)
            if self._active.get(normalized_user_id, 0) == 0:
                self._active.pop(normalized_user_id, None)
                timestamps = self._requests.get(normalized_user_id)
                if timestamps is not None and not timestamps:
                    self._requests.pop(normalized_user_id, None)

    @contextmanager
    def slot(self, user_id: int) -> Iterator[None]:
        self.acquire(user_id)
        try:
            yield
        finally:
            self.release(user_id)

    def admit_stream(
        self,
        user_id: int,
        iterator: AsyncIterator[_T],
    ) -> AdmittedAsyncIterator[_T]:
        self.acquire(user_id)
        try:
            return AdmittedAsyncIterator(iterator, self, user_id)
        except BaseException:
            self.release(user_id)
            raise


agent_admission = AgentAdmissionController()


__all__ = [
    "AdmissionLimits",
    "AdmittedAsyncIterator",
    "AgentAdmissionController",
    "agent_admission",
]
