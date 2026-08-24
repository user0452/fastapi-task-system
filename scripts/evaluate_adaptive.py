"""Run the deterministic Adaptive Learning Benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.evaluation.adaptive import benchmark_passes, render_report, run_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the Markdown report to this path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run the benchmark and fail if deterministic acceptance checks fail.",
    )
    args = parser.parse_args()

    result = run_benchmark()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_report(result), encoding="utf-8")
        print(f"Adaptive benchmark report written to {args.output}")
    else:
        print(render_report(result))
    print(json.dumps(result["v2"], ensure_ascii=False, sort_keys=True))

    if args.check and not benchmark_passes(result):
        print("Adaptive benchmark acceptance checks failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
