"""Services on the host seen from the container, a Space's key after the move to Docker, and adaptive titles."""

import json
import socket
import threading
from unittest.mock import MagicMock, patch

import pytest

from api import host_loopback, profile_providers, ssh_mount, streaming
from api.job_os import firecrawl


@pytest.fixture
def container(monkeypatch):
    monkeypatch.setattr(host_loopback, "in_container", lambda: True)
    monkeypatch.setattr(host_loopback, "_answers_locally", lambda port: False)
    monkeypatch.setattr(host_loopback, "_host_alias", lambda: "host.docker.internal")


# ── Services on the host ──────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("http://localhost:1234/v1", "http://host.docker.internal:1234/v1"),
    ("http://127.0.0.1:3002", "http://host.docker.internal:3002"),
    ("http://[::1]:11434/v1", "http://host.docker.internal:11434/v1"),
    ("http://192.168.1.5:1234/v1", "http://192.168.1.5:1234/v1"),
    ("https://api.example.com/v1", "https://api.example.com/v1"),
    ("", ""),
    (None, None),
])
def test_a_loopback_url_reaches_the_host_from_the_container(container, url, expected):
    assert host_loopback.host_url(url) == expected


def test_outside_a_container_the_url_is_left_alone(monkeypatch):
    monkeypatch.setattr(host_loopback, "in_container", lambda: False)
    assert host_loopback.host_url("http://localhost:1234/v1") == "http://localhost:1234/v1"


def test_a_service_inside_the_container_keeps_its_loopback_url(container, monkeypatch):
    monkeypatch.setattr(host_loopback, "_answers_locally", lambda port: port == 1234)
    assert host_loopback.host_url("http://localhost:1234/v1") == "http://localhost:1234/v1"
    assert host_loopback.host_url("http://localhost:3002") == "http://host.docker.internal:3002"


def test_without_the_alias_the_url_is_left_alone(monkeypatch):
    monkeypatch.setattr(host_loopback, "in_container", lambda: True)
    monkeypatch.setattr(host_loopback, "_answers_locally", lambda port: False)

    def unknown(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(host_loopback.socket, "getaddrinfo", unknown)
    assert host_loopback.host_url("http://localhost:1234/v1") == "http://localhost:1234/v1"


def test_the_firecrawl_client_calls_the_host(container):
    client = firecrawl.FirecrawlClient(firecrawl.FirecrawlConfig("http://localhost:3002", None, "profile"))
    assert client._url("/v1/search") == "http://host.docker.internal:3002/v1/search"


def test_testing_a_local_model_calls_the_host_and_names_the_configured_url(container, monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "huihui-qwen3.5-9b-abliterated"}]}).encode()

    def urlopen(request, timeout=None):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr(profile_providers, "profile_home", lambda name: "/nowhere")
    monkeypatch.setattr(profile_providers, "_read_config", lambda home: {
        "model": {"provider": "lmstudio", "base_url": "http://localhost:1234/v1"}})
    monkeypatch.setattr(profile_providers, "_read_env", lambda home: {})
    monkeypatch.setattr(profile_providers.urllib.request, "urlopen", urlopen)
    result = profile_providers.test_route("local-model")
    assert seen == ["http://host.docker.internal:1234/v1/models"]
    assert result["ok"] and result["models"] == ["huihui-qwen3.5-9b-abliterated"]

    def refused(request, timeout=None):
        raise OSError("refused")

    monkeypatch.setattr(profile_providers.urllib.request, "urlopen", refused)
    assert "http://localhost:1234/v1" in profile_providers.test_route("local-model")["message"]


def test_a_chat_on_a_local_model_calls_the_host(container):
    runtime = {"provider": "lmstudio", "base_url": "http://localhost:1234/v1"}
    url = streaming._runtime_preferred_base_url(runtime, "lmstudio", "http://localhost:1234/v1")
    assert url == "http://host.docker.internal:1234/v1"


def test_the_managed_services_check_looks_on_the_host(container, monkeypatch):
    from api import managed_services
    seen = []

    class Connection:
        def __init__(self, host, port, timeout=None):
            seen.append(host)

        def request(self, *args):
            raise OSError("refused")

    monkeypatch.setattr(managed_services.http.client, "HTTPConnection", Connection)
    assert managed_services._http_reachable("127.0.0.1", 3002) is False
    assert seen == ["host.docker.internal"]


# ── A Space's key ─────────────────────────────────────────────────────────

def _space(key_path):
    return {"name": "Pi", "path": "/workspace/remote/pi",
            "remote": {"host": "me@pi", "remote_path": "/home/me", "key_path": key_path}}


def test_a_space_saved_before_docker_finds_its_key_where_compose_mounts_it(tmp_path, monkeypatch):
    (tmp_path / "hermes_rp5").write_text("key")
    monkeypatch.setattr(ssh_mount, "_CONTAINER_KEY_DIR", tmp_path)
    assert ssh_mount._remote_cfg(_space("/home/me/.ssh/hermes_rp5"))["key_path"] == str(tmp_path / "hermes_rp5")


def test_a_key_that_exists_is_used_as_saved(tmp_path, monkeypatch):
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "hermes_rp5").write_text("key")
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    (mounted / "hermes_rp5").write_text("key")
    monkeypatch.setattr(ssh_mount, "_CONTAINER_KEY_DIR", mounted)
    assert ssh_mount._remote_cfg(_space(str(saved / "hermes_rp5")))["key_path"] == str(saved / "hermes_rp5")


def test_a_key_that_is_nowhere_stays_as_saved_so_the_error_names_it(tmp_path, monkeypatch):
    monkeypatch.setattr(ssh_mount, "_CONTAINER_KEY_DIR", tmp_path)
    assert ssh_mount._remote_cfg(_space("/home/me/.ssh/gone"))["key_path"] == "/home/me/.ssh/gone"


# ── Adaptive titles ───────────────────────────────────────────────────────

def test_the_interval_saves_whether_the_page_sends_a_number_or_text(tmp_path):
    from api import config
    for sent, kept in ((10, "10"), ("20", "20")):
        with patch.object(config, "SETTINGS_FILE", tmp_path / "settings.json"):
            saved = config.save_settings({"auto_title_refresh_every": sent})
        assert saved["auto_title_refresh_every"] == kept


def test_the_settings_page_sends_the_interval_as_the_option_value():
    from pathlib import Path
    panels = (Path(__file__).parent.parent / "static" / "panels.js").read_text(encoding="utf-8")
    assert "payload.auto_title_refresh_every=autoTitleRefreshSel.value" in panels


def _session(title="Old Title", messages=None):
    session = MagicMock()
    session.title = title
    session.session_id = "sid"
    session.llm_title_generated = True
    session.messages = messages if messages is not None else [
        {"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}] * 5
    return session


def _refresh(put, *, luna_title="New Title", **kwargs):
    route = ("openai-codex", "gpt-6-luna", "high")
    aux = MagicMock(return_value=(luna_title, "llm_aux", ""))
    with patch("api.streaming.get_session", return_value=_session()), \
            patch("api.streaming.session_has_manual_title", return_value=False), \
            patch("api.streaming._aux_title_generation_enabled", return_value=True), \
            patch("api.streaming._aux_title_configured", return_value=False), \
            patch("api.streaming._adaptive_title_route", return_value=route), \
            patch("api.streaming._generate_llm_session_title_via_aux", aux), \
            patch("api.streaming._get_session_agent_lock", return_value=threading.Lock()), \
            patch("api.state_sync.sync_session_title"):
        streaming._run_background_title_refresh("sid", "u", "a", "Old Title", put, **kwargs)
    return aux


def test_the_new_title_reaches_the_page_before_the_stream_closes():
    events = []
    _refresh(lambda name, data: events.append(name), end_stream_for="original")
    assert events.index("title") < events.index("stream_end")
    assert events[-1] == "stream_end"


def test_the_stream_closes_when_the_refresh_finds_nothing():
    events = []
    _refresh(lambda name, data: events.append((name, data)), luna_title=None, end_stream_for="original")
    assert events[-1] == ("stream_end", {"session_id": "original"})


def test_the_stream_closes_when_the_refresh_breaks():
    events = []
    with patch("api.streaming.get_session", side_effect=RuntimeError("boom")):
        streaming._run_background_title_refresh("sid", "u", "a", "Old Title", lambda n, d: events.append(n),
                                                end_stream_for="original")
    assert events == ["stream_end"]


def test_the_refresh_asks_luna():
    aux = _refresh(lambda name, data: None)
    assert aux.call_args.kwargs["provider"] == "openai-codex"
    assert aux.call_args.kwargs["model"] == "gpt-6-luna"
    assert aux.call_args.kwargs["reasoning_effort"] == "high"


def test_when_luna_is_not_available_the_usual_title_route_still_runs():
    calls = []

    def aux(user, assistant, **kwargs):
        calls.append(kwargs)
        return (None, "llm_error_aux", "") if kwargs.get("model") else ("Fallback Title", "llm_aux", "")

    events = []
    with patch("api.streaming.get_session", return_value=_session()), \
            patch("api.streaming.session_has_manual_title", return_value=False), \
            patch("api.streaming._aux_title_generation_enabled", return_value=True), \
            patch("api.streaming._aux_title_configured", return_value=True), \
            patch("api.streaming._adaptive_title_route", return_value=("openai-codex", "gpt-6-luna", "high")), \
            patch("api.streaming._generate_llm_session_title_via_aux", side_effect=aux), \
            patch("api.streaming._get_session_agent_lock", return_value=threading.Lock()), \
            patch("api.state_sync.sync_session_title"):
        streaming._run_background_title_refresh("sid", "u", "a", "Old Title", lambda n, d: events.append((n, d)))
    assert len(calls) == 2 and ("title", {"session_id": "sid", "title": "Fallback Title"}) in events


def test_the_scheduler_says_whether_it_took_over_closing_the_stream():
    put = MagicMock()
    with patch("api.streaming._get_title_refresh_interval", return_value=5), \
            patch("api.streaming.session_has_manual_title", return_value=False), \
            patch("api.streaming.threading.Thread") as thread:
        assert streaming._maybe_schedule_title_refresh(_session(), put, None, end_stream_for="original") is True
        assert thread.call_args.kwargs["args"][-1] == "original"
        assert streaming._maybe_schedule_title_refresh(_session(messages=[{"role": "user", "content": "u"}]), put, None,
                                                       end_stream_for="original") is False
