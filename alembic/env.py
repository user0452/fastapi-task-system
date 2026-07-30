"""Alembic environment for the complete application schema history."""

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.migrations import (
    MIGRATION_LOCK_TIMEOUT_SECONDS,
    migration_lock_name,
)
from app.core.orm import database_url
from app.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    raise RuntimeError(
        "Offline SQL generation is disabled: revisions execute the internal "
        "migration runner and must only run against an explicitly configured database"
    )


def run_migrations_online() -> None:
    connectable = create_engine(
        database_url(),
        connect_args={"init_command": "SET time_zone = '+00:00'"},
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        database_name = str(
            connection.exec_driver_sql("SELECT DATABASE()").scalar_one_or_none() or ""
        ).strip()
        if not database_name:
            raise RuntimeError("无法确定 Alembic 迁移目标数据库")
        lock_name = migration_lock_name(database_name, "alembic-upgrade")
        acquired = connection.exec_driver_sql(
            "SELECT GET_LOCK(%s, %s)",
            (lock_name, MIGRATION_LOCK_TIMEOUT_SECONDS),
        ).scalar_one_or_none()
        connection.commit()
        if int(acquired or 0) != 1:
            raise RuntimeError(
                f"等待 Alembic 迁移锁超时（{MIGRATION_LOCK_TIMEOUT_SECONDS} 秒）"
            )

        migration_failed = False
        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            if connection.in_transaction():
                connection.commit()
        except BaseException:
            migration_failed = True
            if connection.in_transaction():
                connection.rollback()
            raise
        finally:
            release_error: Exception | None = None
            try:
                released = connection.exec_driver_sql(
                    "SELECT RELEASE_LOCK(%s)",
                    (lock_name,),
                ).scalar_one_or_none()
                connection.commit()
                if int(released or 0) != 1:
                    raise RuntimeError("Alembic 迁移锁释放失败")
            except Exception as exc:
                release_error = exc
            if release_error is not None and not migration_failed:
                raise RuntimeError("Alembic 迁移锁释放失败") from release_error


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
