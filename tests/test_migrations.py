import ast
import os
import subprocess
import sys
from pathlib import Path

from app.core.database import get_conn
from app.core.migrations import (
    MIGRATIONS,
    ROOT_DIR,
    _upgrade_legacy_agent_message_sessions,
    run_migrations,
)

REQUIRED_TABLES = {
    "courses",
    "knowledge_points",
    "mastery_records",
    "mastery_changes",
    "study_plans",
    "study_sessions",
    "study_session_items",
    "chat_sessions",
    "evaluation_answers",
    "course_agents",
    "course_agent_memories",
    "agent_runs",
    "agent_tool_calls",
    "external_resources",
    "resource_interactions",
    "knowledge_point_relations",
    "learning_roadmaps",
    "roadmap_generation_jobs",
    "learning_roadmap_stages",
    "roadmap_stage_points",
    "roadmap_stage_sessions",
    "roadmap_adjustments",
    "course_material_blocks",
    "schema_migrations",
}

ALEMBIC_INTERNAL_TARGETS = {
    "20260716_01_orm_baseline.py": "0017",
    "20260716_02_legacy_bridge.py": "0019",
    "20260716_03_agent_crash_safety.py": "0020",
    "20260717_04_agent_lease_renewal.py": "0021",
    "20260718_05_learning_roadmaps.py": "0022",
    "20260718_06_memory_transparency.py": "0023",
    "20260719_07_two_tier_learning_memory.py": "0024",
    "20260719_08_user_llm_configs.py": "0025",
    "20260722_09_complex_document_blocks.py": "0026",
}


def _alembic_internal_target(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_migrations"
    ]
    assert len(calls) == 1, f"{path.name} must call run_migrations exactly once"

    call = calls[0]
    assert not call.args, f"{path.name} must use an explicit target_version keyword"
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    assert set(keywords) == {"target_version"}, (
        f"{path.name} must only pass a fixed target_version to run_migrations"
    )
    target = keywords["target_version"]
    assert isinstance(target, ast.Constant) and isinstance(target.value, str), (
        f"{path.name} target_version must be a string literal"
    )
    return target.value


def test_migrations_are_idempotent():
    assert run_migrations() == []


def test_expected_migration_versions_are_registered():
    assert [migration.version for migration in MIGRATIONS] == [
        "0001",
        "0002",
        "0003",
        "0004",
        "0005",
        "0006",
        "0007",
        "0008",
        "0009",
        "0010",
        "0011",
        "0012",
        "0013",
        "0014",
        "0015",
        "0016",
        "0017",
        "0018",
        "0019",
        "0020",
        "0021",
        "0022",
        "0023",
        "0024",
        "0025",
        "0026",
    ]


def test_alembic_revisions_have_immutable_internal_targets():
    version_dir = ROOT_DIR / "alembic" / "versions"
    revision_paths = {
        path.name: path for path in version_dir.glob("*.py") if path.name != "__init__.py"
    }
    assert set(revision_paths) == set(ALEMBIC_INTERNAL_TARGETS)

    registered_versions = {migration.version for migration in MIGRATIONS}
    for name, expected_target in ALEMBIC_INTERNAL_TARGETS.items():
        actual_target = _alembic_internal_target(revision_paths[name])
        assert actual_target == expected_target
        assert actual_target in registered_versions


def test_alembic_offline_mode_fails_without_connecting_or_exposing_credentials():
    sentinel_password = "offline-password-must-not-appear"
    environment = os.environ.copy()
    environment["DATABASE_NAME"] = "a3_offline_database_must_not_exist"
    environment["DB_NAME"] = environment["DATABASE_NAME"]
    environment["DATABASE_PASSWORD"] = sentinel_password
    environment["DB_PASSWORD"] = sentinel_password

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT_DIR,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "Offline SQL generation is disabled" in output
    assert "OperationalError" not in output
    assert sentinel_password not in output


def test_required_foundation_tables_exist():
    connection = get_conn()
    cursor = connection.cursor()
    try:
        placeholders = ",".join(["%s"] * len(REQUIRED_TABLES))
        cursor.execute(
            f"""
            SELECT table_name AS name
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name IN ({placeholders})
            """,
            tuple(REQUIRED_TABLES),
        )
        actual = {row["name"] for row in cursor.fetchall()}
    finally:
        cursor.close()
        connection.close()

    assert actual == REQUIRED_TABLES


def test_migration_sources_do_not_drop_tables():
    migration_sources = [
        ROOT_DIR / "app" / "core" / "migrations.py",
        *Path(ROOT_DIR / "sql" / "migrations").glob("*.sql"),
    ]
    for path in migration_sources:
        assert "DROP TABLE" not in path.read_text(encoding="utf-8").upper()


def test_legacy_messages_are_attached_to_one_idempotent_session(two_users):
    user, _ = two_users
    connection = get_conn()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO agent_chat_messages (user_id, role, content)
            VALUES (%s, 'user', '旧问题'), (%s, 'assistant', '旧回答')
            """,
            (user["id"], user["id"]),
        )
        _upgrade_legacy_agent_message_sessions(cursor)
        _upgrade_legacy_agent_message_sessions(cursor)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT session_id) AS sessions,
                   SUM(session_id IS NULL) AS missing
            FROM agent_chat_messages
            WHERE user_id = %s AND content IN ('旧问题', '旧回答')
            """,
            (user["id"],),
        )
        result = cursor.fetchone()
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM chat_sessions
            WHERE user_id = %s AND course_id IS NULL AND title = '历史助手对话'
            """,
            (user["id"],),
        )
        session_count = cursor.fetchone()["total"]
        connection.rollback()
    finally:
        cursor.close()
        connection.close()

    assert result == {"sessions": 1, "missing": 0}
    assert session_count == 1
