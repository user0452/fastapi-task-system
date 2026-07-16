"""Lazy ORM mappings for established tables that are being migrated.

The project already has a versioned production schema.  Reflection lets the
remaining repositories use mapped SQLAlchemy entities immediately, without a
second hand-maintained copy of every legacy table definition.  New tables
should use explicit models like :class:`app.models.Course`.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from sqlalchemy.ext.automap import AutomapBase, automap_base

from app.core.orm import get_engine

_base: AutomapBase | None = None
_lock = Lock()


def _classname_for_table(_: AutomapBase, tablename: str, __) -> str:
    return tablename


def reflected_base() -> AutomapBase:
    global _base
    if _base is None:
        with _lock:
            if _base is None:
                base = automap_base()
                base.prepare(
                    autoload_with=get_engine(),
                    classname_for_table=_classname_for_table,
                )
                _base = base
    return _base


def reflected_model(table_name: str) -> type[Any]:
    """Return the SQLAlchemy-mapped class for an existing table."""
    try:
        return reflected_base().classes[table_name]
    except KeyError as exc:
        raise RuntimeError(f"未找到可映射的数据表：{table_name}") from exc


def clear_reflected_models() -> None:
    """Allow a migration in the same process to refresh reflected metadata."""
    global _base
    with _lock:
        _base = None
