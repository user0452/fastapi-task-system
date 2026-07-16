"""Course aggregate ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The users table is still represented by the legacy authentication layer.
    # Keep the database FK without forcing an incomplete Python relationship.
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    goal: Mapped[str] = mapped_column(String(500), nullable=False, server_default=text("''"))
    exam_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    daily_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'draft'"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    )
