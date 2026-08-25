# ruff: noqa: E402

import atexit
import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from dotenv import load_dotenv

from app.core.test_database import (
    create_test_database,
    database_admin_config_from_env,
    drop_test_database,
)

load_dotenv()

TEST_DATABASE_NAME = os.getenv("A3_TEST_DATABASE_NAME") or f"a3_pytest_{uuid4().hex}"
os.environ["APP_ENV"] = "test"
os.environ["A3_MOCK_LLM"] = "true"
os.environ["A3_MOCK_EMBEDDING"] = "true"
os.environ["DATABASE_NAME"] = TEST_DATABASE_NAME
os.environ["DB_NAME"] = TEST_DATABASE_NAME

TEST_DATABASE_ADMIN = database_admin_config_from_env()
create_test_database(TEST_DATABASE_NAME, TEST_DATABASE_ADMIN)

from fastapi.testclient import TestClient

from app.core.database import get_cursor
from app.core.orm import dispose_engine
from app.core.schema import upgrade_database
from app.models.reflection import clear_reflected_models
from app.modules.auth.dependencies import get_current_user
from main import app

_database_cleaned = False


def _cleanup_test_database() -> None:
    global _database_cleaned
    if _database_cleaned:
        return
    clear_reflected_models()
    dispose_engine()
    drop_test_database(TEST_DATABASE_NAME, TEST_DATABASE_ADMIN)
    _database_cleaned = True


atexit.register(_cleanup_test_database)


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
    try:
        upgrade_database()
        yield
    finally:
        _cleanup_test_database()


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
