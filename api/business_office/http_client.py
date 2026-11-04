"""The only outbound HTTP path for provider adapters.

Hosts are allow-listed so a value from an email or note can never steer a
token to another server, and error bodies are dropped because they can echo
credentials.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from api.business_office.errors import ToolError

ALLOWED_HOSTS = frozenset({
    "oauth2.googleapis.com", "gmail.googleapis.com",
    "graph.threads.com", "api.instagram.com", "graph.instagram.com",
})
_TIMEOUT = 20


def request_json(method: str, url: str, *, form: dict[str, Any] | None = None, body: dict[str, Any] | None = None,
                 token: str = "", allow_empty: bool = False) -> dict[str, Any]:
    host = urllib.parse.urlsplit(url).hostname or ""
    if host not in ALLOWED_HOSTS or not url.startswith("https://"):
        raise ToolError("denied", "That provider address is not allowed")
    data, headers = None, {"Accept": "application/json", "User-Agent": "hermes-webui-business-office"}
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310 - allow-listed https hosts
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise _http_error(error) from None
    except (socket.timeout, TimeoutError):
        raise ToolError("timeout", "The provider did not answer in time") from None
    except urllib.error.URLError:
        raise ToolError("unavailable", "The provider could not be reached") from None
    if not raw and allow_empty:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise ToolError("unavailable", "The provider sent an unreadable answer") from None
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def _http_error(error: urllib.error.HTTPError) -> ToolError:
    status = error.code
    if status == 401:
        return ToolError("auth_expired", "The provider rejected the sign-in")
    if status == 403:
        return ToolError("permission", "The provider refused this permission")
    if status == 404:
        return ToolError("not_found", "The provider could not find that item")
    if status == 429:
        try:
            wait = float(error.headers.get("Retry-After") or 0)
        except (TypeError, ValueError):
            wait = 0
        return ToolError("rate_limited", "The provider asked to slow down", retry_after=wait)
    if status >= 500:
        return ToolError("unavailable", "The provider is having trouble")
    return ToolError("rejected", f"The provider rejected the request ({status})")
