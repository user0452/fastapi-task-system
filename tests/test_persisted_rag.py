import numpy as np

from app.integrations.embedding import service as rag_service


def test_persisted_chunk_vectors_only_embed_the_query(monkeypatch):
    calls = []

    def fake_embed(texts):
        calls.append(list(texts))
        return np.asarray([[1.0, 0.0]], dtype="float32")

    monkeypatch.setattr(rag_service, "embed_texts", fake_embed)
    chunks = [
        {
            "id": 1,
            "chunk_text": "等价类划分",
            "embedding_json": "[1.0, 0.0]",
        },
        {
            "id": 2,
            "chunk_text": "边界值分析",
            "embedding_json": "[0.0, 1.0]",
        },
    ]

    results = rag_service.search_similar_chunks("查询", chunks, top_k=2)

    assert calls == [["查询"]]
    assert results[0]["id"] == 1
    assert results[0]["score"] > results[1]["score"]


def test_mock_embeddings_are_deterministic_normalized_and_384_dimensional(monkeypatch):
    monkeypatch.setattr(rag_service, "USE_MOCK_EMBEDDING", True)

    first = rag_service.embed_texts(["等价类划分", "边界值分析"])
    second = rag_service.embed_texts(["等价类划分", "边界值分析"])

    assert first.shape == (2, 384)
    assert np.allclose(first, second)
    assert np.allclose(np.linalg.norm(first, axis=1), np.ones(2))
