"""SQLAlchemy engine, transaction scope, and legacy cursor compatibility.

The application is migrating from direct PyMySQL cursor calls to SQLAlchemy's
synchronous ORM.  ``SqlAlchemyCursor`` keeps the transaction boundary stable
while repositories are converted incrementally: ORM and the remaining
parameterised driver SQL can safely participate in one transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Any, Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, CursorResult, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.metrics import add_gauge, inc_counter, observe, set_gauge

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def database_url() -> URL:
    """Build the driver URL without exposing credentials in logs."""
    settings = get_settings()
    return URL.create(
        "mysql+pymysql",
        username=settings.database_user,
        password=settings.database_password,
        host=settings.database_host,
        port=settings.database_port,
        database=settings.database_name,
        query={"charset": "utf8mb4"},
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            database_url(),
            connect_args={"init_command": "SET time_zone = '+00:00'"},
            pool_size=5,
            max_overflow=15,
            pool_timeout=30,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        set_gauge("a3_db_pool_capacity", 20)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def dispose_engine() -> None:
    """Release pooled connections so a disposable test database can be dropped."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def get_session() -> Iterator[Session]:
    """Provide one synchronous ORM transaction per application operation."""
    started = perf_counter()
    add_gauge("a3_db_pool_in_use", 1)
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        inc_counter("a3_db_transactions_total", status="failed")
        session.rollback()
        raise
    else:
        inc_counter("a3_db_transactions_total", status="committed")
    finally:
        session.close()
        add_gauge("a3_db_pool_in_use", -1)
        observe("a3_db_transaction_duration_seconds", perf_counter() - started)


class SqlAlchemyCursor:
    """PyMySQL-shaped adapter backed by a SQLAlchemy ``Session``.

    New repository code should use ``cursor.session`` and SQLAlchemy's ORM
    expressions.  This adapter is intentionally limited to the legacy code
    path and will disappear once the remaining complex RAG repositories are
    converted.
    """

    def __init__(self, session: Session):
        self.session = session
        self._result: CursorResult[Any] | None = None

    @staticmethod
    def _parameters(params: Any) -> Any:
        if params is None:
            return None
        if isinstance(params, list):
            return tuple(params)
        return params

    def execute(self, statement: str, params: Any = None) -> "SqlAlchemyCursor":
        self._result = self.session.connection().exec_driver_sql(
            statement,
            self._parameters(params),
        )
        return self

    def executemany(self, statement: str, params: list[Any]) -> "SqlAlchemyCursor":
        self._result = self.session.connection().exec_driver_sql(statement, params)
        return self

    @property
    def lastrowid(self) -> int | None:
        return self._result.lastrowid if self._result is not None else None

    @property
    def rowcount(self) -> int:
        return self._result.rowcount if self._result is not None else 0

    def fetchone(self) -> dict[str, Any] | None:
        if self._result is None or not self._result.returns_rows:
            return None
        row = self._result.mappings().first()
        return dict(row) if row is not None else None

    def fetchall(self) -> list[dict[str, Any]]:
        if self._result is None or not self._result.returns_rows:
            return []
        return [dict(row) for row in self._result.mappings().all()]
