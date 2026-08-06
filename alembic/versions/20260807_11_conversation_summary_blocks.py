"""Add durable incremental conversation summary blocks.

Revision ID: 20260807_11
Revises: 20260807_10
Create Date: 2026-08-07
"""

from app.core.migrations import run_migrations

revision = "20260807_11"
down_revision = "20260807_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations(target_version="0028")


def downgrade() -> None:
    raise RuntimeError("Automatic removal of conversation summaries is unsafe")
