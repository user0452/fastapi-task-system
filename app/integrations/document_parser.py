"""Compatibility facade for the layout-aware document parser."""

from __future__ import annotations

from pathlib import Path

from app.integrations.complex_document_parser import (
    MAX_DOCUMENT_PAGES,
    MAX_DOCX_MEMBERS,
    MAX_DOCX_UNCOMPRESSED_SIZE,
    MAX_EXTRACTED_TEXT_CHARS,
    OCR_DPI,
    OCR_LANGUAGE,
    SUPPORTED_DOCUMENT_SUFFIXES,
    parse_document_from_bytes,
    parse_document_from_path,
    parse_text_document,
)
from app.integrations.document_model import DocumentBlock, ParsedDocument


def extract_text_from_document(filename: str, content: bytes) -> str:
    """Return the legacy flattened representation for callers not yet block-aware."""

    return parse_document_from_bytes(filename, content).render_for_index().text


def extract_text_from_path(path: str | Path, filename: str | None = None) -> str:
    """Return the legacy flattened representation for a document on disk."""

    return parse_document_from_path(path, filename).render_for_index().text


__all__ = [
    "MAX_DOCUMENT_PAGES",
    "MAX_DOCX_MEMBERS",
    "MAX_DOCX_UNCOMPRESSED_SIZE",
    "MAX_EXTRACTED_TEXT_CHARS",
    "OCR_DPI",
    "OCR_LANGUAGE",
    "SUPPORTED_DOCUMENT_SUFFIXES",
    "DocumentBlock",
    "ParsedDocument",
    "extract_text_from_document",
    "extract_text_from_path",
    "parse_document_from_bytes",
    "parse_document_from_path",
    "parse_text_document",
]
