"""Point-of-use policy for external job URLs handed to Firecrawl.

Website content and search results are untrusted: a result may point at the
loopback Firecrawl API itself, the LAN, cloud metadata, or a host whose DNS
answer changes between checks. Every URL is parsed, normalised and resolved
at the moment it is about to be fetched, and refused unless every address it
resolves to is public.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048

Resolver = Callable[..., list]


class UnsafeJobUrl(ValueError):
    """Raised for a URL that must not be fetched."""


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_external_job_url(url: str, *, resolve: Resolver = socket.getaddrinfo) -> str:
    """Return ``url`` normalised (lower-case scheme/host, no fragment) or raise.

    Resolution happens on every call so a host that later rebinds to an
    internal address is refused at the time of use, not trusted from an
    earlier check.
    """
    text = str(url or "").strip()
    if not text or len(text) > MAX_URL_LENGTH:
        raise UnsafeJobUrl("URL is empty or too long")
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as error:
        raise UnsafeJobUrl("URL is malformed") from error
    scheme = (parts.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise UnsafeJobUrl("Only http and https job pages can be fetched")
    if parts.username or parts.password:
        raise UnsafeJobUrl("URLs with credentials are not allowed")
    host = (parts.hostname or "").lower()
    if not host:
        raise UnsafeJobUrl("URL has no host")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not _is_public(str(literal)):
        raise UnsafeJobUrl("Literal private or internal address")
    try:
        infos = resolve(host, port or (443 if scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError) as error:
        raise UnsafeJobUrl("Host does not resolve") from error
    addresses = {info[4][0] for info in infos or []}
    if not addresses:
        raise UnsafeJobUrl("Host does not resolve")
    try:
        if not all(_is_public(address) for address in addresses):
            raise UnsafeJobUrl("Host resolves to a private or internal address")
    except ValueError as error:
        if isinstance(error, UnsafeJobUrl):
            raise
        raise UnsafeJobUrl("Host resolves to an invalid address") from error
    netloc = host if port is None else f"{host}:{port}"
    if ":" in host:
        netloc = f"[{host}]" if port is None else f"[{host}]:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
