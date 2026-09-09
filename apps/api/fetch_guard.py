"""Reject non-HTTPS and non-public destinations for user-supplied URLs."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeSource(RuntimeError):
    pass


def assert_fetchable_https(url: str) -> None:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        raise UnsafeSource("only https sources are allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeSource("source URL missing host")
    if parsed.username or parsed.password:
        raise UnsafeSource("source URL must not include credentials")
    _assert_public_host(host)


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _assert_public_host(host: str) -> None:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        literal = ipaddress.ip_address(host)
        if _blocked(literal):
            raise UnsafeSource("source host is not a public address")
        return
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeSource(f"source host did not resolve: {exc}") from exc
    if not infos:
        raise UnsafeSource("source host did not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _blocked(ip):
            raise UnsafeSource("source host is not a public address")
