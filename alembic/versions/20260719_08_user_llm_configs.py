"""Add per-user OpenAI-compatible model configuration.

Revision ID: 20260719_08
Revises: 20260719_07
Create Date: 2026-07-19
"""

from app.core.migrations import run_migrations

revision = "20260719_08"
down_revision = "20260719_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations()


def downgrade() -> None:
    raise RuntimeError("Automatic removal of encrypted user model configuration is unsafe")
