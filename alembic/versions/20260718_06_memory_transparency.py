"""Add transparent, user-controlled course memories.

Revision ID: 20260718_06
Revises: 20260718_05
Create Date: 2026-07-18
"""

from app.core.migrations import run_migrations

revision = "20260718_06"
down_revision = "20260718_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations(target_version="0023")


def downgrade() -> None:
    raise RuntimeError("Course memory audit history cannot be safely downgraded")
