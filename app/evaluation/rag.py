from __future__ import annotations

import json
import statistics
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Callable

import numpy as np

from app.integrations.embedding.chunking import chunk_document, retrieval_text
from app.integrations.embedding.hybrid_search import RETRIEVER_VERSION, hybrid_search
from app.integrations.embedding.service import (
    EMBEDDING_MODEL_NAME,
    embed_texts,
    serialize_embedding,
)

MAX_BUNDLE_ENTRY_BYTES = 5 * 1024 * 1024
EXCLUDED_REASONING_TYPES = {"case", "faq", "evaluation_guidance", "index"}
LEAKED_REFERENCE_PREFIXES = ("YQ-CASE-", "YQ-FAQ-")


def load_bundle(path: str | Path) -> tuple[str, list[dict], dict]:
    bundle = Path(path)
    with zipfile.ZipFile(bundle) as archive:
        unsafe = [
            name
            for name in archive.namelist()
            if Path(name).is_absolute() or ".." in Path(name).parts
        ]
        if unsafe:
            raise ValueError(f"unsafe RAG bundle entries: {unsafe[:3]}")
        markdown = [entry for entry in archive.infolist() if entry.filename.lower().endswith(".md")]
        evaluations = [entry for entry in archive.infolist() if entry.filename.lower().endswith(".jsonl")]
        if len(markdown) != 1 or len(evaluations) != 1:
            raise ValueError("RAG bundle must contain exactly one Markdown corpus and one JSONL evaluation set")
        for entry in [markdown[0], evaluations[0]]:
            if entry.file_size > MAX_BUNDLE_ENTRY_BYTES:
                raise ValueError(f"RAG bundle entry is too large: {entry.filename}")
        corpus = archive.read(markdown[0]).decode("utf-8-sig")
        rows = []
        for line_number, line in enumerate(
            archive.read(evaluations[0]).decode("utf-8-sig").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}") from exc
            required = {"id", "type", "question", "supporting_kb_ids", "difficulty"}
            if not required.issubset(row):
                raise ValueError(f"evaluation row {line_number} is missing required fields")
            rows.append(row)
    return corpus, rows, {
        "bundle": str(bundle.resolve()),
        "corpus_entry": markdown[0].filename,
        "evaluation_entry": evaluations[0].filename,
    }


def deterministic_embeddings(texts: list[str], dimension: int = 384) -> np.ndarray:
    rows = []
    for text in texts:
        source = np.frombuffer((text or " ").encode("utf-8"), dtype=np.uint8)
        if source.size == 0:
            source = np.ones(1, dtype=np.uint8)
        repeated = np.resize(source.astype("float32") + 1.0, dimension)
        repeated += (np.arange(dimension, dtype="float32") % 17) + 1.0
        repeated -= repeated.mean()
        norm = float(np.linalg.norm(repeated)) or 1.0
        rows.append(repeated / norm)
    return np.vstack(rows).astype("float32")


def build_index(
    corpus: str,
    *,
    mode: str = "full",
    embedding_provider: Callable[[list[str]], np.ndarray] = embed_texts,
    document_title: str = "RAG evaluation corpus",
) -> list[dict]:
    if mode not in {"full", "reasoning"}:
        raise ValueError("mode must be 'full' or 'reasoning'")
    chunks = chunk_document(corpus)
    chunks = [chunk for chunk in chunks if chunk.get("document_type") != "index"]
    if mode == "reasoning":
        chunks = [
            chunk
            for chunk in chunks
            if chunk.get("document_type") not in EXCLUDED_REASONING_TYPES
        ]
    texts = [
        retrieval_text(
            chunk["chunk_text"],
            chunk.get("heading_path"),
            chunk.get("kb_ids"),
            document_title,
        )
        for chunk in chunks
    ]
    vectors = embedding_provider(texts)
    if len(vectors) != len(chunks):
        raise ValueError("embedding count does not match evaluation chunks")
    return [
        {
            **chunk,
            "id": index + 1,
            "material_id": 1,
            "material_title": document_title,
            "filename": None,
            "embedding_json": serialize_embedding(vector),
            "embedding_model": EMBEDDING_MODEL_NAME,
        }
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]


def prepare_cases(rows: list[dict], mode: str) -> tuple[list[dict], dict]:
    if mode == "full":
        return list(rows), {"deduplicated": 0, "unsupported_after_filter": 0, "excluded_types": 0}

    prepared = []
    seen_questions = set()
    stats = {"deduplicated": 0, "unsupported_after_filter": 0, "excluded_types": 0}
    for row in rows:
        if row.get("type") == "faq":
            stats["excluded_types"] += 1
            continue
        question_key = " ".join(str(row.get("question") or "").split()).lower()
        if question_key in seen_questions:
            stats["deduplicated"] += 1
            continue
        seen_questions.add(question_key)
        gold = [
            str(kb_id).upper()
            for kb_id in row.get("supporting_kb_ids", [])
            if not str(kb_id).upper().startswith(LEAKED_REFERENCE_PREFIXES)
        ]
        if not gold:
            stats["unsupported_after_filter"] += 1
            continue
        prepared.append({**row, "supporting_kb_ids": gold})
    return prepared, stats


def score_case(case: dict, hits: list[dict], latency_ms: float) -> dict:
    gold = list(dict.fromkeys(str(item).upper() for item in case.get("supporting_kb_ids", [])))
    hit_ids = [
        set(str(item).upper() for item in hit.get("kb_ids", []))
        for hit in hits
    ]
    found = set().union(*hit_ids) if hit_ids else set()
    matched = sorted(set(gold) & found)
    first_rank = next(
        (rank for rank, ids in enumerate(hit_ids, start=1) if set(gold) & ids),
        None,
    )
    recall = len(matched) / len(gold) if gold else 0.0
    return {
        "id": case["id"],
        "type": case["type"],
        "difficulty": case["difficulty"],
        "question": case["question"],
        "gold_kb_ids": gold,
        "matched_kb_ids": matched,
        "missing_kb_ids": sorted(set(gold) - found),
        "support_recall": recall,
        "any_hit": bool(matched),
        "all_support_hit": recall == 1.0,
        "reciprocal_rank": 1.0 / first_rank if first_rank else 0.0,
        "latency_ms": latency_ms,
        "hits": [
            {
                "rank": rank,
                "chunk_id": hit["id"],
                "kb_ids": hit.get("kb_ids", []),
                "heading_path": hit.get("heading_path"),
                "score": hit.get("score", 0.0),
                "dense_score": hit.get("dense_score", 0.0),
                "keyword_score": hit.get("keyword_score", 0.0),
            }
            for rank, hit in enumerate(hits, start=1)
        ],
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _summary(results: list[dict]) -> dict:
    if not results:
        return {
            "cases": 0,
            "mean_support_recall": 0.0,
            "any_hit_rate": 0.0,
            "all_support_rate": 0.0,
            "mrr": 0.0,
        }
    return {
        "cases": len(results),
        "mean_support_recall": round(statistics.fmean(item["support_recall"] for item in results), 6),
        "any_hit_rate": round(statistics.fmean(float(item["any_hit"]) for item in results), 6),
        "all_support_rate": round(statistics.fmean(float(item["all_support_hit"]) for item in results), 6),
        "mrr": round(statistics.fmean(item["reciprocal_rank"] for item in results), 6),
    }


def aggregate_results(results: list[dict]) -> dict:
    by_type: dict[str, list[dict]] = defaultdict(list)
    by_difficulty: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        by_type[result["type"]].append(result)
        by_difficulty[result["difficulty"]].append(result)
    latencies = [item["latency_ms"] for item in results]
    return {
        **_summary(results),
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
            "max": round(max(latencies, default=0.0), 3),
        },
        "by_type": {key: _summary(value) for key, value in sorted(by_type.items())},
        "by_difficulty": {
            key: _summary(value) for key, value in sorted(by_difficulty.items())
        },
    }


def evaluate_bundle(
    bundle_path: str | Path,
    *,
    top_k: int = 8,
    mode: str = "full",
    limit: int | None = None,
    embedding_provider: Callable[[list[str]], np.ndarray] = embed_texts,
    embedding_label: str = EMBEDDING_MODEL_NAME,
    enable_multi_query: bool = False,
    enable_coverage_rerank: bool = True,
) -> dict:
    corpus, rows, source = load_bundle(bundle_path)
    cases, preparation = prepare_cases(rows, mode)
    if limit is not None:
        cases = cases[: max(0, limit)]
    index_started = time.perf_counter()
    chunks = build_index(
        corpus,
        mode=mode,
        embedding_provider=embedding_provider,
        document_title=Path(source["corpus_entry"]).stem,
    )
    index_ms = (time.perf_counter() - index_started) * 1000

    results = []
    for case in cases:
        started = time.perf_counter()
        hits = hybrid_search(
            case["question"],
            chunks,
            [],
            top_k,
            embedding_provider=embedding_provider,
            enable_multi_query=enable_multi_query,
            enable_coverage_rerank=enable_coverage_rerank,
        )
        results.append(score_case(case, hits, (time.perf_counter() - started) * 1000))

    failures = sorted(
        (item for item in results if not item["all_support_hit"]),
        key=lambda item: (item["support_recall"], item["reciprocal_rank"], item["id"]),
    )
    return {
        "source": source,
        "mode": mode,
        "top_k": top_k,
        "retriever_version": RETRIEVER_VERSION,
        "retrieval_options": {
            "multi_query": enable_multi_query,
            "coverage_rerank": enable_coverage_rerank,
        },
        "embedding": embedding_label,
        "input_cases": len(rows),
        "evaluated_cases": len(cases),
        "preparation": preparation,
        "index": {
            "chunks": len(chunks),
            "unique_kb_ids": len({kb_id for chunk in chunks for kb_id in chunk.get("kb_ids", [])}),
            "build_ms": round(index_ms, 3),
        },
        "metrics": aggregate_results(results),
        "failures": failures,
        "results": results,
    }
