"""Safety helpers for disposable pytest and browser-test databases."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import pymysql

DATABASE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
STATIC_TEST_DATABASE_NAMES = frozenset({"a3_ci_test", "a3_e2e_test"})
DYNAMIC_TEST_DATABASE_PATTERN = re.compile(
    r"^a3_(?:"
    r"pytest|goal_test|boundary_test|history_test|concurrent_test|alembic_race_test"
    r")_[0-9a-f]{8,32}$"
)


@dataclass(frozen=True)
class DatabaseAdminConfig:
    host: str
    port: int
    user: str
    password: str


def validate_test_database_name(database_name: str) -> str:
    """Allow only this project's known disposable database namespaces."""
    normalized = database_name.strip()
    if not DATABASE_IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(f"Invalid test database identifier: {database_name!r}")
    if (
        normalized not in STATIC_TEST_DATABASE_NAMES
        and not DYNAMIC_TEST_DATABASE_PATTERN.fullmatch(normalized)
    ):
        raise ValueError(
            f"Refusing destructive test operation on non-test database: {normalized}"
        )
    return normalized


def database_admin_config_from_env() -> DatabaseAdminConfig:
    return DatabaseAdminConfig(
        host=os.getenv("DATABASE_HOST", os.getenv("DB_HOST", "127.0.0.1")),
        port=int(os.getenv("DATABASE_PORT", os.getenv("DB_PORT", "3306"))),
        user=os.getenv("DATABASE_USER", os.getenv("DB_USER", "root")),
        password=os.getenv("DATABASE_PASSWORD", os.getenv("DB_PASSWORD", "")),
    )


def _admin_connection(config: DatabaseAdminConfig):
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        charset="utf8mb4",
        autocommit=True,
    )


def create_test_database(
    database_name: str,
    config: DatabaseAdminConfig | None = None,
) -> str:
    safe_name = validate_test_database_name(database_name)
    connection = _admin_connection(config or database_admin_config_from_env())
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{safe_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()
    return safe_name


def drop_test_database(
    database_name: str,
    config: DatabaseAdminConfig | None = None,
) -> None:
    safe_name = validate_test_database_name(database_name)
    connection = _admin_connection(config or database_admin_config_from_env())
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{safe_name}`")
    finally:
        connection.close()
