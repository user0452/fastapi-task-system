from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network

from fastapi import Request

from app.core.config import get_settings

IPAddress = IPv4Address | IPv6Address


def _parse_ip(value: str) -> IPAddress | None:
    try:
        return ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted(address: IPAddress) -> bool:
    return any(
        address in ip_network(cidr, strict=False)
        for cidr in get_settings().trusted_proxy_cidrs
    )


def get_client_ip(request: Request) -> str:
    direct_value = request.client.host if request.client else "unknown"
    direct_address = _parse_ip(direct_value)
    if direct_address is None or not _is_trusted(direct_address):
        return direct_value

    forwarded_value = request.headers.get("x-forwarded-for")
    if not forwarded_value:
        return str(direct_address)
    raw_hops = [item.strip() for item in forwarded_value.split(",")]
    if not raw_hops or len(raw_hops) > 20:
        return str(direct_address)
    forwarded_hops: list[IPAddress] = []
    for item in raw_hops:
        parsed = _parse_ip(item)
        if parsed is None:
            return str(direct_address)
        forwarded_hops.append(parsed)

    candidate = direct_address
    for hop in reversed(forwarded_hops):
        if not _is_trusted(candidate):
            break
        candidate = hop
    return str(candidate)


__all__ = ["get_client_ip"]
