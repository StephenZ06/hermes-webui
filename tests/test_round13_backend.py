"""Usage for Claude through 9Router, and checking a key before it is saved."""

import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api import account_usage, host_loopback, oauth, profile_providers as pp
import api.routes as routes


# ── Session usage on a Claude profile in the container ────────────────────

class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return self.body


def _fake_9router(seen):
    bodies = iter([b'{"connections": [{"id": "abc", "provider": "claude"}]}',
                   b'{"quotas": {"session (5h)": {"remaining": 65}, "weekly (7d)": {"remaining": 31}}}'])

    def urlopen(request, timeout=None):
        seen.append(request.full_url)
        return _Response(next(bodies))
    return urlopen


def test_claude_usage_reads_the_mounted_token_and_calls_the_host(tmp_path, monkeypatch):
    secret, machine = tmp_path / "secret", tmp_path / "machine"
    secret.write_text("s")
    machine.write_text("m")
    monkeypatch.setattr(account_usage, "_NINE_ROUTER_CLI_SECRET", tmp_path / "gone-1")
    monkeypatch.setattr(account_usage, "_NINE_ROUTER_MACHINE_ID", tmp_path / "gone-2")
    monkeypatch.setattr(account_usage, "_NINE_ROUTER_MOUNTED_CLI_SECRET", secret)
    monkeypatch.setattr(account_usage, "_NINE_ROUTER_MOUNTED_MACHINE_ID", machine)
    monkeypatch.setattr(host_loopback, "in_container", lambda: True)
    monkeypatch.setattr(host_loopback, "_answers_locally", lambda port: False)
    monkeypatch.setattr(host_loopback, "_host_alias", lambda: "host.docker.internal")
    seen = []
    monkeypatch.setattr(account_usage, "urlopen", _fake_9router(seen))

    snapshot = account_usage.fetch_9router_claude_account_usage("http://127.0.0.1:20128/v1")

    assert [w.used_percent for w in snapshot.windows] == [35.0, 69.0]
    assert all(url.startswith("http://host.docker.internal:20128/") for url in seen)


def test_without_a_token_anywhere_there_is_no_usage(tmp_path, monkeypatch):
    for name in ("_NINE_ROUTER_CLI_SECRET", "_NINE_ROUTER_MACHINE_ID",
                 "_NINE_ROUTER_MOUNTED_CLI_SECRET", "_NINE_ROUTER_MOUNTED_MACHINE_ID"):
        monkeypatch.setattr(account_usage, name, tmp_path / name)
    assert account_usage.fetch_9router_claude_account_usage("http://127.0.0.1:20128/v1") is None


class _Handler:
    pass


def _usage_for(tmp_path, monkeypatch, config):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text(config, encoding="utf-8")
    seen = []
    monkeypatch.setattr(routes, "j", lambda handler, payload, **kwargs: seen.append(payload))
    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda name: home)
    monkeypatch.setattr("api.profiles.get_active_profile_name", lambda: "p")
    monkeypatch.setattr("api.profiles._cron_env_lock", SimpleNamespace(locked=lambda: True))

    def blocked(_home):
        raise AssertionError("waited on the cron lock")

    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", blocked)
    return seen


def test_claude_usage_answers_while_a_scheduled_job_holds_the_cron_lock(tmp_path, monkeypatch):
    seen = _usage_for(tmp_path, monkeypatch, "model:\n  provider: custom:9router\n  base_url: http://127.0.0.1:20128/v1\n"
                                             "  default: cc/claude-sonnet-5-5\n")
    monkeypatch.setattr(account_usage, "fetch_9router_claude_account_usage", lambda base: account_usage.AccountUsageSnapshot(
        "9router-claude", (account_usage.AccountUsageWindow("5 hours", 35),), "Claude via 9router"))
    routes._handle_account_usage(_Handler(), SimpleNamespace(query="profile=p"))
    assert seen[-1]["windows"][0]["used_percent"] == 35


def test_a_local_profile_answers_while_a_scheduled_job_holds_the_cron_lock(tmp_path, monkeypatch):
    seen = _usage_for(tmp_path, monkeypatch, "model:\n  provider: lmstudio\n  base_url: http://localhost:1234/v1\n")
    routes._handle_account_usage(_Handler(), SimpleNamespace(query="profile=p"))
    assert seen[-1] == {"available": False, "provider": "lmstudio", "local": True}


@pytest.mark.parametrize("provider,url,local", [
    ("custom:lm-studio", "http://localhost:1234/v1", True),
    ("custom", "http://127.0.0.1:11434/v1", True),
    ("custom:lmstudio", "http://host.docker.internal:1234/v1", True),
    ("lmstudio", "", True),
    ("custom:9router", "http://127.0.0.1:20128/v1", False),
    ("custom:work", "https://models.example.com:1234/v1", False),
    ("openai", "http://localhost:1234/v1", False),
    ("custom:x", "http://[bad", False),
])
def test_what_counts_as_a_local_model(provider, url, local):
    from api.providers import is_self_hosted_route
    assert is_self_hosted_route(provider, url) is local


def test_lm_studio_set_up_through_the_wizard_gets_the_unlimited_card(tmp_path, monkeypatch):
    seen = _usage_for(tmp_path, monkeypatch, "model:\n  provider: custom:lm-studio\n  base_url: http://localhost:1234/v1\n  default: qwen\n")
    routes._handle_account_usage(_Handler(), SimpleNamespace(query="profile=p"))
    assert seen[-1]["local"] is True


# ── Checking a key ────────────────────────────────────────────────────────

KEY = "sk-the-real-key"


def _status(monkeypatch, *answers):
    calls, left = [], list(answers)

    def status_of(method, url, headers):
        calls.append((method, url, headers))
        answer = left.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(pp, "_status_of", status_of)
    return calls


@pytest.mark.parametrize("provider,status,state", [
    ("openai", 200, "ok"),
    ("openai", 401, "rejected"),
    ("openai", 403, "rejected"),
    ("x-ai", 400, "rejected"),
    ("google", 400, "rejected"),
    ("openai", 400, "unknown"),
    ("openai", 402, "unknown"),
    ("openai", 429, "unknown"),
    ("openai", 500, "unknown"),
    ("ollama-cloud", 400, "ok"),
    ("ollama-cloud", 422, "ok"),
    ("ollama-cloud", 401, "rejected"),
])
def test_what_a_providers_answer_means(monkeypatch, provider, status, state):
    _status(monkeypatch, status)
    result = pp.check_key(provider, KEY)
    assert result["state"] == state
    assert KEY not in result["message"]


def test_no_answer_is_not_a_good_key(monkeypatch):
    _status(monkeypatch, OSError("refused"))
    assert pp.check_key("openai", KEY)["state"] == "unknown"


def test_a_provider_that_cannot_be_checked_is_not_called_good(monkeypatch):
    calls = _status(monkeypatch)
    assert pp.check_key("nvidia", KEY)["state"] == "unknown"
    assert calls == []


def test_openrouter_is_asked_where_a_key_is_needed(monkeypatch):
    calls = _status(monkeypatch, 200)
    pp.check_key("openrouter", KEY)
    assert calls[0][1].endswith("/api/v1/key")


def test_each_provider_gets_the_key_in_its_own_header(monkeypatch):
    calls = _status(monkeypatch, 200, 200, 200)
    pp.check_key("anthropic", KEY)
    pp.check_key("google", KEY)
    pp.check_key("openai", KEY)
    assert calls[0][2]["x-api-key"] == KEY and "Authorization" not in calls[0][2]
    assert calls[1][2]["x-goog-api-key"] == KEY and KEY not in calls[1][1]
    assert calls[2][2]["Authorization"] == f"Bearer {KEY}"


def test_a_key_with_a_line_break_goes_nowhere(monkeypatch):
    calls = _status(monkeypatch)
    with pytest.raises(pp.ProfileProviderError):
        pp.check_key("openai", "sk-one\nInjected: yes")
    assert calls == []


def test_a_router_that_lists_models_for_anyone_still_has_its_key_checked(monkeypatch):
    calls = _status(monkeypatch, 200, 401)
    assert pp.check_endpoint("http://router.test/v1", KEY)["state"] == "rejected"
    assert calls[1][0] == "POST" and calls[1][1].endswith("/chat/completions")


def test_an_endpoint_that_passes_the_key_is_good(monkeypatch):
    _status(monkeypatch, 200, 400)
    assert pp.check_endpoint("http://router.test/v1", KEY)["state"] == "ok"


def test_a_local_server_needs_no_key(monkeypatch):
    calls = _status(monkeypatch, 200)
    assert pp.check_endpoint("http://localhost:1234/v1", "")["state"] == "ok"
    assert len(calls) == 1


def test_a_server_that_is_off_can_still_be_saved_by_choice(monkeypatch):
    _status(monkeypatch, OSError("refused"))
    result = pp.check_endpoint("http://localhost:1234/v1", "")
    assert result["state"] == "unknown" and "http://localhost:1234/v1" in result["message"]


@pytest.mark.parametrize("url", ["ftp://host/v1", "file:///etc/passwd", "", "host/v1"])
def test_only_web_addresses_are_tried(monkeypatch, url):
    calls = _status(monkeypatch)
    with pytest.raises(pp.ProfileProviderError):
        pp.check_endpoint(url, KEY)
    assert calls == []


def test_the_real_request_reports_the_status_of_a_refusal(monkeypatch):
    def refused(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, None)

    monkeypatch.setattr(pp.urllib.request, "urlopen", refused)
    assert pp._status_of("GET", "https://api.openai.com/v1/models", {}) == 401


def test_a_saved_endpoints_key_is_used_when_the_box_is_left_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "profile_home", lambda name: tmp_path)
    monkeypatch.setattr(pp, "_read_config", lambda home: {"providers": {"r": {"base_url": "http://r/v1", "key_env": "R_KEY"}}})
    monkeypatch.setattr(pp, "_read_env", lambda home: {"R_KEY": KEY})
    calls = _status(monkeypatch, 200, 400)
    pp.verify_credentials("p", {"id": "r", "base_url": "http://r/v1"})
    assert calls[0][2]["Authorization"] == f"Bearer {KEY}"


def test_the_last_step_tries_a_saved_key_for_real(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "profile_home", lambda name: tmp_path)
    monkeypatch.setattr(pp, "_read_config", lambda home: {"model": {"provider": "openai"}})
    monkeypatch.setattr(pp, "_read_env", lambda home: {"OPENAI_API_KEY": KEY})
    monkeypatch.setattr(pp, "_is_root_home", lambda home: False)
    monkeypatch.setattr(pp, "_env_var_for", lambda provider: "OPENAI_API_KEY")
    monkeypatch.setattr(pp, "_route_status", lambda *a: {"state": "ready", "message": "Key saved."})
    _status(monkeypatch, 401)
    assert pp.test_route("p", "openai")["ok"] is False
    _status(monkeypatch, 200)
    assert pp.test_route("p", "openai")["ok"] is True


# ── Signing a new profile in ──────────────────────────────────────────────

def test_a_new_profile_signs_in_to_the_provider_the_wizard_names(monkeypatch):
    seen = []
    monkeypatch.setattr(routes, "j", lambda handler, payload, **kwargs: payload)
    monkeypatch.setattr(oauth, "profile_oauth_status", lambda name: {"oauth_supported": False, "provider": ""})
    monkeypatch.setattr(oauth, "start_onboarding_oauth_flow", lambda body: seen.append(body) or {"status": "pending"})
    routes._route_post_api_profiles_oauth_start(_Handler(), None, {"name": "fresh", "provider": "openai-codex"}, None)
    assert seen == [{"provider": "openai-codex", "profile": "fresh"}]


def test_without_a_named_provider_the_profiles_own_is_used(monkeypatch):
    seen = []
    monkeypatch.setattr(routes, "j", lambda handler, payload, **kwargs: payload)
    monkeypatch.setattr(oauth, "profile_oauth_status", lambda name: {"oauth_supported": True, "provider": "anthropic"})
    monkeypatch.setattr(oauth, "start_onboarding_oauth_flow", lambda body: seen.append(body) or {"status": "pending"})
    routes._route_post_api_profiles_oauth_start(_Handler(), None, {"name": "old"}, None)
    assert seen[0]["provider"] == "anthropic"


# ── Resume Studio's preview ───────────────────────────────────────────────

def test_the_resume_preview_may_be_framed_by_the_page_that_shows_it(monkeypatch):
    from api.job_os import api as job_api, export, resume
    from tests.test_job_os_tailor import _H

    monkeypatch.setattr(resume, "load_resume", lambda: {"text": "x", "filename": "cv.txt"})
    monkeypatch.setattr(resume, "original_file", lambda: None)
    monkeypatch.setattr(resume, "style_profile", lambda: {})
    monkeypatch.setattr(export, "text_page", lambda *a, **k: "<p>x</p>")
    handler = _H()
    job_api._resume_file(handler, True)
    assert "frame-ancestors 'self'" in handler._csp_report_only_policy
    assert "frame-ancestors 'none'" not in handler._csp_report_only_policy
