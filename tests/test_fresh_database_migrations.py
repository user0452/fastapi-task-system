from uuid import uuid4

import pymysql

from app.core.config import get_settings
from app.core.migrations import MIGRATIONS, run_migrations


def test_migrations_build_fresh_database_without_touching_existing_data():
    settings = get_settings()
    database_name = f"a3_goal_test_{uuid4().hex[:12]}"
    admin_connection = pymysql.connect(
        host=settings.database_host,
        port=settings.database_port,
        user=settings.database_user,
        password=settings.database_password,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    admin_cursor = admin_connection.cursor()

    try:
        admin_cursor.execute(
            f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        test_connection = pymysql.connect(
            host=settings.database_host,
            port=settings.database_port,
            user=settings.database_user,
            password=settings.database_password,
            database=database_name,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
        try:
            assert run_migrations(test_connection) == [migration.version for migration in MIGRATIONS]
            assert run_migrations(test_connection) == []

            cursor = test_connection.cursor()
            try:
                cursor.execute("SELECT COUNT(*) AS total FROM schema_migrations")
                assert cursor.fetchone()["total"] == len(MIGRATIONS)
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
                cursor.close()
        finally:
            test_connection.close()
    finally:
        admin_cursor.execute(f"DROP DATABASE IF EXISTS `{database_name}`")
        admin_cursor.close()
        admin_connection.close()
