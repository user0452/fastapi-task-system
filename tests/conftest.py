from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_cursor
from app.core.migrations import run_migrations
from main import app
from utils import get_current_user


@contextmanager
def _temporary_user():
    username = f"goal_test_{uuid4().hex[:16]}"
    with get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, "test-only-password"),
        )
        user_id = cursor.lastrowid

    try:
        yield {"id": user_id, "username": username}
    finally:
        with get_cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    run_migrations()


@pytest.fixture
def two_users():
    with _temporary_user() as first:
        with _temporary_user() as second:
            yield first, second


@pytest.fixture
def api_client(two_users):
    first, _ = two_users
    app.dependency_overrides[get_current_user] = lambda: first
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
