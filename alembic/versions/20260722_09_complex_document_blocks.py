"""Add layout-aware material blocks and chunk provenance.

Revision ID: 20260722_09
Revises: 20260719_08
Create Date: 2026-07-22
"""

from app.core.migrations import run_migrations

revision = "20260722_09"
down_revision = "20260719_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations(target_version="0026")


def downgrade() -> None:
    raise RuntimeError("Automatic removal of parsed document provenance is unsafe")
