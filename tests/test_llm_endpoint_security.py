import asyncio
import socket
from types import SimpleNamespace

import httpcore
import pytest

from app.core.errors import AppError
from app.integrations.llm import endpoint_security
from app.integrations.llm.endpoint_security import (
    ValidatedLlmEndpoint,
    _PinnedAsyncBackend,
    _PinnedSyncBackend,
    validate_user_llm_endpoint,
)
from app.modules.account import llm_config_service


def _dns_record(address: str, port: int = 443):
    if ":" in address:
        return (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (address, port, 0, 0),
        )
    return (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        (address, port),
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/v1",
        "http://127.1/v1",
        "http://2130706433/v1",
        "http://0.0.0.0/v1",
        "http://10.0.0.1/v1",
        "http://100.64.0.1/v1",
        "http://169.254.169.254/latest/meta-data",
        "http://224.0.0.1/v1",
        "http://240.0.0.1/v1",
        "http://[::]/v1",
        "http://[::1]/v1",
        "http://[::ffff:127.0.0.1]/v1",
        "http://[fc00::1]/v1",
        "http://[fe80::1]/v1",
        "http://[ff02::1]/v1",
        "http://localhost/v1",
        "http://api.localhost/v1",
    ],
)
def test_private_and_special_ip_forms_are_rejected(url):
    with pytest.raises(AppError) as exc_info:
        validate_user_llm_endpoint(url)

    assert exc_info.value.error_code == "LLM_BASE_URL_FORBIDDEN"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "//example.com/v1",
        "https://user@example.com/v1",
        "https://user:secret@example.com/v1",
        "https://example.com/v1?target=http://127.0.0.1",
        "https://example.com/v1#fragment",
        "https://example.com:99999/v1",
        "https://example.com\\@127.0.0.1/v1",
        "https://%65xample.com/v1",
        "https://example.com/line\nbreak",
    ],
)
def test_malformed_or_ambiguous_urls_are_rejected(url):
    with pytest.raises(AppError) as exc_info:
        validate_user_llm_endpoint(url)

    assert exc_info.value.error_code == "LLM_BASE_URL_INVALID"


def test_public_ipv4_and_ipv6_literals_are_allowed(monkeypatch):
    monkeypatch.setenv("USER_LLM_REQUIRE_HTTPS", "false")

    ipv4 = validate_user_llm_endpoint("http://8.8.8.8:8080/v1/")
    ipv6 = validate_user_llm_endpoint("https://[2606:4700:4700::1111]/v1/")

    assert ipv4 == ValidatedLlmEndpoint(
        base_url="http://8.8.8.8:8080/v1",
        hostname="8.8.8.8",
        port=8080,
        addresses=("8.8.8.8",),
    )
    assert ipv6 == ValidatedLlmEndpoint(
        base_url="https://[2606:4700:4700::1111]/v1",
        hostname="2606:4700:4700::1111",
        port=443,
        addresses=("2606:4700:4700::1111",),
    )


def test_hostname_resolution_requires_every_result_to_be_public(monkeypatch):
    monkeypatch.setattr(
        endpoint_security.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            _dns_record("8.8.8.8"),
            _dns_record("2606:4700:4700::1111"),
        ],
    )

    endpoint = validate_user_llm_endpoint("https://API.Example.COM./v1/")

    assert endpoint.base_url == "https://api.example.com/v1"
    assert endpoint.hostname == "api.example.com"
    assert endpoint.addresses == ("8.8.8.8", "2606:4700:4700::1111")


def test_hostname_is_rejected_when_one_dns_result_is_private(monkeypatch):
    monkeypatch.setattr(
        endpoint_security.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            _dns_record("8.8.8.8"),
            _dns_record("127.0.0.1"),
        ],
    )

    with pytest.raises(AppError) as exc_info:
        validate_user_llm_endpoint("https://gateway.example/v1")

    assert exc_info.value.error_code == "LLM_BASE_URL_FORBIDDEN"


def test_unresolvable_hostname_returns_controlled_error(monkeypatch):
    def fail_resolution(*_args, **_kwargs):
        raise socket.gaierror("not found")

    monkeypatch.setattr(endpoint_security.socket, "getaddrinfo", fail_resolution)

    with pytest.raises(AppError) as exc_info:
        validate_user_llm_endpoint("https://missing.example/v1")

    assert exc_info.value.error_code == "LLM_BASE_URL_UNRESOLVED"


def test_production_requires_https_by_default_but_policy_is_configurable(monkeypatch):
    monkeypatch.delenv("USER_LLM_REQUIRE_HTTPS", raising=False)
    monkeypatch.setattr(
        endpoint_security,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )

    with pytest.raises(AppError) as exc_info:
        validate_user_llm_endpoint("http://8.8.8.8/v1")
    assert exc_info.value.error_code == "LLM_BASE_URL_HTTPS_REQUIRED"

    monkeypatch.setenv("USER_LLM_REQUIRE_HTTPS", "false")
    assert validate_user_llm_endpoint("http://8.8.8.8/v1").base_url == "http://8.8.8.8/v1"


def test_https_policy_rejects_misspelled_boolean(monkeypatch):
    monkeypatch.setenv("USER_LLM_REQUIRE_HTTPS", "treu")

    with pytest.raises(RuntimeError, match="USER_LLM_REQUIRE_HTTPS"):
        validate_user_llm_endpoint("https://8.8.8.8/v1")


class _FakeSyncBackend:
    def __init__(self, *, fail_first: bool = False):
        self.calls = []
        self.fail_first = fail_first
        self.stream = object()

    def connect_tcp(self, host, port, **kwargs):
        self.calls.append((host, port, kwargs))
        if self.fail_first and len(self.calls) == 1:
            raise httpcore.ConnectError("first address failed")
        return self.stream

    def sleep(self, _seconds):
        return None


def test_sync_backend_connects_only_to_pinned_addresses_and_blocks_redirect_hosts():
    endpoint = ValidatedLlmEndpoint(
        base_url="https://gateway.example/v1",
        hostname="gateway.example",
        port=443,
        addresses=("8.8.8.8", "1.1.1.1"),
    )
    delegate = _FakeSyncBackend(fail_first=True)
    backend = _PinnedSyncBackend(endpoint, delegate)

    stream = backend.connect_tcp("gateway.example", 443, timeout=5)

    assert stream is delegate.stream
    assert [call[:2] for call in delegate.calls] == [("8.8.8.8", 443), ("1.1.1.1", 443)]
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("127.0.0.1", 443)
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("gateway.example", 8443)


def test_sync_backend_falls_back_after_connect_timeout():
    endpoint = ValidatedLlmEndpoint(
        base_url="https://gateway.example/v1",
        hostname="gateway.example",
        port=443,
        addresses=("2606:4700:4700::1111", "8.8.8.8"),
    )

    class TimeoutThenSuccessBackend(_FakeSyncBackend):
        def connect_tcp(self, host, port, **kwargs):
            self.calls.append((host, port, kwargs))
            if len(self.calls) == 1:
                raise httpcore.ConnectTimeout("ipv6 timeout")
            return self.stream

    delegate = TimeoutThenSuccessBackend()
    backend = _PinnedSyncBackend(endpoint, delegate)

    assert backend.connect_tcp("gateway.example", 443, timeout=5) is delegate.stream
    assert [call[:2] for call in delegate.calls] == [
        ("2606:4700:4700::1111", 443),
        ("8.8.8.8", 443),
    ]
    assert delegate.calls[0][2]["timeout"] <= 2.5
    assert delegate.calls[1][2]["timeout"] <= 5


class _FakeAsyncBackend:
    def __init__(self):
        self.calls = []
        self.stream = object()

    async def connect_tcp(self, host, port, **kwargs):
        self.calls.append((host, port, kwargs))
        return self.stream

    async def sleep(self, _seconds):
        return None


def test_async_backend_uses_the_same_pinned_boundary():
    endpoint = ValidatedLlmEndpoint(
        base_url="https://gateway.example/v1",
        hostname="gateway.example",
        port=443,
        addresses=("8.8.8.8",),
    )
    delegate = _FakeAsyncBackend()
    backend = _PinnedAsyncBackend(endpoint, delegate)

    stream = asyncio.run(backend.connect_tcp("gateway.example", 443, timeout=5))

    assert stream is delegate.stream
    assert delegate.calls[0][:2] == ("8.8.8.8", 443)
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(backend.connect_tcp("metadata.google.internal", 443))


def test_async_backend_falls_back_after_connect_timeout():
    endpoint = ValidatedLlmEndpoint(
        base_url="https://gateway.example/v1",
        hostname="gateway.example",
        port=443,
        addresses=("2606:4700:4700::1111", "8.8.8.8"),
    )

    class TimeoutThenSuccessBackend(_FakeAsyncBackend):
        async def connect_tcp(self, host, port, **kwargs):
            self.calls.append((host, port, kwargs))
            if len(self.calls) == 1:
                raise httpcore.ConnectTimeout("ipv6 timeout")
            return self.stream

    delegate = TimeoutThenSuccessBackend()
    backend = _PinnedAsyncBackend(endpoint, delegate)

    assert (
        asyncio.run(backend.connect_tcp("gateway.example", 443, timeout=5))
        is delegate.stream
    )
    assert [call[:2] for call in delegate.calls] == [
        ("2606:4700:4700::1111", 443),
        ("8.8.8.8", 443),
    ]
    assert delegate.calls[0][2]["timeout"] <= 2.5
    assert delegate.calls[1][2]["timeout"] <= 5


def test_probe_revalidates_and_uses_the_pinned_client(monkeypatch):
    endpoint = ValidatedLlmEndpoint(
        base_url="https://gateway.example/v1",
        hostname="gateway.example",
        port=443,
        addresses=("8.8.8.8",),
    )
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "OK"}}]}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(
        llm_config_service,
        "validate_user_llm_endpoint",
        lambda value: endpoint if value == endpoint.base_url else None,
    )
    monkeypatch.setattr(
        llm_config_service,
        "create_pinned_http_client",
        lambda resolved, *, timeout: FakeClient()
        if resolved is endpoint and timeout >= 3
        else None,
    )

    result = llm_config_service._probe_openai_compatible(
        {
            "base_url": endpoint.base_url,
            "model": "gateway-chat",
            "api_key": "sk-test",
        },
    )

    assert result["ok"] is True
    assert captured["url"] == "https://gateway.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.parametrize("payload", [[], {"result": "OK"}])
def test_probe_rejects_non_openai_json_shapes(monkeypatch, payload):
    endpoint = ValidatedLlmEndpoint(
        base_url="https://gateway.example/v1",
        hostname="gateway.example",
        port=443,
        addresses=("8.8.8.8",),
    )

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return payload

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def post(_url, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        llm_config_service,
        "validate_user_llm_endpoint",
        lambda _value: endpoint,
    )
    monkeypatch.setattr(
        llm_config_service,
        "create_pinned_http_client",
        lambda _resolved, *, timeout: FakeClient() if timeout >= 3 else None,
    )

    with pytest.raises(AppError) as failed:
        llm_config_service._probe_openai_compatible(
            {
                "base_url": endpoint.base_url,
                "model": "gateway-chat",
                "api_key": "sk-test",
            },
        )

    assert failed.value.error_code == "LLM_RESPONSE_INVALID"
    assert "sk-test" not in str(failed.value)
