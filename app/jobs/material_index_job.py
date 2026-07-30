import asyncio
import logging
import os
import socket
from contextlib import contextmanager
from threading import Event, Lock, Thread
from time import perf_counter
from typing import Callable, Iterator
from uuid import uuid4

from app.core.database import get_cursor, get_dedicated_conn
from app.core.metrics import inc_counter, observe, set_gauge
from app.modules.materials.service import (
    MATERIAL_DELETION_STATUSES,
    MaterialProcessingCancelled,
    MaterialProcessingLeaseLost,
    backfill_knowledge_point_vectors,
    process_material,
)

logger = logging.getLogger(__name__)
LEASE_MINUTES = 60
LEASE_HEARTBEAT_SECONDS = 60.0
LEASE_HEARTBEAT_RETRY_SECONDS = 5.0
LEASE_HEARTBEAT_SHUTDOWN_SECONDS = 20.0
WORKER_POLL_SECONDS = 2.0


class MaterialJobLeaseLost(MaterialProcessingLeaseLost):
    """Raised when a worker no longer owns the durable material job."""


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:10]}"


def refresh_material_job_metrics() -> None:
    counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT status, COUNT(*) AS total FROM material_processing_jobs GROUP BY status"
        )
        for row in cursor.fetchall():
            if row.get("status") is None or row.get("total") is None:
                continue
            counts[str(row["status"])] = int(row["total"])
    for status, total in counts.items():
        set_gauge("a3_material_jobs", total, status=status)


def enqueue_material_processing_job(user_id: int, course_id: int, material_id: int) -> dict:
    """Create or requeue the durable job for one material."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT IGNORE INTO material_processing_jobs
                (material_id, user_id, course_id, status, available_at)
            VALUES (%s, %s, %s, 'queued', CURRENT_TIMESTAMP(6))
            """,
            (material_id, user_id, course_id),
        )
        cursor.execute(
            """
            SELECT id, status, lease_expires_at,
                   (
                       status = 'running'
                       AND lease_expires_at IS NOT NULL
                       AND lease_expires_at > CURRENT_TIMESTAMP(6)
                   ) AS actively_running
            FROM material_processing_jobs WHERE material_id = %s FOR UPDATE
            """,
            (material_id,),
        )
        current = cursor.fetchone()
        if current is None:
            raise RuntimeError("material processing job disappeared after enqueue")
        actively_running = bool(current.get("actively_running"))
        if not actively_running:
            cursor.execute(
                """
                UPDATE material_processing_jobs
                SET attempts = IF(status = 'failed' OR attempts >= max_attempts, 0, attempts),
                    user_id = %s, course_id = %s, status = 'queued',
                    available_at = CURRENT_TIMESTAMP(6), worker_id = NULL,
                    lease_expires_at = NULL, last_error = NULL, completed_at = NULL
                WHERE id = %s
                """,
                (user_id, course_id, current["id"]),
            )
        cursor.execute(
            """
            SELECT id, material_id, user_id, course_id, status, attempts,
                   max_attempts, worker_id, lease_expires_at, available_at,
                   last_error, created_at, updated_at
            FROM material_processing_jobs WHERE material_id = %s
            """,
            (material_id,),
        )
        job = cursor.fetchone()
        if job is None:
            raise RuntimeError("material processing job could not be reloaded")
        return job


def _claim_job(material_id: int | None, worker_id: str) -> dict | None:
    with get_cursor() as cursor:
        if material_id is None:
            cursor.execute(
                """
                SELECT id
                FROM material_processing_jobs
                WHERE attempts < max_attempts
                  AND available_at <= CURRENT_TIMESTAMP(6)
                  AND (
                      status = 'queued'
                      OR (status = 'running' AND lease_expires_at <= CURRENT_TIMESTAMP(6))
                  )
                ORDER BY available_at, id
                LIMIT 1 FOR UPDATE
                """
            )
        else:
            cursor.execute(
                """
                SELECT id
                FROM material_processing_jobs
                WHERE material_id = %s AND attempts < max_attempts
                  AND available_at <= CURRENT_TIMESTAMP(6)
                  AND (
                      status = 'queued'
                      OR (status = 'running' AND lease_expires_at <= CURRENT_TIMESTAMP(6))
                  )
                LIMIT 1 FOR UPDATE
                """,
                (material_id,),
            )
        selected = cursor.fetchone()
        if selected is None:
            return None
        cursor.execute(
            """
            UPDATE material_processing_jobs
            SET status = 'running', worker_id = %s, attempts = attempts + 1,
                lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s MINUTE),
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP(6)),
                last_error = NULL
            WHERE id = %s
            """,
            (worker_id, LEASE_MINUTES, selected["id"]),
        )
        cursor.execute(
            """
            SELECT id, material_id, user_id, course_id, status, attempts,
                   max_attempts, worker_id, lease_expires_at
            FROM material_processing_jobs WHERE id = %s
            """,
            (selected["id"],),
        )
        return cursor.fetchone()


def _heartbeat(job_id: int, worker_id: str) -> None:
    connection = get_dedicated_conn(
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )
    cursor = connection.cursor()
    try:
        cursor.execute("SET SESSION innodb_lock_wait_timeout = 5")
        cursor.execute(
            """
            UPDATE material_processing_jobs
            SET lease_expires_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s MINUTE)
            WHERE id = %s AND worker_id = %s AND status = 'running'
            """,
            (LEASE_MINUTES, job_id, worker_id),
        )
        if cursor.rowcount != 1:
            raise MaterialJobLeaseLost(
                f"material job {job_id} lease is no longer owned by {worker_id}"
            )
    finally:
        cursor.close()
        connection.close()


@contextmanager
def _maintain_job_lease(job_id: int, worker_id: str) -> Iterator[Callable[[], None]]:
    """Renew a job lease during long parser/LLM calls and surface ownership loss."""
    stopped = Event()
    state_lock = Lock()
    detected_lease_loss: MaterialJobLeaseLost | None = None

    def remember_lease_loss(exc: MaterialJobLeaseLost) -> None:
        nonlocal detected_lease_loss
        with state_lock:
            if detected_lease_loss is None:
                detected_lease_loss = exc

    def known_lease_loss() -> MaterialJobLeaseLost | None:
        with state_lock:
            return detected_lease_loss

    def renew() -> None:
        try:
            _heartbeat(job_id, worker_id)
        except MaterialJobLeaseLost as exc:
            remember_lease_loss(exc)
            raise
        except Exception as exc:
            raise MaterialJobLeaseLost(
                f"material job {job_id} lease renewal failed"
            ) from exc

    def heartbeat_loop() -> None:
        delay = LEASE_HEARTBEAT_SECONDS
        while not stopped.wait(delay):
            try:
                _heartbeat(job_id, worker_id)
            except MaterialJobLeaseLost as exc:
                remember_lease_loss(exc)
                logger.warning(
                    "material_job_lease_lost job_id=%s worker_id=%s",
                    job_id,
                    worker_id,
                )
                return
            except Exception:
                logger.warning(
                    "material_job_heartbeat_failed job_id=%s worker_id=%s",
                    job_id,
                    worker_id,
                )
                delay = min(LEASE_HEARTBEAT_RETRY_SECONDS, LEASE_HEARTBEAT_SECONDS)
            else:
                delay = LEASE_HEARTBEAT_SECONDS

    thread = Thread(
        target=heartbeat_loop,
        name=f"material-job-heartbeat-{job_id}",
        daemon=True,
    )
    thread.start()
    try:
        yield renew
    except BaseException as exc:
        stopped.set()
        thread.join(timeout=LEASE_HEARTBEAT_SHUTDOWN_SECONDS)
        if thread.is_alive():
            raise MaterialJobLeaseLost(
                f"material job {job_id} heartbeat did not stop after failure"
            ) from exc
        if lease_error := known_lease_loss():
            raise lease_error from exc
        raise
    else:
        stopped.set()
        thread.join(timeout=LEASE_HEARTBEAT_SHUTDOWN_SECONDS)
        if thread.is_alive():
            raise MaterialJobLeaseLost(
                f"material job {job_id} heartbeat did not stop cleanly"
            )
        renew()


def _finish_job(job: dict, *, error: Exception | None = None) -> bool:
    with get_cursor() as cursor:
        if error is None:
            cursor.execute(
                """
                UPDATE material_processing_jobs
                SET status = 'completed', worker_id = NULL, lease_expires_at = NULL,
                    completed_at = CURRENT_TIMESTAMP(6), last_error = NULL
                WHERE id = %s AND worker_id = %s AND status = 'running'
                """,
                (job["id"], job["worker_id"]),
            )
            return cursor.rowcount == 1
        if isinstance(error, MaterialProcessingCancelled):
            cursor.execute(
                """
                UPDATE material_processing_jobs
                SET status = 'cancelled', worker_id = NULL, lease_expires_at = NULL,
                    completed_at = CURRENT_TIMESTAMP(6), last_error = %s
                WHERE id = %s AND worker_id = %s AND status = 'running'
                """,
                (str(error)[:2000], job["id"], job["worker_id"]),
            )
            return cursor.rowcount == 1
        retrying = int(job["attempts"]) < int(job["max_attempts"])
        if retrying:
            cursor.execute(
                """
                UPDATE material_processing_jobs
                SET status = 'queued', worker_id = NULL, lease_expires_at = NULL,
                    available_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s SECOND),
                    completed_at = NULL, last_error = %s
                WHERE id = %s AND worker_id = %s
                """,
                (
                    min(60, 5 * int(job["attempts"])),
                    str(error)[:2000],
                    job["id"],
                    job["worker_id"],
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE material_processing_jobs
                SET status = 'failed', worker_id = NULL, lease_expires_at = NULL,
                    available_at = CURRENT_TIMESTAMP(6),
                    completed_at = CURRENT_TIMESTAMP(6), last_error = %s
                WHERE id = %s AND worker_id = %s
                """,
                (str(error)[:2000], job["id"], job["worker_id"]),
            )
        return cursor.rowcount == 1


def run_material_processing_job(user_id: int, material_id: int) -> bool:
    """Claim and process one material; duplicate workers safely become no-ops."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT course_id, processing_status
            FROM course_materials
            WHERE id = %s AND user_id = %s
            """,
            (material_id, user_id),
        )
        material = cursor.fetchone()
    if (
        material is None
        or material.get("course_id") is None
        or material.get("processing_status") in MATERIAL_DELETION_STATUSES
    ):
        return False
    enqueue_material_processing_job(user_id, material["course_id"], material_id)
    worker_id = _worker_id()
    job = _claim_job(material_id, worker_id)
    if job is None:
        return False
    started = perf_counter()
    try:
        with _maintain_job_lease(job["id"], worker_id) as renew_lease:
            process_material(
                user_id,
                material_id,
                heartbeat=renew_lease,
            )
    except Exception as exc:
        _finish_job(job, error=exc)
        inc_counter("a3_material_job_attempts_total", status="failed")
        observe("a3_material_job_duration_seconds", perf_counter() - started, status="failed")
        logger.exception(
            "material_processing_failed user_id=%s material_id=%s job_id=%s attempt=%s",
            user_id,
            material_id,
            job["id"],
            job["attempts"],
        )
        return False
    if not _finish_job(job):
        logger.warning(
            "material_processing_completion_fenced material_id=%s job_id=%s worker_id=%s",
            material_id,
            job["id"],
            worker_id,
        )
        return False
    inc_counter("a3_material_job_attempts_total", status="completed")
    observe("a3_material_job_duration_seconds", perf_counter() - started, status="completed")
    return True


def drain_material_processing_jobs(max_jobs: int = 4) -> int:
    completed = 0
    for _ in range(max(1, max_jobs)):
        worker_id = _worker_id()
        job = _claim_job(None, worker_id)
        if job is None:
            break
        started = perf_counter()
        try:
            with _maintain_job_lease(job["id"], worker_id) as renew_lease:
                process_material(
                    job["user_id"],
                    job["material_id"],
                    heartbeat=renew_lease,
                )
        except Exception as exc:
            _finish_job(job, error=exc)
            inc_counter("a3_material_job_attempts_total", status="failed")
            observe("a3_material_job_duration_seconds", perf_counter() - started, status="failed")
            logger.exception(
                "material_processing_failed user_id=%s material_id=%s job_id=%s attempt=%s",
                job["user_id"],
                job["material_id"],
                job["id"],
                job["attempts"],
            )
        else:
            if not _finish_job(job):
                logger.warning(
                    "material_processing_completion_fenced material_id=%s "
                    "job_id=%s worker_id=%s",
                    job["material_id"],
                    job["id"],
                    worker_id,
                )
                continue
            inc_counter("a3_material_job_attempts_total", status="completed")
            observe("a3_material_job_duration_seconds", perf_counter() - started, status="completed")
            completed += 1
    refresh_material_job_metrics()
    return completed


def recover_pending_material_jobs() -> int:
    """Backfill durable jobs and process them through lease-protected claims."""
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, user_id, course_id
            FROM course_materials
            WHERE processing_status IN ('uploaded', 'parsing', 'indexing')
            ORDER BY id
            """
        )
        pending = list(cursor.fetchall())
    for material in pending:
        if material.get("course_id") is not None:
            enqueue_material_processing_job(material["user_id"], material["course_id"], material["id"])
        run_material_processing_job(material["user_id"], material["id"])
    try:
        backfill_knowledge_point_vectors()
    except Exception:
        logger.exception("knowledge_point_vector_backfill_failed")
    refresh_material_job_metrics()
    return len(pending)


async def material_job_worker(stop: asyncio.Event) -> None:
    """Continuously drain durable jobs; safe to run in every web worker."""
    while not stop.is_set():
        try:
            await asyncio.to_thread(drain_material_processing_jobs)
        except Exception:
            logger.exception("material_job_worker_iteration_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=WORKER_POLL_SECONDS)
        except TimeoutError:
            pass
