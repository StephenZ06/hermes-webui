"""The chat sidebar usage card must follow the active profile's provider.

Requested behavior:

  * Codex profile      -> show the Codex rate-limit windows
  * NeuralWatt profile -> show the NeuralWatt quota
  * local profile      -> show nothing at all

A local / self-hosted server (LM Studio, Ollama) has no subscription quota, so
the handler must return early instead of letting the generic agent fetch or the
credential-pool fallback synthesize a meaningless "Capacity" window for it.
"""
from pathlib import Path
from types import SimpleNamespace
import sys
import types

import pytest

from api.account_usage import AccountUsageSnapshot, AccountUsageWindow
import api.routes as routes

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _write_profile(tmp_path, provider, base_url=None):
    profile_home = tmp_path / f"profile-{provider}-{abs(hash(base_url or '')) % 100000}"
    profile_home.mkdir(parents=True, exist_ok=True)
    config = f"model:\n  provider: {provider}\n"
    if base_url:
        config += f"  base_url: {base_url}\n"
    (profile_home / "config.yaml").write_text(config, encoding="utf-8")
    return profile_home


def _install(monkeypatch, tmp_path, profile_home, resolver=None):
    """Wire the handler to a tmp profile and capture the JSON payload."""
    seen = []
    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda _: profile_home)
    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", lambda _: _Context())
    monkeypatch.setattr(routes, "j", lambda _handler, payload: seen.append(payload))

    runtime_mod = types.ModuleType("hermes_cli.runtime_provider")
    runtime_mod.resolve_runtime_provider = lambda **_: (
        resolver if resolver is not None else (_ for _ in ()).throw(RuntimeError("no runtime"))
    )
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", runtime_mod)
    return seen


def _install_agent_fetch(monkeypatch, record):
    agent_mod = types.ModuleType("agent")
    agent_mod.__path__ = []
    usage_mod = types.ModuleType("agent.account_usage")

    def fetch_account_usage(provider, **kwargs):
        record.append((provider, kwargs))
        return None

    usage_mod.fetch_account_usage = fetch_account_usage
    monkeypatch.setitem(sys.modules, "agent", agent_mod)
    monkeypatch.setitem(sys.modules, "agent.account_usage", usage_mod)


def _record_pool_calls(monkeypatch, record):
    import api.providers as providers

    def account_usage_from_pool(provider):
        record.append(provider)
        return SimpleNamespace(
            available=True,
            provider=provider,
            plan=None,
            windows=(SimpleNamespace(label="Capacity", used_percent=0, reset_at=None, detail="all good"),),
        )

    monkeypatch.setattr(providers, "account_usage_from_pool", account_usage_from_pool)


@pytest.mark.parametrize("provider", ["lmstudio", "ollama"])
def test_local_profiles_report_no_usage_and_never_probe_a_pool(monkeypatch, tmp_path, provider):
    """A local profile must not show usage, and must not even try to."""
    profile_home = _write_profile(tmp_path, provider, "http://127.0.0.1:1234/v1")
    seen = _install(monkeypatch, tmp_path, profile_home)

    fetch_calls = []
    _install_agent_fetch(monkeypatch, fetch_calls)
    pool_calls = []
    _record_pool_calls(monkeypatch, pool_calls)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=local"))

    assert seen[-1] == {"available": False, "provider": provider, "local": True}
    # The pool fallback is what would otherwise invent a "Capacity" window.
    assert pool_calls == []
    assert fetch_calls == []


def test_local_profile_returns_nothing_even_when_a_pool_would_answer(monkeypatch, tmp_path):
    """Regression: the synthesized pool window must not reach a local profile."""
    profile_home = _write_profile(tmp_path, "lmstudio", "http://localhost:1234/v1")
    seen = _install(monkeypatch, tmp_path, profile_home)
    _install_agent_fetch(monkeypatch, [])
    _record_pool_calls(monkeypatch, [])

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=local"))

    assert seen[-1]["available"] is False
    assert seen[-1]["local"] is True
    assert "windows" not in seen[-1]


def test_codex_profile_reports_codex_usage(monkeypatch, tmp_path):
    """A Codex profile surfaces the Codex rate-limit windows."""
    profile_home = _write_profile(tmp_path, "openai-codex")
    seen = _install(monkeypatch, tmp_path, profile_home)

    monkeypatch.setattr(
        "api.account_usage.fetch_codex_cli_account_usage",
        lambda tokens: AccountUsageSnapshot(
            "openai-codex", (AccountUsageWindow("Weekly", 45),)
        ) if tokens else None,
    )
    codex_auth_mod = types.ModuleType("hermes_cli.auth_codex")
    codex_auth_mod._import_codex_cli_tokens = lambda: {"access_token": "desktop-token"}
    monkeypatch.setitem(sys.modules, "hermes_cli.auth_codex", codex_auth_mod)

    pool_calls = []
    _record_pool_calls(monkeypatch, pool_calls)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=codex"))

    assert seen[-1]["provider"] == "openai-codex"
    assert seen[-1]["available"] is True
    assert seen[-1]["windows"][0]["label"] == "Weekly"
    assert pool_calls == []


def test_neuralwatt_profile_reports_neuralwatt_usage(monkeypatch, tmp_path):
    """A NeuralWatt profile surfaces the NeuralWatt quota."""
    profile_home = _write_profile(tmp_path, "custom:api-nw", "https://api.neuralwatt.com/v1")
    seen = _install(monkeypatch, tmp_path, profile_home)
    monkeypatch.setattr(routes, "_resolve_neuralwatt_api_key", lambda *a, **k: "test-key")
    monkeypatch.setattr("api.account_usage.fetch_neuralwatt_account_usage", lambda base, key: (
        AccountUsageSnapshot("neuralwatt", (AccountUsageWindow("Energy", 69.5),), plan="Basic Plan")
    ))

    pool_calls = []
    _record_pool_calls(monkeypatch, pool_calls)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=nw"))

    assert seen[-1]["provider"] == "neuralwatt"
    assert seen[-1]["available"] is True
    assert seen[-1]["windows"][0]["label"] == "Energy"
    assert pool_calls == []


def test_each_9router_claude_profile_reports_the_shared_claude_subscription_usage(monkeypatch, tmp_path):
    """Any cc/ Claude profile uses the same authenticated 9router allowance."""
    profile_home = _write_profile(tmp_path, "custom:9router", "http://127.0.0.1:20128/v1")
    (profile_home / "config.yaml").write_text(
        "model:\n  provider: custom:9router\n  base_url: http://127.0.0.1:20128/v1\n  default: cc/claude-haiku-4-5-20251001\n",
        encoding="utf-8",
    )
    seen = _install(
        monkeypatch,
        tmp_path,
        profile_home,
        resolver={"provider": "custom:9router", "base_url": "http://127.0.0.1:20128/v1", "api_key": "router-key"},
    )
    _install_agent_fetch(monkeypatch, [])
    monkeypatch.setattr(
        "api.account_usage.fetch_9router_claude_account_usage",
        lambda base: AccountUsageSnapshot("9router-claude", (AccountUsageWindow("5 hours", 37),), "Claude via 9router")
        if base == "http://127.0.0.1:20128/v1" else None,
    )

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=coding-claude"))

    assert seen[-1]["provider"] == "9router-claude"
    assert seen[-1]["plan"] == "Claude via 9router"
    assert seen[-1]["windows"][0]["label"] == "5 hours"


def test_usage_widget_hides_itself_on_a_local_response():
    """The client honours the `local` marker so a local profile never paints."""
    js = (REPO_ROOT / "static" / "ui.js").read_text(encoding="utf-8")

    assert "data.local" in js
    guard = js.index("data.local")
    assert "widget.hidden=true" in js[guard : guard + 120]
