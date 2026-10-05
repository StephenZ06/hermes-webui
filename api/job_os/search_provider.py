"""Where Scout's keyword searches go.

Self-hosted SearXNG (behind Firecrawl's /search) scrapes public engines, which
rate-limit and CAPTCHA it after a burst of queries -- observed: Brave
"Suspended: too many requests", DuckDuckGo "CAPTCHA", Google "Suspended".
When ``BRAVE_SEARCH_API_KEY`` is set, Scout uses the official Brave Search API
instead (paced to its free-tier 1 request/second); otherwise it falls back to
Firecrawl search. Firecrawl still reads the pages either way.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from api.job_os.env import profile_env_value
from api.job_os.firecrawl import FirecrawlError

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
MIN_INTERVAL = 1.1  # seconds between Brave calls (free tier: 1 request/second)
_pace_lock = threading.Lock()
_last_call = [0.0]


class BraveSearch:
    name = "brave"

    def __init__(self, api_key: str, *, base_url: str = BRAVE_URL, timeout: float = 20.0) -> None:
        self._key = api_key
        self._url = base_url
        self._timeout = timeout

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        params = urllib.parse.urlencode({"q": query, "count": max(1, min(int(limit), 20))})
        request = urllib.request.Request(f"{self._url}?{params}", headers={
            "Accept": "application/json", "X-Subscription-Token": self._key})
        with _pace_lock:  # one call at a time, spaced to the rate limit
            wait = MIN_INTERVAL - (time.monotonic() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310 - fixed API URL
                    body = response.read(2 * 1024 * 1024)
            except urllib.error.HTTPError as error:
                raise FirecrawlError(f"Brave Search returned HTTP {error.code}") from error
            except (urllib.error.URLError, OSError, TimeoutError) as error:
                raise FirecrawlError("Brave Search did not answer") from error
            finally:
                _last_call[0] = time.monotonic()
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except ValueError as error:
            raise FirecrawlError("Brave Search returned something that is not JSON") from error
        results = ((data.get("web") or {}).get("results") or []) if isinstance(data, dict) else []
        return [{"url": r["url"], "title": str(r.get("title") or "")[:300], "description": str(r.get("description") or "")[:500]}
                for r in results if isinstance(r, dict) and isinstance(r.get("url"), str)]


class ScoutClient:
    """Search through the best available provider; read pages through Firecrawl."""

    def __init__(self, firecrawl, searcher=None) -> None:
        self._firecrawl = firecrawl
        self._searcher = searcher or firecrawl
        self.search_provider = getattr(searcher, "name", "firecrawl") if searcher else "firecrawl"

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        return self._searcher.search(query, limit=limit)

    def scrape(self, url: str, *, links: bool = False) -> dict:
        return self._firecrawl.scrape(url, links=links)


def search_provider_name() -> str:
    return "brave" if profile_env_value("BRAVE_SEARCH_API_KEY")[0] else "firecrawl"


def make_scout_client(firecrawl) -> ScoutClient:
    key, _ = profile_env_value("BRAVE_SEARCH_API_KEY")
    return ScoutClient(firecrawl, BraveSearch(key) if key else None)
