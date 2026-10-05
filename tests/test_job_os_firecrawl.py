"""Firecrawl configuration and health: Not configured / Offline / Incompatible / Healthy."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from api import profiles
from api.job_os import firecrawl
from api.job_os.firecrawl import FirecrawlClient, resolve_firecrawl_config


def _serve(routes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            status, body, ctype = routes.get(self.path, (404, "nope", "text/plain"))
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "research"
    home.mkdir()
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "research")
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: home)
    monkeypatch.delenv("FIRECRAWL_API_URL", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    return home


def test_not_configured_without_any_url(home):
    assert FirecrawlClient(resolve_firecrawl_config()).health()["state"] == "not_configured"


def test_offline_when_nothing_listens(home):
    (home / ".env").write_text("FIRECRAWL_API_URL=http://127.0.0.1:9\n")
    health = FirecrawlClient(resolve_firecrawl_config(), timeout=1.5).health()
    assert health["state"] == "offline"
    assert health["base_url"] == "http://127.0.0.1:9"


def test_incompatible_when_another_service_answers(home):
    server, url = _serve({"/": (200, "<html>router admin</html>", "text/html")})
    try:
        (home / ".env").write_text(f'FIRECRAWL_API_URL="{url}/"\n')
        assert FirecrawlClient(resolve_firecrawl_config()).health()["state"] == "incompatible"
    finally:
        server.shutdown()


def test_healthy_firecrawl_reports_ready_without_leaking_the_key(home):
    server, url = _serve({
        "/": (200, {"message": "Firecrawl API", "documentation_url": "https://docs.firecrawl.dev"}, "application/json"),
        "/v0/health/readiness": (200, {"status": "ok"}, "application/json"),
    })
    try:
        (home / ".env").write_text(f"FIRECRAWL_API_URL={url}\nFIRECRAWL_API_KEY=fc-secretsecretsecret\n")
        health = FirecrawlClient(resolve_firecrawl_config()).health()
    finally:
        server.shutdown()
    assert health["state"] == "healthy" and health["ready"] is True
    assert health["api_key"] == "set"
    assert "fc-secret" not in json.dumps(health)


def test_settings_override_beats_profile_env_beats_process_env(home, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_URL", "http://process.example:3002")
    assert resolve_firecrawl_config().base_url == "http://process.example:3002"
    (home / ".env").write_text("FIRECRAWL_API_URL=http://profile.example:3002\n")
    assert resolve_firecrawl_config().base_url == "http://profile.example:3002"
    cfg = resolve_firecrawl_config(override_url="http://localhost:3002/")
    assert cfg.base_url == "http://localhost:3002" and cfg.source == "settings"


def test_base_url_must_be_http(home):
    (home / ".env").write_text("FIRECRAWL_API_URL=file:///etc/passwd\n")
    assert FirecrawlClient(resolve_firecrawl_config()).health()["state"] == "not_configured"


def test_url_join_keeps_paths(home):
    cfg = firecrawl.FirecrawlConfig(base_url="http://h:1/firecrawl", api_key=None, source="env")
    assert FirecrawlClient(cfg)._url("/v1/search") == "http://h:1/firecrawl/v1/search"
