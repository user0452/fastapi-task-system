"""Bounded, path-first parsing for supported course material documents."""

import re
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.document import Document as DocumentType
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

SUPPORTED_DOCUMENT_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}
MAX_DOCUMENT_PAGES = 2_000
MAX_EXTRACTED_TEXT_CHARS = 12_000_000
MAX_DOCX_UNCOMPRESSED_SIZE = 256 * 1024 * 1024
MAX_DOCX_MEMBERS = 20_000


def _ensure_text_size(length: int) -> None:
    if length > MAX_EXTRACTED_TEXT_CHARS:
        raise ValueError(
            f"资料解析文本超过 {MAX_EXTRACTED_TEXT_CHARS // 1_000_000}M 字符，"
            "请拆分后上传，避免索引任务占用过多内存"
        )


def _bounded_text(text: str) -> str:
    _ensure_text_size(len(text))
    return text


def _decode_text_file(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("gbk", errors="ignore")


def _extract_pdf_reader(reader: PdfReader) -> str:
    if len(reader.pages) > MAX_DOCUMENT_PAGES:
        raise ValueError(f"PDF 页数超过 {MAX_DOCUMENT_PAGES} 页，请拆分后上传")

    texts: list[str] = []
    total_chars = 0
    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            continue
        rendered = f"【第 {index} 页】\n{page_text.strip()}"
        total_chars += len(rendered)
        _ensure_text_size(total_chars)
        texts.append(rendered)
    return "\n\n".join(texts)


def _extract_pdf_text(content: bytes) -> str:
    return _extract_pdf_reader(PdfReader(BytesIO(content)))


def _extract_docx_document(document: DocumentType) -> str:
    lines: list[str] = []
    total_chars = 0
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            style_name = str(block.style.name if block.style else "").strip()
            heading = re.match(r"Heading\s+(\d+)$", style_name, re.IGNORECASE)
            if heading:
                level = max(1, min(6, int(heading.group(1))))
                rendered = f"{'#' * level} {text}"
            elif style_name.lower() == "title":
                rendered = f"# {text}"
            else:
                rendered = text
            total_chars += len(rendered)
            _ensure_text_size(total_chars)
            lines.append(rendered)
            continue

        if isinstance(block, Table):
            for row in block.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                if not any(cells):
                    continue
                rendered = "| " + " | ".join(cells) + " |"
                total_chars += len(rendered)
                _ensure_text_size(total_chars)
                lines.append(rendered)
    return "\n".join(lines)


def _extract_docx_text(content: bytes) -> str:
    return _extract_docx_document(Document(BytesIO(content)))


def _validate_suffix(filename: str | Path) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise ValueError(f"暂不支持 {suffix or '无扩展名'} 文件，仅支持 txt、md、pdf、docx")
    return suffix


def _ensure_non_empty(text: str) -> str:
    text = _bounded_text(text.replace("\ufeff", "").strip())
    if not text:
        raise ValueError(
            "未能从文件中解析出文本；扫描版或图片型 PDF 当前暂不支持 OCR"
        )
    return text


def extract_text_from_document(filename: str, content: bytes) -> str:
    """Compatibility bytes API; path parsing is preferred for uploaded files."""
    suffix = _validate_suffix(filename)
    if suffix in {".txt", ".md"}:
        text = _decode_text_file(content)
    elif suffix == ".pdf":
        text = _extract_pdf_text(content)
    else:
        text = _extract_docx_text(content)
    return _ensure_non_empty(text)


def _validate_docx_archive(path: Path) -> None:
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_DOCX_MEMBERS:
                raise ValueError("DOCX 内部文件数量异常，已拒绝解析")
            if sum(item.file_size for item in members) > MAX_DOCX_UNCOMPRESSED_SIZE:
                raise ValueError("DOCX 解压后体积过大，请拆分后上传")
            names = {item.filename for item in members}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("文件内容不是有效的 DOCX 文档")
    except BadZipFile as exc:
        raise ValueError("文件内容不是有效的 DOCX 文档") from exc


def extract_text_from_path(path: str | Path, filename: str | None = None) -> str:
    """Parse from disk without copying a large upload into a bytes buffer."""
    source = Path(path)
    suffix = _validate_suffix(filename or source.name)
    if suffix in {".txt", ".md"}:
        with source.open("rb") as stream:
            prefix = stream.read(4)
        if b"\x00" in prefix:
            raise ValueError("文本文件包含二进制内容，已拒绝解析")
        try:
            with source.open("r", encoding="utf-8-sig") as stream:
                text = stream.read(MAX_EXTRACTED_TEXT_CHARS + 1)
        except UnicodeDecodeError:
            with source.open("r", encoding="gbk", errors="ignore") as stream:
                text = stream.read(MAX_EXTRACTED_TEXT_CHARS + 1)
    elif suffix == ".pdf":
        with source.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ValueError("文件内容不是有效的 PDF 文档")
        text = _extract_pdf_reader(PdfReader(str(source)))
    else:
        _validate_docx_archive(source)
        text = _extract_docx_document(Document(str(source)))
    return _ensure_non_empty(text)


__all__ = [
    "MAX_DOCUMENT_PAGES",
    "MAX_DOCX_MEMBERS",
    "MAX_DOCX_UNCOMPRESSED_SIZE",
    "MAX_EXTRACTED_TEXT_CHARS",
    "SUPPORTED_DOCUMENT_SUFFIXES",
    "extract_text_from_document",
    "extract_text_from_path",
]
