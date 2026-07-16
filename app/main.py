import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pymysql
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import api_router
from app.core import schema
from app.core.config import get_settings
from app.core.database import get_conn
from app.core.errors import AppError, app_error_handler, error_payload
from app.core.logging import bind_request_id, configure_logging, reset_request_id
from app.core.metrics import inc_counter, observe, render_prometheus
from app.jobs.material_index_job import material_job_worker, recover_pending_material_jobs

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    get_settings().validate_startup()
    from app.modules.agent.service import gc_agent_checkpoints

    worker_stop = asyncio.Event()
    recovery_task = asyncio.create_task(asyncio.to_thread(recover_pending_material_jobs))
    checkpoint_gc_task = asyncio.create_task(asyncio.to_thread(gc_agent_checkpoints))
    worker_task = asyncio.create_task(material_job_worker(worker_stop))
    yield
    worker_stop.set()
    if not recovery_task.done():
        recovery_task.cancel()
    if not checkpoint_gc_task.done():
        checkpoint_gc_task.cancel()
    if not worker_task.done():
        worker_task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_route_policy()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.add_exception_handler(AppError, app_error_handler)

    @application.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        token = bind_request_id(request_id)
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception(
                "http_request_failed",
                extra={"event": "http_request", "method": request.method, "path": request.url.path},
            )
            raise
        finally:
            duration = perf_counter() - started
            inc_counter(
                "a3_http_requests_total",
                method=request.method,
                status=str(status_code),
            )
            observe(
                "a3_http_request_duration_seconds",
                duration,
                method=request.method,
            )
            logger.info(
                "http_request_completed",
                extra={
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            reset_request_id(token)

    async def database_exception_handler(_: Request, __: Exception):
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "数据库连接失败，请检查 DATABASE_* 配置和数据库迁移状态。",
                500,
            ),
        )

    application.add_exception_handler(pymysql.MySQLError, database_exception_handler)
    application.add_exception_handler(SQLAlchemyError, database_exception_handler)

    if settings.enable_legacy_routes:
        from routers import (
            agent,
            ai,
            evaluations,
            external_resources,
            materials,
            memories,
            plans,
            profiles,
            quizzes,
            resources,
            tasks,
            users,
        )

        for legacy_router in [
            materials.router,
            agent.router,
            evaluations.router,
            external_resources.router,
            plans.router,
            quizzes.router,
            resources.router,
            profiles.router,
            users.router,
            tasks.router,
            ai.router,
            memories.router,
        ]:
            application.include_router(legacy_router, deprecated=True)

    application.include_router(api_router)
    application.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    @application.get("/health/live", tags=["health"])
    async def liveness():
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"])
    def readiness():
        connection = get_conn()
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT 1 AS ok")
            cursor.fetchone()
            schema_status = schema.database_schema_status(connection)
        finally:
            cursor.close()
            connection.close()
        if not schema_status["ready"]:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "reason": "database_schema_outdated",
                    **schema_status,
                },
            )
        return {"status": "ready", **schema_status}

    @application.get("/metrics", include_in_schema=False)
    async def metrics():
        return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")

    @application.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/static/vue/index.html")

    return application


app = create_app()
