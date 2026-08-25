from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evaluation.rag import deterministic_embeddings, evaluate_bundle
from app.integrations.embedding.service import EMBEDDING_MODEL_NAME, embed_texts


def evaluate_quality_gates(
    report: dict,
    *,
    min_mean_support_recall: float | None = None,
    min_any_hit_rate: float | None = None,
    min_all_support_rate: float | None = None,
    min_mrr: float | None = None,
    max_p95_ms: float | None = None,
) -> dict:
    """Return a machine-readable verdict for optional retrieval quality gates."""
    metrics = report["metrics"]
    thresholds = {
        "min_mean_support_recall": min_mean_support_recall,
        "min_any_hit_rate": min_any_hit_rate,
        "min_all_support_rate": min_all_support_rate,
        "min_mrr": min_mrr,
        "max_p95_ms": max_p95_ms,
    }
    failures: list[dict] = []
    minimums = {
        "min_mean_support_recall": "mean_support_recall",
        "min_any_hit_rate": "any_hit_rate",
        "min_all_support_rate": "all_support_rate",
        "min_mrr": "mrr",
    }
    for threshold_name, metric_name in minimums.items():
        threshold = thresholds[threshold_name]
        actual = float(metrics[metric_name])
        if threshold is not None and actual < threshold:
            failures.append(
                {
                    "metric": metric_name,
                    "actual": actual,
                    "operator": ">=",
                    "threshold": threshold,
                }
            )
    if max_p95_ms is not None:
        actual_p95 = float(metrics["latency_ms"]["p95"])
        if actual_p95 > max_p95_ms:
            failures.append(
                {
                    "metric": "latency_ms.p95",
                    "actual": actual_p95,
                    "operator": "<=",
                    "threshold": max_p95_ms,
                }
            )
    return {
        "passed": not failures,
        "thresholds": {key: value for key, value in thresholds.items() if value is not None},
        "failures": failures,
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval against a ZIP bundle")
    parser.add_argument("bundle", type=Path, help="ZIP with one Markdown corpus and one JSONL eval set")
    parser.add_argument("--mode", choices=["full", "reasoning"], default="full")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--embedding", choices=["real", "mock"], default="real")
    parser.add_argument("--enable-multi-query", action="store_true")
    parser.add_argument("--disable-coverage-rerank", action="store_true")
    parser.add_argument("--min-mean-support-recall", type=float)
    parser.add_argument("--min-any-hit-rate", type=float)
    parser.add_argument("--min-all-support-rate", type=float)
    parser.add_argument("--min-mrr", type=float)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    if args.top_k < 1 or args.top_k > 100:
        raise SystemExit("--top-k must be between 1 and 100")
    for name in (
        "min_mean_support_recall",
        "min_any_hit_rate",
        "min_all_support_rate",
        "min_mrr",
    ):
        value = getattr(args, name)
        if value is not None and not 0 <= value <= 1:
            raise SystemExit(f"--{name.replace('_', '-')} must be between 0 and 1")
    if args.max_p95_ms is not None and args.max_p95_ms <= 0:
        raise SystemExit("--max-p95-ms must be greater than 0")
    provider = embed_texts if args.embedding == "real" else deterministic_embeddings
    label = EMBEDDING_MODEL_NAME if args.embedding == "real" else "mock-deterministic-384"
    report = evaluate_bundle(
        args.bundle,
        top_k=args.top_k,
        mode=args.mode,
        limit=args.limit,
        embedding_provider=provider,
        embedding_label=label,
        enable_multi_query=args.enable_multi_query,
        enable_coverage_rerank=not args.disable_coverage_rerank,
    )
    report["quality_gates"] = evaluate_quality_gates(
        report,
        min_mean_support_recall=args.min_mean_support_recall,
        min_any_hit_rate=args.min_any_hit_rate,
        min_all_support_rate=args.min_all_support_rate,
        min_mrr=args.min_mrr,
        max_p95_ms=args.max_p95_ms,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    summary = {
        key: report[key]
        for key in ["mode", "top_k", "retriever_version", "embedding", "evaluated_cases", "index"]
    }
    summary["metrics"] = report["metrics"]
    summary["quality_gates"] = report["quality_gates"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not report["quality_gates"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
