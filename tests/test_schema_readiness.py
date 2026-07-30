import pytest

from app.core import schema
from app.core.database import get_conn
from app.core.migrations import MIGRATIONS
from app.core.test_database import validate_test_database_name


def test_readiness_reports_current_alembic_head(api_client):
    response = api_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["current_revisions"] == list(schema.alembic_heads())
    assert response.json()["current_internal_migrations"] == [
        migration.version for migration in MIGRATIONS
    ]


def test_readiness_requires_the_internal_migration_history():
    connection = get_conn()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "DELETE FROM schema_migrations WHERE version = %s",
            (MIGRATIONS[-1].version,),
        )

        status = schema.database_schema_status(connection)

        assert status["ready"] is False
        assert status["current_revisions"] == list(schema.alembic_heads())
        assert status["expected_internal_migration"] == MIGRATIONS[-1].version
        assert MIGRATIONS[-1].version not in status["current_internal_migrations"]
    finally:
        connection.rollback()
        cursor.close()
        connection.close()


def test_readiness_rejects_stale_schema(api_client, monkeypatch):
    monkeypatch.setattr(
        schema,
        "database_schema_status",
        lambda _connection: {
            "ready": False,
            "current_revisions": ["old_revision"],
            "expected_revisions": ["new_revision"],
            "current_revision": "old_revision",
            "expected_revision": "new_revision",
        },
    )

    response = api_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["reason"] == "database_schema_outdated"


@pytest.mark.parametrize(
    "database_name",
    [
        "a3_ci_test",
        "a3_e2e_test",
        "a3_pytest_01234567",
        "a3_goal_test_0123456789ab",
        "a3_boundary_test_0123456789ab",
        "a3_history_test_0123456789ab",
        "a3_concurrent_test_0123456789ab",
        "a3_alembic_race_test_0123456789",
    ],
)
def test_destructive_database_guard_accepts_project_test_databases(
    database_name,
):
    assert validate_test_database_name(database_name) == database_name


@pytest.mark.parametrize(
    "database_name",
    [
        "task_db2",
        "customer_test_data",
        "a3_customer_test_data",
        "a3_ci_test_backup",
        "a3_pytest_production",
        "A3_E2E_TEST",
    ],
)
def test_destructive_database_guard_rejects_non_project_databases(database_name):
    with pytest.raises(ValueError, match="non-test database"):
        validate_test_database_name(database_name)


def test_destructive_database_guard_rejects_invalid_identifier():
    with pytest.raises(ValueError, match="Invalid test database identifier"):
        validate_test_database_name("a3_ci_test; DROP DATABASE production")
