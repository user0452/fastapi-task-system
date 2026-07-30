"""SSRF-safe validation and HTTP clients for user-provided LLM endpoints."""

from __future__ import annotations

import os
import re
import socket
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from time import monotonic
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

import httpcore
import httpx

from app.core.config import get_settings
from app.core.errors import AppError

_MAX_URL_LENGTH = 2048
_HTTPS_POLICY_ENV = "USER_LLM_REQUIRE_HTTPS"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_MAX_RESOLVED_ADDRESSES = 16
_LEGACY_NUMERIC_HOST = re.compile(
    r"(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+))*"
)


@dataclass(frozen=True, slots=True)
class ValidatedLlmEndpoint:
    """A normalized endpoint and the public IPs approved for this connection."""

    base_url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _invalid_url(message: str = "API 地址必须是有效的 http 或 https URL") -> AppError:
    return AppError(message, 422, "LLM_BASE_URL_INVALID")


def _https_required() -> bool:
    configured = str(os.getenv(_HTTPS_POLICY_ENV, "") or "").strip().lower()
    if configured:
        if configured in _TRUE_VALUES:
            return True
        if configured in _FALSE_VALUES:
            return False
        raise RuntimeError(
            f"{_HTTPS_POLICY_ENV} 必须是 true/false、1/0、yes/no 或 on/off"
        )
    return get_settings().environment == "production"


def _normalize_hostname(hostname: str) -> str:
    candidate = hostname.rstrip(".").lower()
    if not candidate or "%" in candidate:
        raise _invalid_url()
    try:
        ip_address(candidate)
    except ValueError:
        if _LEGACY_NUMERIC_HOST.fullmatch(candidate):
            raise AppError(
                "模型 API 地址不能使用非标准数字 IP 表示法",
                422,
                "LLM_BASE_URL_FORBIDDEN",
            ) from None
    try:
        normalized = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise _invalid_url() from exc
    if len(normalized) > 253 or any(
        not label or len(label) > 63 for label in normalized.split(".")
    ):
        raise _invalid_url()
    return normalized


def _normalize_url(value: str) -> tuple[str, str, int]:
    raw = str(value or "").strip().rstrip("/")
    if (
        not raw
        or len(raw) > _MAX_URL_LENGTH
        or "\\" in raw
        or any(ord(character) <= 0x20 or ord(character) == 0x7F for character in raw)
    ):
        raise _invalid_url()

    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise _invalid_url() from exc

    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise _invalid_url()
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise _invalid_url(
            "API 地址不能包含账号、密码、查询参数或片段",
        )
    if _https_required() and parsed.scheme != "https":
        raise AppError(
            "当前环境要求模型 API 使用 HTTPS",
            422,
            "LLM_BASE_URL_HTTPS_REQUIRED",
        )

    hostname = _normalize_hostname(parsed.hostname)
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise AppError(
            "模型 API 地址不能指向本机、内网或保留网络",
            422,
            "LLM_BASE_URL_FORBIDDEN",
        )

    effective_port = port or (443 if parsed.scheme == "https" else 80)
    if not 1 <= effective_port <= 65535:
        raise _invalid_url()

    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = host_for_url if effective_port == default_port else f"{host_for_url}:{effective_port}"
    normalized = urlunsplit(
        (parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""),
    )
    return normalized, hostname, effective_port


def _assert_public_address(address: IPv4Address | IPv6Address) -> None:
    mapped = address.ipv4_mapped if isinstance(address, IPv6Address) else None
    candidate = mapped or address
    if (
        not candidate.is_global
        or candidate.is_private
        or candidate.is_loopback
        or candidate.is_link_local
        or candidate.is_reserved
        or candidate.is_multicast
        or candidate.is_unspecified
    ):
        raise AppError(
            "模型 API 地址不能指向本机、内网或保留网络",
            422,
            "LLM_BASE_URL_FORBIDDEN",
        )


def _resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    try:
        literal = ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        _assert_public_address(literal)
        return (str(literal),)

    try:
        records = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except OSError as exc:
        raise AppError(
            "无法解析模型 API 地址",
            422,
            "LLM_BASE_URL_UNRESOLVED",
        ) from exc

    addresses: list[str] = []
    for _family, _socktype, _proto, _canonical_name, sockaddr in records:
        raw_address = str(sockaddr[0]).split("%", 1)[0]
        try:
            resolved = ip_address(raw_address)
        except ValueError as exc:
            raise AppError(
                "模型 API 地址解析结果无效",
                422,
                "LLM_BASE_URL_UNRESOLVED",
            ) from exc
        _assert_public_address(resolved)
        canonical = str(resolved)
        if canonical not in addresses:
            addresses.append(canonical)
            if len(addresses) > _MAX_RESOLVED_ADDRESSES:
                raise AppError(
                    "模型 API 地址解析结果过多",
                    422,
                    "LLM_BASE_URL_UNRESOLVED",
                )

    if not addresses:
        raise AppError(
            "无法解析模型 API 地址",
            422,
            "LLM_BASE_URL_UNRESOLVED",
        )
    return tuple(addresses)


def validate_user_llm_endpoint(value: str) -> ValidatedLlmEndpoint:
    """Normalize a URL, resolve it, and reject every non-public result."""

    base_url, hostname, port = _normalize_url(value)
    return ValidatedLlmEndpoint(
        base_url=base_url,
        hostname=hostname,
        port=port,
        addresses=_resolve_public_addresses(hostname, port),
    )


def _matches_endpoint(host: str, port: int, endpoint: ValidatedLlmEndpoint) -> bool:
    return host.rstrip(".").lower() == endpoint.hostname and port == endpoint.port


class _PinnedSyncBackend(httpcore.NetworkBackend):
    def __init__(
        self,
        endpoint: ValidatedLlmEndpoint,
        backend: httpcore.NetworkBackend | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._backend = backend or httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        if not _matches_endpoint(host, port, self._endpoint):
            raise httpcore.ConnectError("Blocked connection outside validated LLM endpoint")

        last_error: Exception | None = None
        started = monotonic()
        address_count = len(self._endpoint.addresses)
        for index, address in enumerate(self._endpoint.addresses):
            attempt_timeout = timeout
            if timeout is not None:
                remaining = max(0.0, timeout - (monotonic() - started))
                if remaining <= 0:
                    last_error = httpcore.ConnectTimeout(
                        "Validated LLM endpoint connection timed out"
                    )
                    break
                attempt_timeout = remaining / max(1, address_count - index)
            try:
                return self._backend.connect_tcp(
                    address,
                    port,
                    timeout=attempt_timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise httpcore.ConnectError("Unable to connect to validated LLM endpoint") from last_error

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("Unix sockets are not allowed for user LLM endpoints")

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


class _PinnedAsyncBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        endpoint: ValidatedLlmEndpoint,
        backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._backend = backend or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if not _matches_endpoint(host, port, self._endpoint):
            raise httpcore.ConnectError("Blocked connection outside validated LLM endpoint")

        last_error: Exception | None = None
        started = monotonic()
        address_count = len(self._endpoint.addresses)
        for index, address in enumerate(self._endpoint.addresses):
            attempt_timeout = timeout
            if timeout is not None:
                remaining = max(0.0, timeout - (monotonic() - started))
                if remaining <= 0:
                    last_error = httpcore.ConnectTimeout(
                        "Validated LLM endpoint connection timed out"
                    )
                    break
                attempt_timeout = remaining / max(1, address_count - index)
            try:
                return await self._backend.connect_tcp(
                    address,
                    port,
                    timeout=attempt_timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise httpcore.ConnectError("Unable to connect to validated LLM endpoint") from last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("Unix sockets are not allowed for user LLM endpoints")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class _PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(self, endpoint: ValidatedLlmEndpoint) -> None:
        super().__init__(trust_env=False, retries=0)
        setattr(self._pool, "_network_backend", _PinnedSyncBackend(endpoint))


class _PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self, endpoint: ValidatedLlmEndpoint) -> None:
        super().__init__(trust_env=False, retries=0)
        setattr(self._pool, "_network_backend", _PinnedAsyncBackend(endpoint))


def create_pinned_http_client(
    endpoint: ValidatedLlmEndpoint,
    *,
    timeout: float,
) -> httpx.Client:
    return httpx.Client(
        transport=_PinnedHTTPTransport(endpoint),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    )


def create_pinned_async_http_client(
    endpoint: ValidatedLlmEndpoint,
    *,
    timeout: float,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=_PinnedAsyncHTTPTransport(endpoint),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    )


__all__ = [
    "ValidatedLlmEndpoint",
    "create_pinned_async_http_client",
    "create_pinned_http_client",
    "validate_user_llm_endpoint",
]
