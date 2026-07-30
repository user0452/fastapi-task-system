"""Run one minimal real LLM call and a real local embedding smoke check."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from langchain_core.messages import HumanMessage

from app.core.config import get_settings
from app.integrations.embedding.service import (
    EMBEDDING_MODEL_NAME,
    USE_MOCK_EMBEDDING,
    embed_texts,
)
from app.integrations.llm.model_provider import get_llm


def check_embedding(
    provider: Callable[[list[str]], np.ndarray] = embed_texts,
) -> dict[str, Any]:
    if USE_MOCK_EMBEDDING:
        raise RuntimeError("A3_MOCK_EMBEDDING must be false for a live canary")
    started = time.perf_counter()
    vectors = np.asarray(
        provider(["课程学习计划", "database migration recovery"]),
        dtype="float32",
    )
    latency_ms = (time.perf_counter() - started) * 1000
    if vectors.ndim != 2 or vectors.shape[0] != 2 or vectors.shape[1] < 128:
        raise RuntimeError("embedding provider returned an invalid matrix")
    if not np.isfinite(vectors).all():
        raise RuntimeError("embedding provider returned non-finite values")
    norms = np.linalg.norm(vectors, axis=1)
    if not all(math.isclose(float(norm), 1.0, rel_tol=0.15) for norm in norms):
        raise RuntimeError("embedding vectors are not normalized")
    if np.allclose(vectors[0], vectors[1]):
        raise RuntimeError("embedding provider returned identical vectors for distinct texts")
    return {
        "component": "embedding",
        "model": EMBEDDING_MODEL_NAME,
        "dimensions": int(vectors.shape[1]),
        "latency_ms": round(latency_ms, 3),
        "passed": True,
    }


def check_llm(model_factory: Callable[[], Any] = get_llm) -> dict[str, Any]:
    settings = get_settings()
    if settings.mock_llm:
        raise RuntimeError("A3_MOCK_LLM must be false for a live canary")
    started = time.perf_counter()
    response = model_factory().invoke(
        [HumanMessage(content="Reply with exactly A3_CANARY_OK and nothing else.")]
    )
    latency_ms = (time.perf_counter() - started) * 1000
    content = response.content if hasattr(response, "content") else response
    if isinstance(content, list):
        content = " ".join(str(item) for item in content)
    if not str(content).strip():
        raise RuntimeError("LLM provider returned an empty response")
    return {
        "component": "llm",
        "model": settings.deepseek_model,
        "latency_ms": round(latency_ms, 3),
        "passed": True,
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify configured real AI integrations")
    parser.add_argument(
        "--component",
        action="append",
        choices=["llm", "embedding"],
        help="Component to check; repeat to select both (default: both)",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    requested = list(dict.fromkeys(args.component or ["llm", "embedding"]))
    checks = {"llm": check_llm, "embedding": check_embedding}
    results: list[dict[str, Any]] = []
    failed = False
    for component in requested:
        try:
            results.append(checks[component]())
        except Exception as exc:  # The report deliberately excludes provider error text and secrets.
            failed = True
            results.append(
                {
                    "component": component,
                    "passed": False,
                    "error_type": type(exc).__name__,
                }
            )
    report = {"passed": not failed, "results": results}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
