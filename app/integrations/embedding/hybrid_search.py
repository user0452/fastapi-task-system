import math
import os
import re
from collections import Counter
from functools import lru_cache

import numpy as np

from app.integrations.embedding.service import deserialize_embedding, embed_texts

ASCII_WORD = re.compile(r"[a-zA-Z0-9_]+")
CHINESE_RUN = re.compile(r"[\u4e00-\u9fff]+")
RETRIEVER_VERSION = "persistent-dense-bm25-rrf-rerank-v3"
RERANKER_VERSION = "lexical-semantic-v1"
RRF_K = 60
RRF_WEIGHTS = {"dense": 1.0, "keyword": 1.0, "knowledge": 0.35}
FOCUSED_QUERY_WEIGHT = 0.65
COVERAGE_DUPLICATE_PENALTY = 0.18
MAX_QUERY_VARIANTS = 3
QUOTED_SPAN = re.compile(r"[\"'“‘]([^\"'”’]{4,120})[\"'”’]")
SCENARIO_SPAN = re.compile(
    r"(?:在|当|若|如果)\s*(.{4,120}?)(?:情景下|场景下|情况下|时)"
)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_ENABLE_MULTI_QUERY = _env_flag("RAG_ENABLE_MULTI_QUERY", False)
DEFAULT_ENABLE_COVERAGE_RERANK = _env_flag("RAG_ENABLE_COVERAGE_RERANK", True)


def _terms(text: str) -> list[str]:
    normalized = (text or "").lower().strip()
    terms = ASCII_WORD.findall(normalized)
    for run in CHINESE_RUN.findall(normalized):
        terms.append(run)
        if len(run) == 1:
            terms.append(run)
        else:
            terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    return terms


def tokenize_for_search(text: str) -> list[str]:
    """Stable public tokenizer shared by ingestion and candidate lookup."""
    return [term[:100] for term in _terms(text) if 0 < len(term) <= 100]


def build_query_variants(query: str) -> list[str]:
    """Keep the original question and add focused scenario clauses when present.

    Complex support questions often contain a concrete incident in quotes followed by
    a generic request such as "how should this be handled".  The focused clause is
    retrieved alongside the complete question rather than replacing it.
    """
    normalized = re.sub(r"\s+", " ", query or "").strip()
    if not normalized:
        return []

    variants = [normalized]
    for pattern in (QUOTED_SPAN, SCENARIO_SPAN):
        for match in pattern.finditer(normalized):
            focus = match.group(1).strip(" \t\n\r，,。！？?!；;：:\"'“”‘’")
            if len(focus) < 4 or focus in variants:
                continue
            variants.append(focus)
            if len(variants) >= MAX_QUERY_VARIANTS:
                return variants
    return variants


def _keyword_score(query: str, text: str) -> float:
    query_terms = _terms(query)
    if not query_terms:
        return 0.0
    text_terms = Counter(_terms(text))
    matched = sum(min(2, text_terms.get(term, 0)) for term in query_terms)
    score = matched / (len(query_terms) * 2)
    normalized_query = re.sub(r"\s+", "", query.lower())
    normalized_text = re.sub(r"\s+", "", text.lower())
    if normalized_query and normalized_query in normalized_text:
        score = max(score, 0.95)
    return float(min(1.0, score))


def _dense_score(query_embedding: np.ndarray, embedding_json: str | None) -> float:
    if not embedding_json:
        return 0.0
    try:
        vector = deserialize_embedding(embedding_json)
        if vector.shape != query_embedding.shape:
            return 0.0
        score = float(np.dot(query_embedding, vector))
        return max(0.0, min(1.0, (score + 1.0) / 2.0))
    except (TypeError, ValueError):
        return 0.0


def _knowledge_point_text(point: dict) -> str:
    return " ".join(
        [
            str(point.get("name") or ""),
            str(point.get("description") or ""),
            str(point.get("summary") or ""),
            *[str(example) for example in point.get("examples", [])],
        ]
    ).strip()


def _knowledge_point_score(query: str, query_embedding: np.ndarray, point: dict) -> float:
    dense = _dense_score(query_embedding, point.get("embedding_json"))
    keyword = _keyword_score(query, _knowledge_point_text(point))
    return dense * 0.65 + keyword * 0.35


def rank_knowledge_candidates(
    query: str,
    knowledge_points: list[dict],
    query_embedding: np.ndarray,
    limit: int,
) -> list[tuple[dict, float]]:
    embedding = np.asarray(query_embedding, dtype="float32")
    if embedding.ndim != 1 or limit <= 0:
        return []
    ranked = [
        (point, _knowledge_point_score(query, embedding, point))
        for point in knowledge_points
        if point.get("status", "active") == "active"
    ]
    ranked.sort(
        key=lambda item: (
            item[1],
            float(item[0].get("extraction_confidence") or 0),
            -int(item[0]["id"]),
        ),
        reverse=True,
    )
    return [item for item in ranked[:limit] if item[1] > 0]


@lru_cache(maxsize=8)
def _dense_matrix(serialized: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    vectors = []
    valid = []
    dimension = 0
    for value in serialized:
        try:
            vector = deserialize_embedding(value) if value else np.empty(0, dtype="float32")
        except (TypeError, ValueError):
            vector = np.empty(0, dtype="float32")
        if vector.ndim == 1 and vector.size and not dimension:
            dimension = int(vector.size)
        vectors.append(vector)
    if not dimension:
        return np.empty((len(serialized), 0), dtype="float32"), np.zeros(len(serialized), dtype=bool)
    matrix = np.zeros((len(serialized), dimension), dtype="float32")
    for index, vector in enumerate(vectors):
        if vector.shape == (dimension,):
            matrix[index] = vector
            valid.append(True)
        else:
            valid.append(False)
    return matrix, np.asarray(valid, dtype=bool)


def _dense_chunk_scores(query_embedding: np.ndarray, chunks: list[dict]) -> list[float]:
    matrix, valid = _dense_matrix(tuple(str(chunk.get("embedding_json") or "") for chunk in chunks))
    if matrix.shape[1:] != query_embedding.shape:
        return [0.0] * len(chunks)
    similarities = matrix @ query_embedding
    normalized = np.clip((similarities + 1.0) / 2.0, 0.0, 1.0)
    normalized[~valid] = 0.0
    return normalized.astype(float).tolist()


def _chunk_search_text(chunk: dict) -> str:
    kb_ids = chunk.get("kb_ids") or []
    return "\n".join(
        part
        for part in [
            str(chunk.get("material_title") or "").strip(),
            str(chunk.get("heading_path") or "").strip(),
            " ".join(str(item) for item in kb_ids),
            str(chunk.get("chunk_text") or "").strip(),
        ]
        if part
    )


@lru_cache(maxsize=8)
def _bm25_corpus(documents: tuple[str, ...]):
    tokenized = tuple(tuple(_terms(document)) for document in documents)
    document_count = len(tokenized)
    average_length = sum(len(tokens) for tokens in tokenized) / max(1, document_count)
    frequencies: Counter[str] = Counter()
    for tokens in tokenized:
        frequencies.update(set(tokens))
    return tokenized, document_count, average_length, frequencies


def _bm25_scores(query: str, documents: list[str]) -> list[float]:
    query_terms = _terms(query)
    if not query_terms or not documents:
        return [0.0] * len(documents)

    tokenized, document_count, average_length, frequencies = _bm25_corpus(tuple(documents))

    k1, b = 1.5, 0.75
    raw_scores = []
    query_frequency = Counter(query_terms)
    for document, tokens in zip(documents, tokenized):
        term_frequency = Counter(tokens)
        length = max(1, len(tokens))
        score = 0.0
        for term, query_count in query_frequency.items():
            frequency = term_frequency.get(term, 0)
            if not frequency:
                continue
            document_frequency = frequencies[term]
            inverse_frequency = math.log(
                1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            denominator = frequency + k1 * (1.0 - b + b * length / max(1.0, average_length))
            score += query_count * inverse_frequency * frequency * (k1 + 1.0) / denominator
        normalized_query = re.sub(r"\s+", "", query.lower())
        normalized_document = re.sub(r"\s+", "", document.lower())
        if normalized_query and normalized_query in normalized_document:
            score += 2.0
        raw_scores.append(score)

    maximum = max(raw_scores, default=0.0)
    if maximum <= 0:
        return [0.0] * len(raw_scores)
    return [float(score / maximum) for score in raw_scores]


def _ranks(scores: list[float]) -> dict[int, int]:
    ordered = sorted(range(len(scores)), key=lambda index: (scores[index], -index), reverse=True)
    return {index: rank for rank, index in enumerate(ordered, start=1)}


def _coverage_rerank(ranked: list[dict], top_k: int) -> list[dict]:
    """Select high-scoring results while avoiding duplicate evidence fragments.

    The base retrieval score remains available as ``score``.  Only selection order
    changes, and the applied penalty is returned for traceability.
    """
    remaining = list(ranked)
    selected: list[dict] = []
    selected_ids: set[str] = set()

    while remaining and len(selected) < top_k:
        def selection_value(item: dict) -> tuple[float, float, float, int]:
            kb_ids = {str(kb_id).upper() for kb_id in item.get("kb_ids", [])}
            overlap = len(kb_ids & selected_ids)
            penalty = COVERAGE_DUPLICATE_PENALTY * overlap
            return (
                float(item.get("rerank_score", item["score"])) - penalty,
                float(item["keyword_score"]),
                float(item["dense_score"]),
                -int(item["id"]),
            )

        chosen = max(remaining, key=selection_value)
        remaining.remove(chosen)
        kb_ids = {str(kb_id).upper() for kb_id in chosen.get("kb_ids", [])}
        overlap = len(kb_ids & selected_ids)
        penalty = COVERAGE_DUPLICATE_PENALTY * overlap
        selected_ids.update(kb_ids)
        selected.append(
            {
                **chosen,
                "selection_score": round(
                    float(chosen.get("rerank_score", chosen["score"])) - penalty, 6
                ),
                "evidence_overlap": overlap,
                "coverage_penalty": round(penalty, 6),
            }
        )
    return selected


def _relevance_rerank(query: str, ranked: list[dict]) -> list[dict]:
    """Cheap second-stage reranker over the bounded candidate set."""
    query_terms = set(tokenize_for_search(query))
    compact_query = re.sub(r"\s+", "", query or "").casefold()
    reranked = []
    for item in ranked:
        text = _chunk_search_text(item)
        text_terms = set(tokenize_for_search(text))
        coverage = len(query_terms & text_terms) / max(1, len(query_terms))
        compact_text = re.sub(r"\s+", "", text).casefold()
        phrase_bonus = 1.0 if compact_query and compact_query in compact_text else 0.0
        rerank_score = (
            float(item["score"]) * 0.72
            + coverage * 0.23
            + phrase_bonus * 0.05
        )
        reranked.append(
            {
                **item,
                "term_coverage": round(coverage, 6),
                "phrase_match": bool(phrase_bonus),
                "rerank_score": round(rerank_score, 6),
                "reranker_version": RERANKER_VERSION,
            }
        )
    reranked.sort(
        key=lambda item: (
            item["rerank_score"], item["keyword_score"], item["dense_score"], -int(item["id"])
        ),
        reverse=True,
    )
    return reranked


def hybrid_search(
    query: str,
    chunks: list[dict],
    knowledge_points: list[dict],
    top_k: int = 5,
    embedding_provider=embed_texts,
    enable_multi_query: bool = DEFAULT_ENABLE_MULTI_QUERY,
    enable_coverage_rerank: bool = DEFAULT_ENABLE_COVERAGE_RERANK,
    precomputed_query_embeddings: np.ndarray | list[list[float]] | None = None,
) -> list[dict]:
    if not query.strip() or not chunks:
        return []

    queries = build_query_variants(query) if enable_multi_query else [query.strip()]
    query_embeddings = np.asarray(
        embedding_provider(queries)
        if precomputed_query_embeddings is None
        else precomputed_query_embeddings,
        dtype="float32",
    )
    if query_embeddings.ndim != 2 or query_embeddings.shape[0] != len(queries):
        raise ValueError("embedding provider must return one vector per query variant")
    query_embedding = query_embeddings[0]
    point_scores: dict[int, float] = {}
    point_by_chunk: dict[int, list[dict]] = {}

    for point in knowledge_points:
        point_scores[point["id"]] = _knowledge_point_score(query, query_embedding, point)
        public_point = {
            "id": point["id"],
            "name": point.get("name", ""),
            "description": point.get("description", ""),
            "summary": point.get("summary", ""),
            "examples": point.get("examples", []),
        }
        for chunk_id in point.get("source_chunk_ids", []):
            point_by_chunk.setdefault(int(chunk_id), []).append(public_point)

    search_texts = [_chunk_search_text(chunk) for chunk in chunks]
    dense_scores = _dense_chunk_scores(query_embedding, chunks)
    keyword_scores = _bm25_scores(query, search_texts)
    focused_dense_scores = [
        _dense_chunk_scores(embedding, chunks)
        for embedding in query_embeddings[1:]
    ]
    focused_keyword_scores = [
        _bm25_scores(focused_query, search_texts)
        for focused_query in queries[1:]
    ]
    knowledge_scores = []
    linked_by_index = []
    for chunk in chunks:
        linked_points = point_by_chunk.get(int(chunk["id"]), [])
        knowledge = max(
            (point_scores.get(point["id"], 0.0) for point in linked_points),
            default=0.0,
        )
        knowledge_scores.append(knowledge)
        linked_by_index.append(linked_points)

    dense_ranks = _ranks(dense_scores)
    keyword_ranks = _ranks(keyword_scores)
    knowledge_ranks = _ranks(knowledge_scores)
    focused_dense_ranks = [_ranks(scores) for scores in focused_dense_scores]
    focused_keyword_ranks = [_ranks(scores) for scores in focused_keyword_scores]
    candidate_limit = min(len(chunks), max(60, top_k * 10))
    candidate_indices = set(
        sorted(range(len(chunks)), key=lambda index: dense_scores[index], reverse=True)[:candidate_limit]
    )
    candidate_indices.update(
        sorted(range(len(chunks)), key=lambda index: keyword_scores[index], reverse=True)[:candidate_limit]
    )
    if any(score > 0 for score in knowledge_scores):
        candidate_indices.update(
            sorted(range(len(chunks)), key=lambda index: knowledge_scores[index], reverse=True)[:candidate_limit]
        )
    for scores in [*focused_dense_scores, *focused_keyword_scores]:
        candidate_indices.update(
            sorted(range(len(chunks)), key=lambda index: scores[index], reverse=True)[:candidate_limit]
        )

    ranked = []
    maximum_rrf = (
        sum(RRF_WEIGHTS.values())
        + len(focused_dense_scores) * FOCUSED_QUERY_WEIGHT
        + len(focused_keyword_scores) * FOCUSED_QUERY_WEIGHT
    ) / (RRF_K + 1)
    for index in candidate_indices:
        dense = dense_scores[index]
        keyword = keyword_scores[index]
        knowledge = knowledge_scores[index]
        rrf = RRF_WEIGHTS["dense"] / (RRF_K + dense_ranks[index])
        if keyword > 0:
            rrf += RRF_WEIGHTS["keyword"] / (RRF_K + keyword_ranks[index])
        if knowledge > 0:
            rrf += RRF_WEIGHTS["knowledge"] / (RRF_K + knowledge_ranks[index])
        focused_matches = 0
        for scores, ranks in zip(focused_dense_scores, focused_dense_ranks):
            if scores[index] > 0:
                rrf += FOCUSED_QUERY_WEIGHT / (RRF_K + ranks[index])
                focused_matches += 1
        for scores, ranks in zip(focused_keyword_scores, focused_keyword_ranks):
            if scores[index] > 0:
                rrf += FOCUSED_QUERY_WEIGHT / (RRF_K + ranks[index])
                focused_matches += 1
        score = min(1.0, rrf / maximum_rrf)
        chunk = chunks[index]
        ranked.append(
            {
                **chunk,
                "score": round(score, 6),
                "dense_score": round(dense, 6),
                "keyword_score": round(keyword, 6),
                "knowledge_score": round(knowledge, 6),
                "dense_rank": dense_ranks[index],
                "keyword_rank": keyword_ranks[index],
                "rrf_score": round(rrf, 8),
                "focused_query_matches": focused_matches,
                "query_variants": queries,
                "knowledge_points": linked_by_index[index],
            }
        )

    ranked.sort(
        key=lambda item: (
            item["score"],
            item["keyword_score"],
            item["dense_score"],
            -int(item["id"]),
        ),
        reverse=True,
    )
    ranked = _relevance_rerank(query, ranked)
    if not enable_coverage_rerank:
        return [
            {
                **item,
                "selection_score": item["score"],
                "evidence_overlap": 0,
                "coverage_penalty": 0.0,
            }
            for item in ranked[: min(top_k, len(ranked))]
        ]
    return _coverage_rerank(ranked, min(top_k, len(ranked)))
