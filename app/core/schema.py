"""Alembic entry points and runtime schema-readiness checks."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pymysql
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command
from app.core.database import get_conn

ROOT_DIR = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    config = Config(str(ROOT_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT_DIR / "alembic"))
    return config


def upgrade_database(revision: str = "head") -> None:
    command.upgrade(alembic_config(), revision)


@lru_cache(maxsize=1)
def alembic_heads() -> tuple[str, ...]:
    script = ScriptDirectory.from_config(alembic_config())
    return tuple(sorted(script.get_heads()))


def database_schema_status(connection=None) -> dict[str, Any]:
    owns_connection = connection is None
    if connection is None:
        connection = get_conn()
    cursor = connection.cursor()
    try:
        try:
            cursor.execute("SELECT version_num FROM alembic_version")
            current = tuple(sorted(row["version_num"] for row in cursor.fetchall()))
        except pymysql.MySQLError as exc:
            if exc.args and exc.args[0] == 1146:
                current = ()
            else:
                raise
        expected = alembic_heads()
        return {
            "ready": set(current) == set(expected),
            "current_revisions": list(current),
            "expected_revisions": list(expected),
            "current_revision": current[0] if len(current) == 1 else None,
            "expected_revision": expected[0] if len(expected) == 1 else None,
        }
    finally:
        cursor.close()
        if owns_connection:
            connection.close()
