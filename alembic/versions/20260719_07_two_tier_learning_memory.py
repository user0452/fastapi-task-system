"""Add durable two-tier learning memory.

Revision ID: 20260719_07
Revises: 20260718_06
Create Date: 2026-07-19
"""

from app.core.migrations import run_migrations

revision = "20260719_07"
down_revision = "20260718_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations(target_version="0024")


def downgrade() -> None:
    raise RuntimeError("Automatic learning memory cannot be safely downgraded")
