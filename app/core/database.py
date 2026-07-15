from contextlib import contextmanager
from time import perf_counter

import pymysql

from app.core.config import get_settings
from app.core.metrics import add_gauge, inc_counter, observe, set_gauge

_pool = None


def _database_config() -> dict:
    settings = get_settings()
    return {
        "host": settings.database_host,
        "port": settings.database_port,
        "user": settings.database_user,
        "password": settings.database_password,
        "database": settings.database_name,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }


def _get_pool():
    global _pool
    if _pool is None:
        try:
            from dbutils.pooled_db import PooledDB

            _pool = PooledDB(
                creator=pymysql,
                maxconnections=20,
                mincached=2,
                maxcached=5,
                blocking=True,
                ping=1,
                **_database_config(),
            )
            set_gauge("a3_db_pool_capacity", 20)
        except ImportError:
            _pool = "fallback"
    return _pool


def get_conn():
    """Return a pooled database connection when DBUtils is available."""
    pool = _get_pool()
    if pool == "fallback":
        return pymysql.connect(**_database_config())
    return pool.connection()


@contextmanager
def get_cursor():
    """Provide a short transaction boundary and always release resources."""
    started = perf_counter()
    add_gauge("a3_db_pool_in_use", 1)
    connection = None
    cursor = None
    try:
        connection = get_conn()
        # DBUtils only disables transparent reconnects after an explicit begin().
        # Without it, a reconnect can silently discard writes made with autocommit off.
        connection.begin()
        cursor = connection.cursor()
        yield cursor
        connection.commit()
    except Exception:
        inc_counter("a3_db_transactions_total", status="failed")
        if connection is not None:
            connection.rollback()
        raise
    else:
        inc_counter("a3_db_transactions_total", status="committed")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
        add_gauge("a3_db_pool_in_use", -1)
        observe("a3_db_transaction_duration_seconds", perf_counter() - started)


__all__ = ["get_conn", "get_cursor"]
