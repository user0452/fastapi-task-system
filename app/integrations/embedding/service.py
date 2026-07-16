"""Local embedding model and vector serialization boundary."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from threading import Lock

import numpy as np

USE_MOCK_EMBEDDING = os.getenv("A3_MOCK_EMBEDDING", "false").strip().lower() in {
    "1", "true", "yes", "on",
}
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
)
if USE_MOCK_EMBEDDING:
    EMBEDDING_MODEL_NAME = "mock-deterministic-384"
_model = None
_model_lock = Lock()


def get_embedding_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def _mock_embedding(text: str) -> np.ndarray:
    source = np.frombuffer((text or " ").encode("utf-8"), dtype=np.uint8)
    if source.size == 0:
        source = np.ones(1, dtype=np.uint8)
    row = np.resize(source.astype("float32") + 1.0, 384)
    row += (np.arange(384, dtype="float32") % 17) + 1.0
    row -= row.mean()
    return row / (float(np.linalg.norm(row)) or 1.0)


@lru_cache(maxsize=512)
def _get_single_embedding(text: str) -> np.ndarray:
    if USE_MOCK_EMBEDDING:
        return _mock_embedding(text)
    return get_embedding_model().encode(
        [text], convert_to_numpy=True, normalize_embeddings=True
    )[0]


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype="float32")
    if len(texts) == 1:
        return np.vstack([_get_single_embedding(texts[0])]).astype("float32")
    if USE_MOCK_EMBEDDING:
        return np.vstack([_mock_embedding(text) for text in texts]).astype("float32")
    return get_embedding_model().encode(
        texts,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")


def serialize_embedding(embedding: np.ndarray) -> str:
    return json.dumps(np.asarray(embedding, dtype="float32").tolist())


def deserialize_embedding(value: str) -> np.ndarray:
    return np.asarray(json.loads(value), dtype="float32")


def split_text_to_chunks(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    value = (text or "").strip()
    if not value:
        return []
    chunks = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(value):
        chunk = value[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def search_similar_chunks(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    if not query or not chunks:
        return []
    if all(item.get("embedding_json") for item in chunks):
        vectors = np.vstack([deserialize_embedding(item["embedding_json"]) for item in chunks])
    else:
        vectors = embed_texts([item["chunk_text"] for item in chunks])
    query_vector = embed_texts([query])[0]
    scores = vectors @ query_vector
    indices = np.argsort(scores)[::-1][: min(top_k, len(chunks))]
    return [{**chunks[int(index)], "score": float(scores[int(index)])} for index in indices]


__all__ = [
    "EMBEDDING_MODEL_NAME", "USE_MOCK_EMBEDDING", "deserialize_embedding",
    "embed_texts", "get_embedding_model", "search_similar_chunks", "serialize_embedding",
    "split_text_to_chunks",
]
