from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document as DocxDocument

from app.evaluation.document_parsing import (
    aggregate_document_reports,
    evaluate_parsed_document,
    evaluate_quality_gates,
)
from app.integrations import complex_document_parser
from app.integrations.document_parser import parse_document_from_path
from scripts.build_complex_document_fixtures import build_fixture_pack

MANIFEST = Path(__file__).parent / "fixtures" / "complex_documents" / "manifest.json"


@pytest.fixture
def complex_document_pack(tmp_path: Path) -> tuple[Path, dict]:
    build_fixture_pack(tmp_path)
    return tmp_path, json.loads(MANIFEST.read_text(encoding="utf-8"))


def _fake_ocr(_page) -> dict:
    return {
        "blocks": [
            {
                "type": 0,
                "bbox": (72, 100, 500, 140),
                "lines": [
                    {
                        "spans": [
                            {"text": "Scanned invoice total 128.50"},
                        ]
                    }
                ],
            }
        ]
    }


def test_docx_preserves_order_and_table_but_excludes_headers(complex_document_pack):
    root, manifest = complex_document_pack
    specification = manifest["documents"][0]
    parsed = parse_document_from_path(root / specification["file"])
    indexed = parsed.render_for_index().text

    assert "正文中的业务约束必须保留" in indexed
    assert "| 字段 | 含义 |" in indexed
    assert "重复页眉噪声" not in indexed
    assert "重复页脚噪声" not in indexed
    assert any(block.block_type == "table" for block in parsed.blocks)
    assert {block.noise_reason for block in parsed.blocks if not block.should_index} == {
        "repeated_header",
        "repeated_footer",
    }
    assert indexed.index("第一步读取正文版面") < indexed.index("| 字段")
    assert indexed.index("| 字段") < indexed.index("最后一步保存来源块编号")


def test_pdf_recovers_table_page_provenance_and_repeated_noise(complex_document_pack):
    root, manifest = complex_document_pack
    specification = manifest["documents"][1]
    parsed = parse_document_from_path(root / specification["file"])
    indexed = parsed.render_for_index().text

    tables = [block for block in parsed.blocks if block.block_type == "table"]
    assert tables
    assert tables[0].page_number == 2
    assert "Recall" in " ".join(cell for row in tables[0].table_cells or [] for cell in row)
    assert "A3 Complex Document Benchmark" not in indexed
    assert "Page 1" not in indexed
    assert "【第 2 页】" in indexed
    assert any(block.noise_reason == "repeated_header" for block in parsed.blocks)
    assert any(block.noise_reason == "page_number" for block in parsed.blocks)


def test_scanned_pdf_uses_injected_ocr_provider(complex_document_pack):
    root, manifest = complex_document_pack
    specification = manifest["documents"][2]
    parsed = parse_document_from_path(
        root / specification["file"],
        ocr_provider=_fake_ocr,
    )

    assert "Scanned invoice total 128.50" in parsed.render_for_index().text
    assert any(block.ocr_used for block in parsed.blocks if block.should_index)
    assert any(block.noise_reason == "image_not_transcribed" for block in parsed.blocks)


def test_scanned_pdf_has_actionable_error_without_ocr_runtime(
    complex_document_pack,
    monkeypatch,
):
    root, manifest = complex_document_pack
    specification = manifest["documents"][2]

    def unavailable(_page):
        raise RuntimeError("tesseract unavailable")

    monkeypatch.setattr(complex_document_parser, "_ocr_page_dict", unavailable)
    with pytest.raises(ValueError, match="Tesseract"):
        parse_document_from_path(root / specification["file"])


def test_text_path_parser_uses_a_bounded_text_stream(tmp_path, monkeypatch):
    source = tmp_path / "notes.md"
    source.write_text("# 课程笔记\n\n有界读取", encoding="utf-8")

    def fail_unbounded_read(_self):
        raise AssertionError("parse_document_from_path must not call Path.read_bytes()")

    monkeypatch.setattr(Path, "read_bytes", fail_unbounded_read)

    parsed = parse_document_from_path(source)

    assert "有界读取" in parsed.render_for_index().text


def test_text_path_parser_rejects_content_beyond_the_character_limit(tmp_path, monkeypatch):
    source = tmp_path / "oversized.txt"
    source.write_text("x" * 33, encoding="utf-8")
    monkeypatch.setattr(complex_document_parser, "MAX_EXTRACTED_TEXT_CHARS", 32)

    with pytest.raises(ValueError, match="解析文本超过"):
        parse_document_from_path(source)


def test_docx_parser_rejects_content_beyond_the_character_limit(tmp_path, monkeypatch):
    source = tmp_path / "oversized.docx"
    document = DocxDocument()
    document.add_paragraph("x" * 64)
    document.save(source)
    monkeypatch.setattr(complex_document_parser, "MAX_EXTRACTED_TEXT_CHARS", 32)

    with pytest.raises(ValueError, match="解析文本超过"):
        parse_document_from_path(source)


def test_complex_document_golden_metrics_pass(complex_document_pack):
    root, manifest = complex_document_pack
    reports = []
    for specification in manifest["documents"]:
        parsed = parse_document_from_path(
            root / specification["file"],
            ocr_provider=_fake_ocr if specification.get("requires_ocr") else None,
        )
        reports.append(evaluate_parsed_document(parsed, specification))

    metrics = aggregate_document_reports(reports)
    verdict = evaluate_quality_gates(metrics, manifest["quality_gates"])

    assert metrics == {
        "content_recall": 1.0,
        "noise_exclusion_rate": 1.0,
        "table_cell_recall": 1.0,
        "reading_order_accuracy": 1.0,
    }
    assert verdict == {
        "passed": True,
        "thresholds": manifest["quality_gates"],
        "failures": [],
    }
