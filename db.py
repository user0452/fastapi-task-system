"""Compatibility imports for legacy modules.

New code should import from `app.core.database`.
"""

from app.core.database import get_conn, get_cursor

__all__ = ["get_conn", "get_cursor"]
