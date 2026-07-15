import numpy as np

from app.integrations.embedding.hybrid_search import (
    _coverage_rerank,
    build_query_variants,
    hybrid_search,
)
from services.rag_service import serialize_embedding


def test_query_variants_keep_question_and_extract_quoted_scenario():
    query = '在“backup reports success but restore fails” scenario, how should this be handled?'

    variants = build_query_variants(query)

    assert variants[0] == query
    assert "backup reports success but restore fails" in variants
    assert len(variants) == len(set(variants))


def test_coverage_rerank_avoids_duplicate_kb_evidence_before_new_evidence():
    ranked = [
        {"id": 1, "kb_ids": ["YQ-A"], "score": 0.92, "keyword_score": 0.9, "dense_score": 0.9},
        {"id": 2, "kb_ids": ["YQ-A"], "score": 0.88, "keyword_score": 0.88, "dense_score": 0.88},
        {"id": 3, "kb_ids": ["YQ-B"], "score": 0.76, "keyword_score": 0.76, "dense_score": 0.76},
    ]

    selected = _coverage_rerank(ranked, top_k=2)

    assert [item["id"] for item in selected] == [1, 3]
    assert selected[1]["evidence_overlap"] == 0
    assert selected[1]["coverage_penalty"] == 0.0


def test_hybrid_search_batches_focused_query_with_original_question():
    requested = []

    def embeddings(texts):
        requested.append(list(texts))
        return np.tile(np.array([[1.0, 0.0]], dtype="float32"), (len(texts), 1))

    chunks = [
        {
            "id": 1,
            "material_title": "Runbook",
            "heading_path": "Recovery",
            "kb_ids": ["YQ-DR-002"],
            "chunk_text": "Backup success requires restore verification.",
            "embedding_json": serialize_embedding(np.array([1.0, 0.0], dtype="float32")),
        }
    ]
    query = 'In “backup reports success but restore fails” scenario, how should this be handled?'

    results = hybrid_search(
        query,
        chunks,
        [],
        top_k=1,
        embedding_provider=embeddings,
        enable_multi_query=True,
    )

    assert results[0]["kb_ids"] == ["YQ-DR-002"]
    assert requested == [[query, "backup reports success but restore fails"]]
    assert results[0]["focused_query_matches"] == 2
