"""Reach a service on the host machine from inside the WebUI's container.

Firecrawl, LM Studio, Ollama and 9Router run on the host (or publish their port
there), and the URLs that name them say ``localhost`` because that is what they
print. Inside the container ``localhost`` is the container, so those URLs are
refused even though the service is up. The address is rewritten at the point of
use and never saved, so the same configuration keeps working outside Docker.

Anything uncertain leaves the URL as it was: outside a container, when the alias
does not resolve, or when something inside the container answers on that port.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_CONTAINER_MARKERS = ("/.dockerenv", "/run/.containerenv")
_DEFAULT_ALIAS = "host.docker.internal"
_PROBE_TIMEOUT = 0.2


def in_container() -> bool:
    return any(Path(marker).exists() for marker in _CONTAINER_MARKERS)


def _host_alias() -> str | None:
    alias = os.environ.get("HERMES_WEBUI_HOST_ALIAS", "").strip() or _DEFAULT_ALIAS
    try:
        socket.getaddrinfo(alias, None)
    except OSError:
        return None
    return alias


def _answers_locally(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=_PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def host_address(host: str, port: int) -> str:
    """``host``, or the host machine's alias when loopback here cannot be what is meant."""
    if str(host or "").lower() not in _LOOPBACK or not in_container() or _answers_locally(port):
        return host
    return _host_alias() or host


def host_url(url: str | None) -> str | None:
    """``url`` with a loopback host swapped for the host machine's alias when that is needed."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
        hostname, port = parts.hostname, parts.port
    except ValueError:
        return url
    if not hostname:
        return url
    port = port or (443 if parts.scheme == "https" else 80)
    swapped = host_address(hostname, port)
    if swapped == hostname:
        return url
    netloc = f"{swapped}:{parts.port}" if parts.port else swapped
    return urlunsplit(parts._replace(netloc=netloc))
