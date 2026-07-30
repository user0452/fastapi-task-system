"""Deprecated compatibility import for the v1 document parser."""

from app.integrations.document_parser import (
    MAX_DOCUMENT_PAGES,
    MAX_DOCX_MEMBERS,
    MAX_DOCX_UNCOMPRESSED_SIZE,
    MAX_EXTRACTED_TEXT_CHARS,
    SUPPORTED_DOCUMENT_SUFFIXES,
    DocumentBlock,
    ParsedDocument,
    extract_text_from_document,
    extract_text_from_path,
    parse_document_from_bytes,
    parse_document_from_path,
    parse_text_document,
)

__all__ = [
    "MAX_DOCUMENT_PAGES",
    "MAX_DOCX_MEMBERS",
    "MAX_DOCX_UNCOMPRESSED_SIZE",
    "MAX_EXTRACTED_TEXT_CHARS",
    "SUPPORTED_DOCUMENT_SUFFIXES",
    "DocumentBlock",
    "ParsedDocument",
    "extract_text_from_document",
    "extract_text_from_path",
    "parse_document_from_bytes",
    "parse_document_from_path",
    "parse_text_document",
]
