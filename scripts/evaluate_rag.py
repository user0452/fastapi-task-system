from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evaluation.rag import deterministic_embeddings, evaluate_bundle
from services.rag_service import EMBEDDING_MODEL_NAME, embed_texts


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval against a ZIP bundle")
    parser.add_argument("bundle", type=Path, help="ZIP with one Markdown corpus and one JSONL eval set")
    parser.add_argument("--mode", choices=["full", "reasoning"], default="full")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--embedding", choices=["real", "mock"], default="real")
    parser.add_argument("--enable-multi-query", action="store_true")
    parser.add_argument("--disable-coverage-rerank", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    if args.top_k < 1 or args.top_k > 100:
        raise SystemExit("--top-k must be between 1 and 100")
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
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    summary = {
        key: report[key]
        for key in ["mode", "top_k", "retriever_version", "embedding", "evaluated_cases", "index"]
    }
    summary["metrics"] = report["metrics"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
