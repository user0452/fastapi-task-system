"""Add durable Agent request, tool, and resume-message coordination.

Revision ID: 20260716_03
Revises: 20260716_02
Create Date: 2026-07-16
"""

from app.core.migrations import run_migrations

revision = "20260716_03"
down_revision = "20260716_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_migrations()


def downgrade() -> None:
    raise RuntimeError("Durable Agent coordination cannot be safely downgraded")
