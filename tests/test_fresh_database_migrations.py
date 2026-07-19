import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pymysql

from app.core.config import get_settings
from app.core.migrations import run_migrations
from app.core.test_database import create_test_database, drop_test_database

ROOT_DIR = Path(__file__).resolve().parents[1]


def _connection(database_name: str):
    settings = get_settings()
    return pymysql.connect(
        host=settings.database_host,
        port=settings.database_port,
        user=settings.database_user,
        password=settings.database_password,
        database=database_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _run_alembic(database_name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_NAME"] = database_name
    environment["DB_NAME"] = database_name
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=ROOT_DIR,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )


def test_alembic_upgrade_head_builds_a_fresh_database():
    database_name = f"a3_goal_test_{uuid4().hex[:12]}"
    create_test_database(database_name)
    try:
        _run_alembic(database_name, "upgrade", "head")
        _run_alembic(database_name, "upgrade", "head")
        connection = _connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                assert cursor.fetchone()["version_num"] == "20260719_08"
                cursor.execute("SELECT COUNT(*) AS total FROM schema_migrations")
                assert cursor.fetchone()["total"] >= 23
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    """,
                    (database_name,),
                )
                assert cursor.fetchone()["total"] >= 24
        finally:
            connection.close()
    finally:
        drop_test_database(database_name)


def test_alembic_upgrades_a_previously_stamped_historical_database():
    database_name = f"a3_history_test_{uuid4().hex[:12]}"
    create_test_database(database_name)
    try:
        connection = _connection(database_name)
        try:
            assert run_migrations(connection, target_version="0017")[-1] == "0017"
        finally:
            connection.close()

        _run_alembic(database_name, "stamp", "20260716_01")
        _run_alembic(database_name, "upgrade", "head")
        _run_alembic(database_name, "upgrade", "head")

        connection = _connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                assert cursor.fetchone()["version_num"] == "20260719_08"
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM schema_migrations "
                    "WHERE version IN "
                    "('0018', '0019', '0020', '0021', '0022', '0023', '0024', '0025')"
                )
                assert cursor.fetchone()["total"] == 8
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                      AND (
                        (table_name = 'users' AND column_name = 'timezone')
                        OR (table_name = 'agent_runs' AND column_name = 'input_hash')
                        OR (table_name = 'agent_tool_calls' AND column_name = 'lease_owner')
                        OR (
                            table_name = 'agent_chat_messages'
                            AND column_name = 'idempotency_key'
                        )
                        OR (
                            table_name = 'course_agent_memories'
                            AND column_name IN ('source_type', 'enabled')
                        )
                      )
                    """
                )
                assert cursor.fetchone()["total"] == 6
                cursor.execute(
                    """
                    SELECT column_name AS name, is_nullable AS nullable
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE() AND table_name = 'agent_runs'
                      AND column_name IN ('agent_id', 'course_id')
                    """
                )
                nullable_columns = {
                    row["name"]: row["nullable"] for row in cursor.fetchall()
                }
                assert nullable_columns == {"agent_id": "YES", "course_id": "YES"}
        finally:
            connection.close()
    finally:
        drop_test_database(database_name)
