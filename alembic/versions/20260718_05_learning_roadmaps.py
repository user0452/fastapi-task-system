"""Add durable staged learning roadmaps.

Revision ID: 20260718_05
Revises: 20260717_04
Create Date: 2026-07-18
"""

from app.core.migrations import run_migrations

revision = "20260718_05"
down_revision = "20260717_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations()


def downgrade() -> None:
    raise RuntimeError("Learning roadmap history cannot be safely downgraded")
