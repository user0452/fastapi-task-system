"""Rebuild stale course-material indexes for one user, sequentially.

Usage:
    python -m scripts.reindex_user_materials stringo
"""

from __future__ import annotations

import argparse

from app.core.database import get_cursor
from app.integrations.embedding.chunking import CHUNKER_VERSION
from app.modules.materials.service import process_material


def stale_materials(username: str) -> tuple[int, list[dict]]:
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user is None:
            raise SystemExit(f"user not found: {username}")
        cursor.execute(
            """
            SELECT id, title
            FROM course_materials
            WHERE user_id = %s AND COALESCE(chunker_version, '') <> %s
            ORDER BY id
            """,
            (user["id"], CHUNKER_VERSION),
        )
        return int(user["id"]), list(cursor.fetchall())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    args = parser.parse_args()
    user_id, materials = stale_materials(args.username)
    for index, material in enumerate(materials, start=1):
        print(
            f"[{index}/{len(materials)}] reindex material_id={material['id']}",
            flush=True,
        )
        result = process_material(user_id, int(material["id"]))
        print(
            f"material_id={material['id']} chunks={result['chunk_count']} "
            f"objectives={result.get('learning_objective_count', 0)}",
            flush=True,
        )
    print(f"completed={len(materials)} version={CHUNKER_VERSION}", flush=True)


if __name__ == "__main__":
    main()
