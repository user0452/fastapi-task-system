"""Add general-chat durable run support after Agent crash-safety baseline.

Revision ID: 20260717_04
Revises: 20260716_03
Create Date: 2026-07-17
"""

from app.core.migrations import run_migrations

revision = "20260717_04"
down_revision = "20260716_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations()


def downgrade() -> None:
    raise RuntimeError("General Agent request idempotency cannot be safely downgraded")
