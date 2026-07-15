from __future__ import annotations

import os
import re
from dataclasses import dataclass

CHUNKER_VERSION = "structure-token-v2"
DEFAULT_TARGET_TOKENS = int(os.getenv("RAG_CHUNK_TARGET_TOKENS", "220"))
DEFAULT_MAX_TOKENS = int(os.getenv("RAG_CHUNK_MAX_TOKENS", "320"))
DEFAULT_OVERLAP_TOKENS = int(os.getenv("RAG_CHUNK_OVERLAP_TOKENS", "40"))

PAGE_MARKER = re.compile(r"^\s*【第\s*(\d+)\s*页】\s*$")
MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PLAIN_HEADING = re.compile(
    r"^\s*(第[0-9一二三四五六七八九十百零]+[章节篇部][^\n]{0,80})\s*$"
)
KB_MARKER = re.compile(
    r"^\s*(?:\*\*)?KB-ID\s*[：:]\s*([A-Za-z0-9][A-Za-z0-9_-]*)(?:\*\*)?\s*$",
    re.IGNORECASE,
)
KB_ID = re.compile(r"\bYQ-[A-Za-z0-9][A-Za-z0-9_-]*\b", re.IGNORECASE)
SENTENCE_END = set("。！？；.!?;")
CJK = re.compile(r"[\u3400-\u9fff]")
ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class _Block:
    text: str
    start: int
    end: int
    page_number: int | None
    heading_path: tuple[str, ...]
    kb_ids: tuple[str, ...]
    atomic: bool


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-free estimate for mixed Chinese/technical text."""
    value = text or ""
    cjk_count = len(CJK.findall(value))
    ascii_count = sum(max(1, (len(word) + 3) // 4) for word in ASCII_WORD.findall(value))
    punctuation_count = sum(1 for char in value if not char.isspace() and not char.isalnum())
    return max(1, cjk_count + ascii_count + (punctuation_count + 3) // 4)


def _clean_heading(value: str) -> str:
    return re.sub(r"\s+#+\s*$", "", value.strip()).strip()


def _document_type(heading_path: tuple[str, ...]) -> str:
    path = " > ".join(heading_path).lower()
    if "附录" in path and "索引" in path:
        return "index"
    if "典型案例" in path or "case" in path:
        return "case"
    if "常见问题" in path or "faq" in path:
        return "faq"
    if "rag评测" in path or "evaluation" in path:
        return "evaluation_guidance"
    return "content"


def _extract_blocks(text: str) -> list[_Block]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines(keepends=True)
    heading_stack: list[str] = []
    page_number: int | None = None
    blocks: list[_Block] = []
    parts: list[str] = []
    part_start = 0
    part_end = 0
    part_page: int | None = None
    part_heading: tuple[str, ...] = ()
    part_ids: list[str] = []
    atomic = False
    offset = 0

    def flush() -> None:
        nonlocal parts, part_start, part_end, part_page, part_heading, part_ids, atomic
        raw_content = "".join(parts)
        leading = len(raw_content) - len(raw_content.lstrip())
        trailing_end = len(raw_content.rstrip())
        content = raw_content[leading:trailing_end]
        if content:
            ids = list(dict.fromkeys(part_ids))
            blocks.append(
                _Block(
                    text=content,
                    start=part_start + leading,
                    end=part_start + trailing_end,
                    page_number=part_page,
                    heading_path=part_heading,
                    kb_ids=tuple(ids),
                    atomic=atomic,
                )
            )
        parts = []
        part_start = 0
        part_end = 0
        part_page = None
        part_heading = ()
        part_ids = []
        atomic = False

    def start_part(start: int, *, is_atomic: bool = False) -> None:
        nonlocal part_start, part_page, part_heading, atomic
        if not parts:
            part_start = start
            part_page = page_number
            part_heading = tuple(heading_stack)
        atomic = atomic or is_atomic

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        line_start = offset
        offset += len(raw_line)

        page_match = PAGE_MARKER.match(stripped)
        if page_match:
            flush()
            page_number = int(page_match.group(1))
            continue

        heading_match = MARKDOWN_HEADING.match(stripped)
        plain_match = PLAIN_HEADING.match(stripped) if not heading_match else None
        if heading_match or plain_match:
            flush()
            if heading_match:
                level = len(heading_match.group(1))
                title = _clean_heading(heading_match.group(2))
            else:
                assert plain_match is not None
                level = 1
                title = _clean_heading(plain_match.group(1))
            heading_stack[level - 1 :] = [title]
            continue

        kb_match = KB_MARKER.match(stripped)
        if kb_match:
            flush()
            start_part(line_start, is_atomic=True)
            part_ids.append(kb_match.group(1).upper())
            parts.append(raw_line)
            part_end = offset
            continue

        inline_ids = [match.upper() for match in KB_ID.findall(stripped)]
        if inline_ids and stripped.startswith(("-", "*", "|")):
            flush()
            start_part(line_start, is_atomic=True)
            part_ids.extend(inline_ids)
            parts.append(raw_line)
            part_end = offset
            flush()
            continue

        if not stripped:
            if parts and atomic:
                parts.append(raw_line)
                part_end = offset
            elif parts:
                flush()
            continue

        start_part(line_start)
        parts.append(raw_line)
        part_end = offset

    flush()
    return blocks


def _best_cut(text: str, start: int, limit: int) -> int:
    hard_end = min(len(text), start + max(1, limit))
    if hard_end >= len(text):
        return len(text)
    minimum = start + max(1, int(limit * 0.55))
    for index in range(hard_end, minimum, -1):
        if text[index - 1] in SENTENCE_END or text[index - 1] == "\n":
            return index
    return hard_end


def _char_budget(text: str, token_budget: int) -> int:
    if estimate_tokens(text) <= token_budget:
        return len(text)
    low, high = 1, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_tokens(text[:middle]) <= token_budget:
            low = middle
        else:
            high = middle - 1
    return max(1, low)


def _split_block(
    block: _Block,
    max_tokens: int,
    overlap_tokens: int,
) -> list[_Block]:
    prefix = " > ".join(block.heading_path)
    if block.atomic and block.kb_ids:
        prefix = f"{prefix}\nKB-ID: {', '.join(block.kb_ids)}".strip()
    content_budget = max(24, max_tokens - estimate_tokens(prefix))
    if estimate_tokens(block.text) <= content_budget:
        return [block]

    pieces: list[_Block] = []
    start = 0
    while start < len(block.text):
        limit = _char_budget(block.text[start:], content_budget)
        end = _best_cut(block.text, start, limit)
        raw_piece = block.text[start:end]
        leading = len(raw_piece) - len(raw_piece.lstrip())
        trailing_end = len(raw_piece.rstrip())
        piece_text = raw_piece[leading:trailing_end]
        if piece_text:
            pieces.append(
                _Block(
                    text=piece_text,
                    start=block.start + start + leading,
                    end=min(block.end, block.start + start + trailing_end),
                    page_number=block.page_number,
                    heading_path=block.heading_path,
                    kb_ids=block.kb_ids,
                    atomic=block.atomic,
                )
            )
        if end >= len(block.text):
            break
        overlap_chars = _char_budget(block.text[:end], overlap_tokens)
        next_start = max(start + 1, end - overlap_chars)
        while next_start < end and block.text[next_start].isspace():
            next_start += 1
        start = next_start
    return pieces


def chunk_document(
    text: str,
    *,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[dict]:
    """Split a document at page, heading, paragraph and KB-ID boundaries."""
    if target_tokens < 24 or max_tokens < target_tokens:
        raise ValueError("invalid RAG chunk token budget")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("invalid RAG chunk overlap")

    source_blocks = _extract_blocks(text)
    expanded: list[_Block] = []
    for block in source_blocks:
        expanded.extend(_split_block(block, max_tokens, overlap_tokens))

    grouped: list[_Block] = []
    pending: list[_Block] = []

    def flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        grouped.append(
            _Block(
                text="\n\n".join(item.text for item in pending).strip(),
                start=pending[0].start,
                end=pending[-1].end,
                page_number=pending[0].page_number,
                heading_path=pending[0].heading_path,
                kb_ids=tuple(dict.fromkeys(kb_id for item in pending for kb_id in item.kb_ids)),
                atomic=False,
            )
        )
        pending = []

    for block in expanded:
        if block.atomic:
            flush_pending()
            grouped.append(block)
            continue
        compatible = (
            not pending
            or (
                pending[-1].page_number == block.page_number
                and pending[-1].heading_path == block.heading_path
            )
        )
        candidate = "\n\n".join([*(item.text for item in pending), block.text])
        candidate_ids = tuple(
            dict.fromkeys(kb_id for item in [*pending, block] for kb_id in item.kb_ids)
        )
        candidate_tokens = estimate_tokens(
            retrieval_text(candidate, block.heading_path, candidate_ids)
        )
        if not compatible or (pending and candidate_tokens > target_tokens):
            flush_pending()
        pending.append(block)
    flush_pending()

    return [
        {
            "chunk_index": index,
            "page_number": block.page_number,
            "heading_path": " > ".join(block.heading_path) or None,
            "kb_ids": list(block.kb_ids),
            "document_type": _document_type(block.heading_path),
            "char_start": block.start,
            "char_end": block.end,
            "chunk_text": block.text,
            "chunker_version": CHUNKER_VERSION,
            "estimated_tokens": estimate_tokens(retrieval_text(block.text, block.heading_path, block.kb_ids)),
        }
        for index, block in enumerate(grouped)
        if block.text.strip()
    ]


def retrieval_text(
    chunk_text: str,
    heading_path: tuple[str, ...] | list[str] | str | None = None,
    kb_ids: tuple[str, ...] | list[str] | None = None,
    document_title: str | None = None,
) -> str:
    if isinstance(heading_path, str):
        heading = heading_path.strip()
    else:
        heading = " > ".join(heading_path or ()).strip()
    parts = [
        (document_title or "").strip(),
        heading,
        f"KB-ID: {', '.join(kb_ids or [])}" if kb_ids else "",
        (chunk_text or "").strip(),
    ]
    return "\n".join(part for part in parts if part)
