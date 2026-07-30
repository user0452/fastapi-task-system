"""Bring previously stamped databases through the historical migration runner.

Revision ID: 20260716_02
Revises: 20260716_01
Create Date: 2026-07-16
"""

from app.core.migrations import run_migrations

revision = "20260716_02"
down_revision = "20260716_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations(target_version="0019")


def downgrade() -> None:
    raise RuntimeError("The historical migration bridge cannot be safely downgraded")
