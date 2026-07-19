"""Small encryption boundary for user-supplied application secrets."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    secret_key = get_settings().secret_key
    if not secret_key:
        raise RuntimeError("SECRET_KEY 未配置，无法安全保存 API 密钥")
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return "v1:" + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value.startswith("v1:"):
        raise RuntimeError("不支持的密钥加密版本")
    try:
        return _fernet().decrypt(value[3:].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise RuntimeError("API 密钥无法解密，请重新保存配置") from exc


__all__ = ["decrypt_secret", "encrypt_secret"]
