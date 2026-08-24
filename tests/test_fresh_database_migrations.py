import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pymysql

from app.core.config import get_settings
from app.core.migrations import MIGRATIONS, run_migrations
from app.core.test_database import create_test_database, drop_test_database

ROOT_DIR = Path(__file__).resolve().parents[1]

ALEMBIC_INTERNAL_BOUNDARIES = [
    ("20260716_01", "0017"),
    ("20260716_02", "0019"),
    ("20260716_03", "0020"),
    ("20260717_04", "0021"),
    ("20260718_05", "0022"),
    ("20260718_06", "0023"),
    ("20260719_07", "0024"),
    ("20260719_08", "0025"),
    ("20260722_09", "0026"),
    ("20260807_10", "0027"),
    ("20260807_11", "0028"),
]

ADAPTIVE_TABLES = {
    "curriculum_builds",
    "learning_objectives",
    "objective_relations",
    "objective_evidence",
    "questions",
    "question_objectives",
    "learning_actions",
    "question_attempts",
    "learning_evidence",
    "student_objective_states",
    "misconceptions",
}


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
                assert cursor.fetchone()["version_num"] == "20260825_12"
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
                cursor.execute(
                    "SELECT table_name AS name FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name IN (" +
                    ",".join(["%s"] * len(ADAPTIVE_TABLES)) + ")",
                    (database_name, *sorted(ADAPTIVE_TABLES)),
                )
                assert {row["name"] for row in cursor.fetchall()} == ADAPTIVE_TABLES
        finally:
            connection.close()
    finally:
        drop_test_database(database_name)


def test_each_alembic_revision_stops_at_its_internal_migration_boundary():
    database_name = f"a3_boundary_test_{uuid4().hex[:12]}"
    create_test_database(database_name)
    try:
        migration_versions = [migration.version for migration in MIGRATIONS]
        for alembic_revision, internal_target in ALEMBIC_INTERNAL_BOUNDARIES:
            _run_alembic(database_name, "upgrade", alembic_revision)
            target_index = migration_versions.index(internal_target)
            expected_versions = set(migration_versions[: target_index + 1])

            connection = _connection(database_name)
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT version_num FROM alembic_version")
                    assert cursor.fetchone()["version_num"] == alembic_revision
                    cursor.execute("SELECT version FROM schema_migrations")
                    actual_versions = {row["version"] for row in cursor.fetchall()}
                    assert actual_versions == expected_versions
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
                assert cursor.fetchone()["version_num"] == "20260825_12"
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM schema_migrations "
                    "WHERE version IN "
                    "('0018', '0019', '0020', '0021', '0022', '0023', '0024', '0025', '0026')"
                )
                assert cursor.fetchone()["total"] == 9
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


def test_internal_migration_runner_serializes_concurrent_deployments():
    database_name = f"a3_concurrent_test_{uuid4().hex[:12]}"
    create_test_database(database_name)
    barrier = Barrier(2)

    def migrate() -> list[str]:
        connection = _connection(database_name)
        try:
            barrier.wait(timeout=10)
            return run_migrations(connection, target_version="0017")
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: migrate(), range(2)))

        assert sorted(len(result) for result in results) == [0, 17]
        connection = _connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
                assert [row["version"] for row in cursor.fetchall()] == [
                    migration.version for migration in MIGRATIONS[:17]
                ]
        finally:
            connection.close()
    finally:
        drop_test_database(database_name)


def test_alembic_serializes_concurrent_upgrade_processes():
    database_name = f"a3_alembic_race_test_{uuid4().hex[:10]}"
    create_test_database(database_name)
    barrier = Barrier(2)

    def upgrade() -> subprocess.CompletedProcess[str]:
        barrier.wait(timeout=10)
        environment = os.environ.copy()
        environment["DATABASE_NAME"] = database_name
        environment["DB_NAME"] = database_name
        return subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT_DIR,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: upgrade(), range(2)))

        failures = [
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            for result in results
            if result.returncode != 0
        ]
        assert not failures, "\n\n".join(failures)

        connection = _connection(database_name)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                assert cursor.fetchone()["version_num"] == "20260825_12"
                cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
                assert [row["version"] for row in cursor.fetchall()] == [
                    migration.version for migration in MIGRATIONS
                ]
        finally:
            connection.close()
    finally:
        drop_test_database(database_name)
