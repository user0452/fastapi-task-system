"""Database entry points.

Runtime code obtains a SQLAlchemy-backed cursor transaction from this module.
``get_conn`` remains only for the schema-migration runner, whose DDL is
intentionally expressed as raw SQL.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pymysql

from app.core.config import get_settings
from app.core.orm import SqlAlchemyCursor, get_engine, get_session


class _MigrationConnection:
    """Expose the historic dictionary cursor only to the DDL migration runner."""

    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return self._connection.cursor(pymysql.cursors.DictCursor)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def get_conn():
    """Return a pooled DB-API connection for schema migrations only."""
    return _MigrationConnection(get_engine().raw_connection())


def get_dedicated_conn(
    *,
    autocommit: bool = True,
    connect_timeout: int = 5,
    read_timeout: int = 10,
    write_timeout: int = 10,
) -> pymysql.connections.Connection:
    """Open a bounded control connection without consuming the application pool."""
    settings = get_settings()
    return pymysql.connect(
        host=settings.database_host,
        port=settings.database_port,
        user=settings.database_user,
        password=settings.database_password,
        database=settings.database_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=autocommit,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
        init_command="SET time_zone = '+00:00'",
    )


@contextmanager
def get_cursor() -> Iterator[SqlAlchemyCursor]:
    """Compatibility boundary for repositories during the ORM migration."""
    with get_session() as session:
        yield SqlAlchemyCursor(session)


__all__ = ["get_conn", "get_cursor", "get_dedicated_conn"]
