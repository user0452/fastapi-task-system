from __future__ import annotations

import bcrypt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password_and_rehash(password: str, stored_hash: str) -> tuple[bool, str | None]:
    if stored_hash.startswith("$argon2id$"):
        try:
            valid = bool(_PASSWORD_HASHER.verify(stored_hash, password))
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False, None
        replacement = hash_password(password) if _PASSWORD_HASHER.check_needs_rehash(stored_hash) else None
        return bool(valid), replacement

    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        password_bytes = password.encode("utf-8")
        if len(password_bytes) > 72:
            return False, None
        try:
            valid = bcrypt.checkpw(password_bytes, stored_hash.encode("utf-8"))
        except ValueError:
            return False, None
        return valid, hash_password(password) if valid else None

    return False, None


def verify_password(password: str, stored_hash: str) -> bool:
    valid, _ = verify_password_and_rehash(password, stored_hash)
    return valid


__all__ = ["hash_password", "verify_password", "verify_password_and_rehash"]
