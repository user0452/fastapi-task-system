"""Deterministic quality metrics for layout-aware document parsing."""

from __future__ import annotations

import re
from statistics import fmean
from typing import Any

from app.integrations.document_model import ParsedDocument

METRIC_NAMES = (
    "content_recall",
    "noise_exclusion_rate",
    "table_cell_recall",
    "reading_order_accuracy",
)


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _recall(expected: list[str], actual: str) -> float:
    if not expected:
        return 1.0
    normalized_actual = _normalized(actual)
    hits = sum(1 for item in expected if _normalized(item) in normalized_actual)
    return hits / len(expected)


def _exclusion_rate(expected_noise: list[str], indexed_text: str) -> float:
    if not expected_noise:
        return 1.0
    normalized_text = _normalized(indexed_text)
    excluded = sum(1 for item in expected_noise if _normalized(item) not in normalized_text)
    return excluded / len(expected_noise)


def _reading_order_accuracy(expected: list[str], indexed_text: str) -> float:
    if not expected:
        return 1.0
    normalized_text = _normalized(indexed_text)
    positions = [normalized_text.find(_normalized(item)) for item in expected]
    if len(positions) == 1:
        return float(positions[0] >= 0)
    correct = sum(
        1
        for left, right in zip(positions, positions[1:])
        if left >= 0 and right >= 0 and left < right
    )
    return correct / (len(positions) - 1)


def evaluate_parsed_document(parsed: ParsedDocument, specification: dict[str, Any]) -> dict:
    """Evaluate one parsed document against a small human-readable golden spec."""
    indexed_text = parsed.render_for_index().text
    table_text = "\n".join(
        str(cell)
        for block in parsed.blocks
        for row in block.table_cells or []
        for cell in row
    )
    metrics = {
        "content_recall": _recall(
            list(specification.get("required_text") or []),
            indexed_text,
        ),
        "noise_exclusion_rate": _exclusion_rate(
            list(specification.get("excluded_noise") or []),
            indexed_text,
        ),
        "table_cell_recall": _recall(
            list(specification.get("table_cells") or []),
            table_text,
        ),
        "reading_order_accuracy": _reading_order_accuracy(
            list(specification.get("reading_order") or []),
            indexed_text,
        ),
    }
    return {
        "file": specification.get("file") or parsed.source_name,
        "metrics": {name: round(value, 4) for name, value in metrics.items()},
        "diagnostics": parsed.diagnostics(),
    }


def aggregate_document_reports(reports: list[dict[str, Any]]) -> dict[str, float]:
    if not reports:
        return {name: 0.0 for name in METRIC_NAMES}
    return {
        name: round(fmean(float(report["metrics"][name]) for report in reports), 4)
        for name in METRIC_NAMES
    }


def evaluate_quality_gates(metrics: dict[str, float], gates: dict[str, Any]) -> dict[str, Any]:
    failures = []
    for metric_name in METRIC_NAMES:
        threshold_name = f"min_{metric_name}"
        if threshold_name not in gates:
            continue
        threshold = float(gates[threshold_name])
        actual = float(metrics.get(metric_name, 0.0))
        if actual < threshold:
            failures.append(
                {
                    "metric": metric_name,
                    "actual": actual,
                    "operator": ">=",
                    "threshold": threshold,
                }
            )
    return {"passed": not failures, "thresholds": dict(gates), "failures": failures}


__all__ = [
    "METRIC_NAMES",
    "aggregate_document_reports",
    "evaluate_parsed_document",
    "evaluate_quality_gates",
]
