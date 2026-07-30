"""Evaluate complex-document parsing against the repository golden manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evaluation.document_parsing import (
    aggregate_document_reports,
    evaluate_parsed_document,
    evaluate_quality_gates,
)
from app.integrations.document_parser import parse_document_from_path
from scripts.build_complex_document_fixtures import build_fixture_pack

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT_DIR / "tests" / "fixtures" / "complex_documents" / "manifest.json"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documents", type=Path, help="Directory containing the fixture documents")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--build-fixtures", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    if arguments.build_fixtures:
        build_fixture_pack(arguments.documents)
    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    reports = []
    errors = []
    skipped = []
    for specification in manifest["documents"]:
        if arguments.skip_ocr and specification.get("requires_ocr"):
            skipped.append(specification["file"])
            continue
        try:
            parsed = parse_document_from_path(arguments.documents / specification["file"])
            reports.append(evaluate_parsed_document(parsed, specification))
        except Exception as exc:
            errors.append(
                {
                    "file": specification["file"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    metrics = aggregate_document_reports(reports)
    quality_gates = evaluate_quality_gates(metrics, manifest.get("quality_gates") or {})
    quality_gates["passed"] = bool(quality_gates["passed"] and not errors)
    report = {
        "schema_version": 1,
        "documents": reports,
        "errors": errors,
        "skipped": skipped,
        "metrics": metrics,
        "quality_gates": quality_gates,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if quality_gates["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
