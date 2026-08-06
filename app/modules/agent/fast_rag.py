"""Deterministic Fast RAG retrieval/evidence phase (no LLM calls)."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable


@dataclass(frozen=True)
class FastRagPrepared:
    citations: list[dict]
    anchor_chunk_ids: list[int]
    evidence: dict
    retrieval_ms: float
    evidence_ms: float


class FastRagFallback(RuntimeError):
    pass


def _select_anchors(citations: list[dict], max_anchors: int, min_score: float) -> list[dict]:
    anchors: list[dict] = []
    seen_material_sections: set[tuple[int | None, str]] = set()
    for item in citations:
        score = float(item.get("rerank_score", item.get("selection_score", item.get("score", 0))) or 0)
        if score < min_score or not item.get("chunk_id"):
            continue
        key = (item.get("material_id"), str(item.get("heading_path") or ""))
        if key in seen_material_sections:
            continue
        anchors.append(item)
        seen_material_sections.add(key)
        if len(anchors) >= max(1, max_anchors):
            break
    return anchors


def prepare_fast_rag(
    *,
    user_id: int,
    course_id: int,
    resolved_query: str,
    search_materials: Callable[[int, int, str, int], dict],
    read_evidence: Callable[[int, int, list[int], int, int], dict],
    max_anchors: int,
    neighbor_window: int,
    min_retrieval_score: float,
) -> FastRagPrepared:
    if len(str(resolved_query or "").strip()) < 3:
        raise FastRagFallback("resolved_query_is_low_information")
    retrieval_started = perf_counter()
    result = search_materials(user_id, course_id, resolved_query, max(4, max_anchors * 3))
    retrieval_ms = (perf_counter() - retrieval_started) * 1000
    citations = list(result.get("citations") or [])
    anchors = _select_anchors(citations, max_anchors, min_retrieval_score)
    if not anchors:
        raise FastRagFallback("retrieval_has_no_qualified_anchor")
    evidence_started = perf_counter()
    evidence = read_evidence(
        user_id, course_id, [int(item["chunk_id"]) for item in anchors], neighbor_window, 12000
    )
    evidence_ms = (perf_counter() - evidence_started) * 1000
    if not evidence.get("evidence_blocks"):
        raise FastRagFallback("evidence_is_empty")
    return FastRagPrepared(
        citations=anchors,
        anchor_chunk_ids=[int(item["chunk_id"]) for item in anchors],
        evidence=evidence,
        retrieval_ms=retrieval_ms,
        evidence_ms=evidence_ms,
    )


__all__ = ["FastRagFallback", "FastRagPrepared", "prepare_fast_rag"]
