"""Adopt the existing application schema as Alembic's ORM baseline.

Revision ID: 20260716_01
Revises:
Create Date: 2026-07-16
"""

revision = "20260716_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``app.core.migrations`` owns the historical schema.  This revision
    # intentionally records the hand-off without rebuilding live tables.
    pass


def downgrade() -> None:
    # A baseline cannot safely remove a schema that may predate Alembic.
    raise RuntimeError("ORM baseline revision cannot be downgraded")
