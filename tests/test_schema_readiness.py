import pytest

from app.core import schema
from app.core.test_database import validate_test_database_name


def test_readiness_reports_current_alembic_head(api_client):
    response = api_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["current_revisions"] == list(schema.alembic_heads())


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


def test_destructive_database_guard_requires_test_marker():
    assert validate_test_database_name("a3_pytest_1234") == "a3_pytest_1234"
    assert validate_test_database_name("a3_e2e_test") == "a3_e2e_test"

    with pytest.raises(ValueError, match="non-test database"):
        validate_test_database_name("task_db2")
