"""Adopt the existing application schema as Alembic's ORM baseline.

Revision ID: 20260716_01
Revises:
Create Date: 2026-07-16
"""

from app.core.migrations import run_migrations

revision = "20260716_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This makes ``alembic upgrade head`` sufficient for both an empty
    # database and an un-stamped historical installation.
    run_migrations()


def downgrade() -> None:
    # A baseline cannot safely remove a schema that may predate Alembic.
    raise RuntimeError("ORM baseline revision cannot be downgraded")
