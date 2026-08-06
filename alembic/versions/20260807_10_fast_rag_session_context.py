"""Persist scoped Fast RAG retrieval context.

Revision ID: 20260807_10
Revises: 20260722_09
Create Date: 2026-08-07
"""

from app.core.migrations import run_migrations

revision = "20260807_10"
down_revision = "20260722_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations(target_version="0027")


def downgrade() -> None:
    raise RuntimeError("Automatic removal of session retrieval context is unsafe")
