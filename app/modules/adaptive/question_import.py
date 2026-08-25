"""Small, auditable question-bank file parser for JSON, JSONL, Markdown and TXT."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_IMPORT_SUFFIXES = {".json", ".jsonl", ".md", ".markdown", ".txt"}
MAX_IMPORT_QUESTIONS = 500


@dataclass(frozen=True)
class ParsedQuestion:
    content: str
    answer: str | None
    rubric: str | None
    explanation: str | None
    question_type: str
    options: list[str]
    tolerance: float | None
    difficulty: str
    source_url: str | None
    raw_provenance: dict[str, Any]
    parse_status: str
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "answer": self.answer or "",
            "rubric": self.rubric,
            "explanation": self.explanation,
            "question_type": self.question_type,
            "options": self.options,
            "tolerance": self.tolerance,
            "difficulty": self.difficulty,
            "source_url": self.source_url,
            "raw_provenance": self.raw_provenance,
            "parse_status": self.parse_status,
            "parse_error": self.parse_error,
        }


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _difficulty(value: Any) -> str:
    normalized = _clean(value, 20).casefold()
    return {
        "简单": "easy",
        "容易": "easy",
        "easy": "easy",
        "简单题": "easy",
        "困难": "hard",
        "难": "hard",
        "hard": "hard",
        "困难题": "hard",
    }.get(normalized, "medium")


def _question_type(value: Any, options: list[str]) -> str:
    normalized = _clean(value, 30).casefold()
    if normalized in {"single_choice", "choice", "选择题", "单选", "multiple_choice", "多选"}:
        return "multiple_choice"
    if normalized in {"true_false", "判断", "判断题"}:
        return "true_false"
    if normalized in {"calculation", "计算", "计算题"}:
        return "calculation"
    if normalized in {"scenario", "情境", "场景题"}:
        return "scenario"
    if normalized in {"essay", "论述", "论述题"}:
        return "essay"
    if options:
        return "multiple_choice"
    return "short_answer"


def _options(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean(item, 500) for item in value if _clean(item, 500)][:8]


def _from_mapping(raw: dict[str, Any], index: int, filename: str) -> ParsedQuestion:
    content = _clean(raw.get("content") or raw.get("question") or raw.get("prompt") or raw.get("题目"), 8000)
    answer = _clean(
        raw.get("answer")
        or raw.get("reference_answer")
        or raw.get("correct_answer")
        or raw.get("solution")
        or raw.get("答案"),
        5000,
    ) or None
    options = _options(raw.get("options") or raw.get("choices") or raw.get("选项"))
    question_type = _question_type(raw.get("question_type") or raw.get("type") or raw.get("题型"), options)
    parse_status = "ready"
    parse_error = None
    if len(content) < 8:
        parse_status, parse_error = "invalid", "题目内容少于 8 个字符"
    elif answer is None:
        parse_status, parse_error = "needs_review", "缺少参考答案"
    elif question_type == "multiple_choice" and len(options) < 2:
        parse_status, parse_error = "needs_review", "选择题缺少至少两个选项"
    tolerance = None
    raw_tolerance = raw.get("tolerance") or raw.get("容差")
    if raw_tolerance not in (None, ""):
        try:
            tolerance = max(0.0, float(raw_tolerance))
        except (TypeError, ValueError):
            parse_status, parse_error = "needs_review", "计算题容差不是有效数字"
    return ParsedQuestion(
        content=content,
        answer=answer,
        rubric=_clean(raw.get("rubric") or raw.get("评分标准") or raw.get("rubric_text"), 5000) or None,
        explanation=_clean(raw.get("explanation") or raw.get("解析") or raw.get("explain"), 5000) or None,
        question_type=question_type,
        options=options,
        tolerance=tolerance,
        difficulty=_difficulty(raw.get("difficulty") or raw.get("难度")),
        source_url=_clean(raw.get("source_url") or raw.get("url") or raw.get("来源"), 1000) or None,
        raw_provenance={
            "filename": filename[:255],
            "line_or_index": index,
            "raw_keys": sorted(str(key)[:80] for key in raw.keys())[:30],
        },
        parse_status=parse_status,
        parse_error=parse_error,
    )


def _parse_structured(text: str, suffix: str, filename: str) -> list[ParsedQuestion]:
    if suffix == ".jsonl":
        rows: list[Any] = []
        for index, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"content": line, "_parse_error": f"第 {index} 行不是有效 JSON"})
    else:
        payload = json.loads(text)
        if isinstance(payload, dict):
            rows = payload.get("questions") or payload.get("items") or payload.get("题目") or []
        else:
            rows = payload
    if not isinstance(rows, list):
        raise ValueError("JSON 题库必须是数组，或对象中的 questions/items 数组")
    result: list[ParsedQuestion] = []
    for index, raw in enumerate(rows[:MAX_IMPORT_QUESTIONS], start=1):
        if not isinstance(raw, dict):
            result.append(
                ParsedQuestion(
                    content=_clean(raw, 8000), answer=None, rubric=None, explanation=None,
                    question_type="short_answer", options=[], difficulty="medium",
                    tolerance=None,
                    source_url=None, raw_provenance={"filename": filename, "line_or_index": index},
                    parse_status="invalid", parse_error="题目条目必须是对象",
                )
            )
            continue
        parsed = _from_mapping(raw, index, filename)
        custom_error = raw.get("_parse_error")
        if custom_error:
            parsed = ParsedQuestion(**{**parsed.__dict__, "parse_status": "invalid", "parse_error": str(custom_error)[:500]})
        result.append(parsed)
    return result


_FIELD_LABELS = {
    "question": "content",
    "q": "content",
    "题目": "content",
    "问题": "content",
    "answer": "answer",
    "a": "answer",
    "答案": "answer",
    "参考答案": "answer",
    "rubric": "rubric",
    "评分标准": "rubric",
    "explanation": "explanation",
    "解析": "explanation",
    "difficulty": "difficulty",
    "难度": "difficulty",
    "type": "question_type",
    "question_type": "question_type",
    "题型": "question_type",
    "source_url": "source_url",
    "来源": "source_url",
    "tolerance": "tolerance",
    "容差": "tolerance",
}


def _parse_text_blocks(text: str, filename: str) -> list[ParsedQuestion]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]
    result: list[ParsedQuestion] = []
    for index, block in enumerate(blocks[:MAX_IMPORT_QUESTIONS], start=1):
        fields: dict[str, Any] = {}
        current: str | None = None
        options: list[str] = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            option_match = re.match(r"^(?:[-*]\s*)?([A-Ha-h])\s*[.)、:]\s*(.+)$", line)
            if option_match:
                options.append(option_match.group(2).strip())
                continue
            label_match = re.match(r"^(?:#+\s*)?([^:：]{1,20})\s*[:：]\s*(.*)$", line)
            if label_match:
                label = label_match.group(1).strip().casefold()
                field = _FIELD_LABELS.get(label)
                if field:
                    current = field
                    fields[field] = label_match.group(2).strip()
                    continue
            if current:
                fields[current] = f"{fields.get(current, '')}\n{line}".strip()
            elif "content" not in fields:
                fields["content"] = line.lstrip("# ")
            else:
                fields["answer"] = f"{fields.get('answer', '')}\n{line}".strip()
        fields["options"] = options
        result.append(_from_mapping(fields, index, filename))
    return result


def parse_question_bank(content: bytes, filename: str) -> list[ParsedQuestion]:
    suffix = Path(filename or "").suffix.casefold()
    if suffix not in SUPPORTED_IMPORT_SUFFIXES:
        raise ValueError(f"题库文件格式不支持，仅支持 {', '.join(sorted(SUPPORTED_IMPORT_SUFFIXES))}")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("题库文件必须是 UTF-8 文本") from exc
    if not text.strip():
        raise ValueError("题库文件为空")
    if suffix in {".json", ".jsonl"}:
        try:
            result = _parse_structured(text, suffix, filename)
        except json.JSONDecodeError as exc:
            raise ValueError(f"题库 JSON 解析失败：第 {exc.lineno} 行") from exc
    else:
        result = _parse_text_blocks(text, filename)
    if not result:
        raise ValueError("没有解析出题目")
    return result


def normalize_and_deduplicate(items: list[ParsedQuestion]) -> tuple[list[ParsedQuestion], int]:
    seen: set[str] = set()
    deduped: list[ParsedQuestion] = []
    duplicates = 0
    for item in items[:MAX_IMPORT_QUESTIONS]:
        key = re.sub(r"\W+", "", item.content.casefold())
        if not key or key in seen:
            duplicates += 1
            continue
        seen.add(key)
        deduped.append(item)
    return deduped, duplicates


__all__ = [
    "MAX_IMPORT_QUESTIONS",
    "ParsedQuestion",
    "SUPPORTED_IMPORT_SUFFIXES",
    "normalize_and_deduplicate",
    "parse_question_bank",
]
