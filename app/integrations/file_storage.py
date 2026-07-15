import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.integrations.document_parser import SUPPORTED_DOCUMENT_SUFFIXES

ROOT_DIR = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", ROOT_DIR / "var" / "uploads")).resolve()
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_UPLOAD_SIZE = 100 * 1024 * 1024


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str
    storage_path: str
    mime_type: str
    size: int


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        supported = "、".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise ValueError(f"暂不支持该文件类型，仅支持 {supported}")
    return suffix


def resolve_upload_path(storage_path: str) -> Path:
    candidate = Path(storage_path).resolve()
    candidate.relative_to(UPLOAD_ROOT)
    return candidate


async def save_upload(file: UploadFile, user_id: int) -> StoredUpload:
    suffix = _safe_suffix(file.filename or "")
    user_directory = (UPLOAD_ROOT / str(user_id)).resolve()
    user_directory.relative_to(UPLOAD_ROOT)
    user_directory.mkdir(parents=True, exist_ok=True)
    destination = user_directory / f"{uuid4().hex}{suffix}"
    total = 0

    try:
        with destination.open("wb") as output:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise ValueError("文件过大，当前最大支持 100MB")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if total == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("上传文件不能为空")

    return StoredUpload(
        original_filename=file.filename or destination.name,
        storage_path=str(destination),
        mime_type=file.content_type or "application/octet-stream",
        size=total,
    )


async def read_limited_upload(file: UploadFile) -> bytes:
    chunks = []
    total = 0
    try:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_SIZE:
                raise ValueError("文件过大，当前最大支持 100MB")
            chunks.append(chunk)
    finally:
        await file.close()

    if total == 0:
        raise ValueError("上传文件不能为空")
    return b"".join(chunks)


def read_upload(storage_path: str) -> bytes:
    path = resolve_upload_path(storage_path)
    if path.stat().st_size > MAX_UPLOAD_SIZE:
        raise ValueError("文件过大，当前最大支持 100MB")
    return path.read_bytes()
