"""Scout search provider: Brave Search API when keyed, Firecrawl otherwise."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from api import profiles
from api.job_os import search_provider
from api.job_os.firecrawl import FirecrawlError


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setattr(search_provider, "MIN_INTERVAL", 0)
    return tmp_path


def _brave(status=200, body=None):
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append((parse_qs(urlsplit(self.path).query), self.headers.get("X-Subscription-Token")))
            data = json.dumps(body if body is not None else {"web": {"results": [{"url": "https://jobs.lever.co/a/1", "title": "Eng"}, {"x": 1}]}}).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/search", seen


def test_brave_results_are_shaped_and_keyed(home):
    server, url, seen = _brave()
    try:
        results = search_provider.BraveSearch("brave-key", base_url=url).search("site:jobs.lever.co python", limit=50)
    finally:
        server.shutdown()
    assert results == [{"url": "https://jobs.lever.co/a/1", "title": "Eng", "description": ""}]
    assert seen[0][0]["count"] == ["20"] and seen[0][1] == "brave-key"


def test_brave_errors_are_secret_free(home):
    server, url, _ = _brave(status=429, body={"error": "rate"})
    try:
        with pytest.raises(FirecrawlError) as err:
            search_provider.BraveSearch("brave-key", base_url=url).search("q")
    finally:
        server.shutdown()
    assert "429" in str(err.value) and "brave-key" not in str(err.value)


def test_provider_follows_the_key(home):
    class FC:
        def search(self, q, limit=10):
            return [{"url": "fc"}]

        def scrape(self, url, links=False):
            return {"html": "", "links": [], "title": ""}

    assert search_provider.search_provider_name() == "firecrawl"
    client = search_provider.make_scout_client(FC())
    assert client.search_provider == "firecrawl" and client.search("q") == [{"url": "fc"}]
    (home / ".env").write_text("BRAVE_SEARCH_API_KEY=bk\n")
    assert search_provider.search_provider_name() == "brave"
    assert search_provider.make_scout_client(FC()).search_provider == "brave"
