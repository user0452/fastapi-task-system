"""Canonical layout-aware document model used before RAG chunking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PARSER_VERSION = "layout-blocks-v1"
BLOCK_TYPES = {"heading", "paragraph", "table", "image", "list", "noise"}


def _clean_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "").replace("\r\n", "\n")).strip()


def _clean_cell(value: Any) -> str:
    return _clean_text("" if value is None else str(value)).replace("\n", "<br>")


def table_to_markdown(rows: list[list[str]]) -> str:
    cleaned = [[_clean_cell(cell) for cell in row] for row in rows if any(_clean_cell(c) for c in row)]
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    normalized = [row + [""] * (width - len(row)) for row in cleaned]
    header = normalized[0]
    body = normalized[1:]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


@dataclass
class DocumentBlock:
    block_id: str
    block_index: int
    block_type: str
    text: str = ""
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    reading_order: int = 0
    heading_level: int | None = None
    table_cells: list[list[str]] | None = None
    ocr_used: bool = False
    ocr_confidence: float | None = None
    should_index: bool = True
    noise_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.block_type not in BLOCK_TYPES:
            raise ValueError(f"unsupported document block type: {self.block_type}")
        self.text = _clean_text(self.text)
        if self.bbox is not None:
            x0, y0, x1, y1 = self.bbox
            self.bbox = (
                round(float(x0), 3),
                round(float(y0), 3),
                round(float(x1), 3),
                round(float(y1), 3),
            )
        if self.table_cells is not None:
            self.table_cells = [
                [_clean_cell(cell) for cell in row]
                for row in self.table_cells
            ]

    def index_text(self) -> str:
        if not self.should_index:
            return ""
        if self.block_type == "table" and self.table_cells:
            return table_to_markdown(self.table_cells)
        if self.block_type == "heading":
            level = max(1, min(6, int(self.heading_level or 1)))
            return f"{'#' * level} {self.text}" if self.text else ""
        return self.text

    def as_record(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "block_index": self.block_index,
            "block_type": self.block_type,
            "page_number": self.page_number,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "reading_order": self.reading_order,
            "heading_level": self.heading_level,
            "text": self.text,
            "table_cells": self.table_cells,
            "ocr_used": self.ocr_used,
            "ocr_confidence": self.ocr_confidence,
            "should_index": self.should_index,
            "noise_reason": self.noise_reason,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RenderedBlockSpan:
    block_id: str
    start: int
    end: int


@dataclass(frozen=True)
class RenderedDocument:
    text: str
    spans: tuple[RenderedBlockSpan, ...]


@dataclass
class ParsedDocument:
    source_name: str
    blocks: list[DocumentBlock]
    warnings: list[str] = field(default_factory=list)
    parser_version: str = PARSER_VERSION

    def render_for_index(self) -> RenderedDocument:
        parts: list[str] = []
        spans: list[RenderedBlockSpan] = []
        offset = 0
        current_page: int | None = None
        for block in sorted(self.blocks, key=lambda item: (item.block_index, item.reading_order)):
            content = block.index_text()
            if not content:
                continue
            if block.page_number is not None and block.page_number != current_page:
                marker = f"【第 {block.page_number} 页】"
                separator = "\n\n" if parts else ""
                parts.append(separator + marker)
                offset += len(separator) + len(marker)
                current_page = block.page_number
            separator = "\n\n" if parts else ""
            parts.append(separator + content)
            start = offset + len(separator)
            end = start + len(content)
            spans.append(RenderedBlockSpan(block.block_id, start, end))
            offset = end
        return RenderedDocument("".join(parts).strip(), tuple(spans))

    def block_map(self) -> dict[str, DocumentBlock]:
        return {block.block_id: block for block in self.blocks}

    def source_block_ids_for_range(
        self,
        start: int | None,
        end: int | None,
        *,
        rendered: RenderedDocument | None = None,
    ) -> list[str]:
        return self.source_block_ids_for_ranges(
            [(start, end)],
            rendered=rendered,
        )[0]

    def source_block_ids_for_ranges(
        self,
        ranges: list[tuple[int | None, int | None]],
        *,
        rendered: RenderedDocument | None = None,
    ) -> list[list[str]]:
        """Map ordered or overlapping text ranges to blocks with a sweep-line scan."""

        rendered = rendered or self.render_for_index()
        results: list[list[str]] = [[] for _ in ranges]
        normalized = sorted(
            (
                (index, int(start), int(end))
                for index, (start, end) in enumerate(ranges)
                if start is not None and end is not None and int(end) > int(start)
            ),
            key=lambda item: (item[1], item[2], item[0]),
        )
        active: list[RenderedBlockSpan] = []
        span_index = 0
        spans = rendered.spans
        for range_index, start, end in normalized:
            active = [span for span in active if span.end > start]
            while span_index < len(spans) and spans[span_index].start < end:
                span = spans[span_index]
                span_index += 1
                if span.end > start:
                    active.append(span)
            results[range_index] = [
                span.block_id
                for span in active
                if span.start < end and span.end > start
            ]
        return results

    def diagnostics(self) -> dict[str, Any]:
        indexed = [block for block in self.blocks if block.should_index and block.index_text()]
        return {
            "parser_version": self.parser_version,
            "total_blocks": len(self.blocks),
            "indexed_blocks": len(indexed),
            "noise_blocks": sum(1 for block in self.blocks if not block.should_index),
            "table_blocks": sum(1 for block in self.blocks if block.block_type == "table"),
            "image_blocks": sum(1 for block in self.blocks if block.block_type == "image"),
            "ocr_blocks": sum(1 for block in self.blocks if block.ocr_used),
            "warnings": list(self.warnings),
        }


__all__ = [
    "BLOCK_TYPES",
    "PARSER_VERSION",
    "DocumentBlock",
    "ParsedDocument",
    "RenderedBlockSpan",
    "RenderedDocument",
    "table_to_markdown",
]
