"""Per-user OpenAI-compatible model configuration and connectivity checks."""

from __future__ import annotations

from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import get_settings
from app.core.database import get_cursor
from app.core.errors import AppError
from app.core.secret_crypto import decrypt_secret, encrypt_secret


def normalize_openai_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AppError(
            "API 地址必须是有效的 http 或 https URL",
            422,
            "LLM_BASE_URL_INVALID",
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AppError(
            "API 地址不能包含账号、密码、查询参数或片段",
            422,
            "LLM_BASE_URL_INVALID",
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _load_config(user_id: int) -> dict | None:
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT user_id, provider, enabled, base_url, model,
                   api_key_ciphertext, api_key_hint, created_at, updated_at
            FROM user_llm_configs
            WHERE user_id = %s
            """,
            (user_id,),
        )
        return cursor.fetchone()


def _public_config(row: dict | None) -> dict:
    settings = get_settings()
    server_default_available = bool(
        settings.deepseek_api_key
        and settings.deepseek_base_url
        and settings.deepseek_model
    )
    if row is None:
        return {
            "provider": "openai_compatible",
            "configured": False,
            "enabled": False,
            "base_url": "",
            "model": "",
            "has_api_key": False,
            "api_key_hint": None,
            "active_source": "server_default",
            "server_default_available": server_default_available,
            "server_default_model": settings.deepseek_model if server_default_available else None,
            "updated_at": None,
        }
    enabled = bool(row["enabled"])
    return {
        "provider": "openai_compatible",
        "configured": True,
        "enabled": enabled,
        "base_url": row["base_url"],
        "model": row["model"],
        "has_api_key": bool(row["api_key_ciphertext"]),
        "api_key_hint": row["api_key_hint"],
        "active_source": "user" if enabled else "server_default",
        "server_default_available": server_default_available,
        "server_default_model": settings.deepseek_model if server_default_available else None,
        "updated_at": row["updated_at"],
    }


def get_user_llm_config(user_id: int) -> dict:
    return _public_config(_load_config(user_id))


def save_user_llm_config(
    user_id: int,
    *,
    enabled: bool,
    base_url: str,
    model: str,
    api_key: str | None,
) -> dict:
    normalized_url = normalize_openai_base_url(base_url)
    normalized_model = str(model or "").strip()
    if not normalized_model:
        raise AppError("模型名称不能为空", 422, "LLM_MODEL_REQUIRED")

    current = _load_config(user_id)
    secret = str(api_key or "").strip()
    if secret:
        ciphertext = encrypt_secret(secret)
        hint = f"••••{secret[-4:]}"
    elif current is not None:
        ciphertext = current["api_key_ciphertext"]
        hint = current["api_key_hint"]
    else:
        raise AppError("首次配置时必须填写 API Key", 422, "LLM_API_KEY_REQUIRED")

    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO user_llm_configs
                (user_id, provider, enabled, base_url, model, api_key_ciphertext, api_key_hint)
            VALUES (%s, 'openai_compatible', %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                enabled = VALUES(enabled),
                base_url = VALUES(base_url),
                model = VALUES(model),
                api_key_ciphertext = VALUES(api_key_ciphertext),
                api_key_hint = VALUES(api_key_hint)
            """,
            (user_id, enabled, normalized_url, normalized_model, ciphertext, hint),
        )
    return get_user_llm_config(user_id)


def delete_user_llm_config(user_id: int) -> None:
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM user_llm_configs WHERE user_id = %s", (user_id,))


def get_enabled_user_llm_config(user_id: int) -> dict | None:
    row = _load_config(user_id)
    if row is None or not bool(row["enabled"]):
        return None
    try:
        api_key = decrypt_secret(row["api_key_ciphertext"])
    except RuntimeError as exc:
        raise AppError(str(exc), 409, "LLM_API_KEY_DECRYPT_FAILED") from exc
    return {
        "base_url": row["base_url"],
        "model": row["model"],
        "api_key": api_key,
    }


def _probe_openai_compatible(config: dict) -> dict:
    endpoint = f"{config['base_url'].rstrip('/')}/chat/completions"
    started = perf_counter()
    try:
        with httpx.Client(
            timeout=min(30.0, max(3.0, get_settings().llm_timeout_seconds)),
            follow_redirects=False,
        ) as client:
            response = client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config["model"],
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 2,
                    "temperature": 0,
                },
            )
    except httpx.RequestError as exc:
        raise AppError(
            "无法连接该 API 地址，请检查地址和网络",
            422,
            "LLM_CONNECTION_FAILED",
        ) from exc
    if response.status_code >= 400:
        raise AppError(
            f"API 返回 HTTP {response.status_code}，请检查密钥、模型和地址",
            422,
            "LLM_CONNECTION_FAILED",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(
            "API 未返回 OpenAI 兼容的 JSON 响应",
            422,
            "LLM_RESPONSE_INVALID",
        ) from exc
    if not isinstance(payload.get("choices"), list):
        raise AppError(
            "API 响应缺少 OpenAI 兼容的 choices 字段",
            422,
            "LLM_RESPONSE_INVALID",
        )
    return {
        "ok": True,
        "model": config["model"],
        "latency_ms": max(1, round((perf_counter() - started) * 1000)),
    }


def test_user_llm_config(
    user_id: int,
    *,
    base_url: str,
    model: str,
    api_key: str | None,
) -> dict:
    current = _load_config(user_id)
    secret = str(api_key or "").strip()
    if not secret and current is not None:
        try:
            secret = decrypt_secret(current["api_key_ciphertext"])
        except RuntimeError as exc:
            raise AppError(str(exc), 409, "LLM_API_KEY_DECRYPT_FAILED") from exc
    if not secret:
        raise AppError("测试连接前请填写 API Key", 422, "LLM_API_KEY_REQUIRED")
    config = {
        "base_url": normalize_openai_base_url(base_url),
        "model": str(model or "").strip(),
        "api_key": secret,
    }
    if not config["model"]:
        raise AppError("模型名称不能为空", 422, "LLM_MODEL_REQUIRED")
    return _probe_openai_compatible(config)


__all__ = [
    "delete_user_llm_config",
    "get_enabled_user_llm_config",
    "get_user_llm_config",
    "normalize_openai_base_url",
    "save_user_llm_config",
    "test_user_llm_config",
]
