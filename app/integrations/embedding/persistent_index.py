"""Disk-backed FAISS candidate index for course material retrieval."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

import numpy as np

from app.integrations.embedding.service import deserialize_embedding

ROOT_DIR = Path(__file__).resolve().parents[3]
INDEX_ROOT = Path(os.getenv("RAG_INDEX_DIR", ROOT_DIR / "var" / "rag_indexes")).resolve()
_LOCK = RLock()
_CACHE: dict[str, tuple[int, object]] = {}
INDEX_FORMAT_VERSION = 1


def _index_path(user_id: int, course_id: int) -> Path:
    return INDEX_ROOT / str(int(user_id)) / f"course-{int(course_id)}.faiss"


def _metadata_path(user_id: int, course_id: int) -> Path:
    return _index_path(user_id, course_id).with_suffix(".json")


def _read_metadata(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def rebuild_course_vector_index(
    user_id: int,
    course_id: int,
    rows: list[dict],
    *,
    embedding_model: str,
    generation: int,
) -> int:
    """Atomically replace one course index using already-persisted embeddings."""
    import faiss

    vectors: list[np.ndarray] = []
    ids: list[int] = []
    dimension = 0
    for row in rows:
        value = row.get("embedding_json")
        if not value:
            continue
        try:
            vector = deserialize_embedding(value).astype("float32")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if vector.ndim != 1 or not vector.size:
            continue
        if not dimension:
            dimension = int(vector.size)
        if vector.shape != (dimension,):
            continue
        vectors.append(vector)
        ids.append(int(row["id"]))

    target = _index_path(user_id, course_id)
    metadata = _metadata_path(user_id, course_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        current_metadata = _read_metadata(metadata)
        current_generation = int(current_metadata.get("generation") or 0)
        if current_generation > int(generation):
            return int(current_metadata.get("count") or 0)
        if not vectors:
            target.unlink(missing_ok=True)
            meta_temp = metadata.with_name(f"{metadata.name}.{uuid4().hex}.tmp")
            try:
                meta_temp.write_text(
                    json.dumps(
                        {
                            "user_id": int(user_id),
                            "course_id": int(course_id),
                            "embedding_model": embedding_model,
                            "dimension": 0,
                            "count": 0,
                            "generation": int(generation),
                            "index_version": INDEX_FORMAT_VERSION,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                os.replace(meta_temp, metadata)
            finally:
                meta_temp.unlink(missing_ok=True)
            _CACHE.pop(str(target), None)
            return 0
        matrix = np.vstack(vectors).astype("float32")
        faiss.normalize_L2(matrix)
        index = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
        index.add_with_ids(matrix, np.asarray(ids, dtype="int64"))
        temp = target.with_name(f"{target.name}.{uuid4().hex}.tmp")
        meta_temp = metadata.with_name(f"{metadata.name}.{uuid4().hex}.tmp")
        try:
            faiss.write_index(index, str(temp))
            meta_temp.write_text(
                json.dumps(
                    {
                        "user_id": int(user_id),
                        "course_id": int(course_id),
                        "embedding_model": embedding_model,
                        "dimension": dimension,
                        "count": len(ids),
                        "generation": int(generation),
                        "index_version": INDEX_FORMAT_VERSION,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.replace(temp, target)
            os.replace(meta_temp, metadata)
        finally:
            temp.unlink(missing_ok=True)
            meta_temp.unlink(missing_ok=True)
        _CACHE.pop(str(target), None)
    return len(ids)


def _load_index(path: Path):
    import faiss

    modified = path.stat().st_mtime_ns
    key = str(path)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] == modified:
            return cached[1]
        index = faiss.read_index(str(path))
        _CACHE[key] = (modified, index)
        return index


def vector_candidates(
    user_id: int,
    course_id: int,
    query_embeddings: np.ndarray,
    limit: int,
) -> list[tuple[int, float]]:
    path = _index_path(user_id, course_id)
    if not path.exists() or limit <= 0:
        return []
    matrix = np.asarray(query_embeddings, dtype="float32")
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    try:
        index = _load_index(path)
        if matrix.shape[1] != index.d:
            return []
        import faiss

        faiss.normalize_L2(matrix)
        scores, ids = index.search(matrix, int(limit))
    except (OSError, RuntimeError, ValueError):
        return []
    best: dict[int, float] = {}
    for score_row, id_row in zip(scores, ids):
        for score, chunk_id in zip(score_row, id_row):
            if int(chunk_id) < 0:
                continue
            best[int(chunk_id)] = max(best.get(int(chunk_id), -1.0), float(score))
    return sorted(best.items(), key=lambda item: (item[1], -item[0]), reverse=True)


def remove_course_vector_index(user_id: int, course_id: int) -> None:
    path = _index_path(user_id, course_id)
    with _LOCK:
        path.unlink(missing_ok=True)
        _metadata_path(user_id, course_id).unlink(missing_ok=True)
        _CACHE.pop(str(path), None)


__all__ = [
    "rebuild_course_vector_index",
    "remove_course_vector_index",
    "vector_candidates",
]
