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
    "schema_migrations",
}


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
    ]


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
