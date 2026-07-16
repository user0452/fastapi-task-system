"""Declarative base and serialisation helpers for SQLAlchemy models."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def model_as_dict(instance: Any) -> dict[str, Any]:
    """Return mapped column values without leaking SQLAlchemy internals."""
    mapper = inspect(instance).mapper
    return {attribute.key: getattr(instance, attribute.key) for attribute in mapper.column_attrs}
