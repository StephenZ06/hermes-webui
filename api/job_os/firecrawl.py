"""Server-side Firecrawl adapter for Job OS.

Firecrawl is self-hosted (see the spec's 2026-10-05 decision update) and
operator-configured, so its base URL may be loopback; that is deliberately
*not* run through the job-URL policy, which applies to the pages Firecrawl is
asked to fetch. The API key never leaves the server: health and diagnostics
report only whether one is set.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from api.job_os.env import profile_env_value

MAX_RESPONSE_BYTES = 64 * 1024
MAX_PAGE_BYTES = 4 * 1024 * 1024
SEARCH_TIMEOUT = 60.0
SCRAPE_TIMEOUT = 90.0


class FirecrawlError(RuntimeError):
    """A bounded, secret-free description of a failed Firecrawl call."""


@dataclass(frozen=True)
class FirecrawlConfig:
    base_url: str | None
    api_key: str | None
    source: str | None  # "settings", "profile", "process" or None


def _clean_base_url(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return None
    return text.rstrip("/")


def resolve_firecrawl_config(override_url: str | None = None) -> FirecrawlConfig:
    """Settings override, then the active profile's ``.env``, then the process env."""
    api_key, _ = profile_env_value("FIRECRAWL_API_KEY")
    override = _clean_base_url(override_url)
    if override:
        return FirecrawlConfig(override, api_key, "settings")
    value, source = profile_env_value("FIRECRAWL_API_URL")
    base = _clean_base_url(value)
    return FirecrawlConfig(base, api_key, source if base else None)


class FirecrawlClient:
    def __init__(self, config: FirecrawlConfig, *, timeout: float = 5.0) -> None:
        self.config = config
        self.timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self.config.base_url}/{path.lstrip('/')}"

    def _get(self, path: str) -> tuple[int, bytes, str]:
        headers = {"Accept": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(self._url(path), headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - operator-configured URL
                return response.status, response.read(MAX_RESPONSE_BYTES), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            return error.code, error.read(MAX_RESPONSE_BYTES) if error.fp else b"", error.headers.get("Content-Type", "")

    def _post(self, path: str, payload: dict, *, timeout: float, limit: int) -> dict:
        if not self.config.base_url:
            raise FirecrawlError("Firecrawl is not configured")
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(self._url(path), data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-configured URL
                body = response.read(limit + 1)
        except urllib.error.HTTPError as error:
            raise FirecrawlError(f"Firecrawl returned HTTP {error.code}") from error
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            raise FirecrawlError("Firecrawl did not answer") from error
        if len(body) > limit:
            raise FirecrawlError("Firecrawl response was too large")
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except ValueError as error:
            raise FirecrawlError("Firecrawl returned something that is not JSON") from error
        if not isinstance(data, dict) or data.get("success") is False:
            message = str((data or {}).get("error") or "request failed")[:160] if isinstance(data, dict) else "request failed"
            raise FirecrawlError(f"Firecrawl: {message}")
        return data

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        """Web search through Firecrawl: ``[{"url", "title", "description"}]``."""
        data = self._post("/v1/search", {"query": query, "limit": max(1, min(int(limit), 50))},
                          timeout=SEARCH_TIMEOUT, limit=MAX_RESPONSE_BYTES * 16)
        results = data.get("data") if isinstance(data.get("data"), list) else []
        out = []
        for item in results:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                out.append({"url": item["url"], "title": str(item.get("title") or "")[:300],
                            "description": str(item.get("description") or "")[:500]})
        return out

    def scrape(self, url: str, *, links: bool = False) -> dict:
        """One page: ``{"html", "links", "title"}`` (raw HTML keeps JSON-LD)."""
        formats = ["rawHtml"] + (["links"] if links else [])
        data = self._post("/v1/scrape", {"url": url, "formats": formats, "timeout": int(SCRAPE_TIMEOUT * 1000) - 5000},
                          timeout=SCRAPE_TIMEOUT, limit=MAX_PAGE_BYTES)
        page = data.get("data") if isinstance(data.get("data"), dict) else {}
        meta = page.get("metadata") if isinstance(page.get("metadata"), dict) else {}
        return {
            "html": str(page.get("rawHtml") or "")[:MAX_PAGE_BYTES],
            "links": [link for link in (page.get("links") or []) if isinstance(link, str)][:500],
            "title": str(meta.get("title") or "")[:300],
            "status": meta.get("statusCode"),
        }

    def health(self) -> dict:
        """Classify the service as ``not_configured``, ``offline``,
        ``incompatible`` or ``healthy``. Never raises; never includes the key."""
        base = {
            "base_url": self.config.base_url,
            "source": self.config.source,
            "api_key": "set" if self.config.api_key else "unset",
            "ready": False,
        }
        if not self.config.base_url:
            return {**base, "state": "not_configured", "detail": "No Firecrawl URL is configured."}
        started = time.monotonic()
        try:
            status, body, _ctype = self._get("/")
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            return {**base, "state": "offline", "detail": "Firecrawl did not answer."}
        latency = round((time.monotonic() - started) * 1000)
        try:
            payload = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            payload = None
        if status != 200 or not isinstance(payload, dict) or "firecrawl" not in str(payload.get("message", "")).lower():
            return {**base, "state": "incompatible", "latency_ms": latency,
                    "detail": "Something answered at this URL, but it is not the Firecrawl API."}
        try:
            ready_status, _body, _ctype = self._get("/v0/health/readiness")
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            ready_status = 0
        if ready_status != 200:
            return {**base, "state": "offline", "latency_ms": latency,
                    "detail": "Firecrawl is running but not ready yet."}
        return {**base, "state": "healthy", "ready": True, "latency_ms": latency, "detail": "Firecrawl is ready."}
