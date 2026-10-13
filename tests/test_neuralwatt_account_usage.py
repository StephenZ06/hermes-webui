import api.account_usage as local_usage
from api.account_usage import (
    AccountUsageSnapshot,
    AccountUsageWindow,
    fetch_9router_claude_account_usage,
    neuralwatt_quota_snapshot,
)
from types import SimpleNamespace
import sys
import types

import api.routes as routes


def test_neuralwatt_fetch_defaults_to_documented_v1_endpoint(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False

        def read(self):
            return b'{"limits":{"weekly":{"limit":100,"used":5}}}'

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        return Response()

    monkeypatch.setattr(local_usage, "urlopen", fake_urlopen)
    snapshot = local_usage.fetch_neuralwatt_account_usage("", "test-key")

    assert snapshot is not None
    assert snapshot.windows[0].used_percent == 5
    assert seen == {
        "url": "https://api.neuralwatt.com/v1/quota",
        "auth": "Bearer test-key",
    }


def test_9router_claude_usage_uses_only_the_local_cli_token_and_preserves_windows(monkeypatch, tmp_path):
    """Claude subscription usage comes from 9router, never from a Claude OAuth token."""
    cli_secret = tmp_path / "cli-secret"
    cli_secret.write_text("local-cli-token\n", encoding="utf-8")
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("machine-identity\n", encoding="utf-8")
    seen = []

    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self):
            import json
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        seen.append((request.full_url, request.get_header("X-9r-cli-token")))
        if request.full_url.startswith("http://127.0.0.1:20128/api/providers/client"):
            return Response({"connections": [{"id": "claude-connection", "provider": "claude", "isActive": True}]})
        return Response({"quotas": {
            "session (5h)": {"remaining": 75, "resetAt": "2026-10-14T18:00:00Z"},
            "weekly (7d)": {"remaining": 60, "resetAt": "2026-10-20T18:00:00Z"},
        }})

    monkeypatch.setattr(local_usage, "_NINE_ROUTER_CLI_SECRET", cli_secret)
    monkeypatch.setattr(local_usage, "_NINE_ROUTER_MACHINE_ID", machine_id)
    monkeypatch.setattr(local_usage, "urlopen", fake_urlopen)

    snapshot = fetch_9router_claude_account_usage("http://127.0.0.1:20128/v1")

    assert snapshot is not None
    assert snapshot.provider == "9router-claude"
    assert snapshot.plan == "Claude via 9router"
    assert [(window.label, window.used_percent) for window in snapshot.windows] == [
        ("5 hours", 25.0), ("Weekly", 40.0),
    ]
    import hashlib
    expected_token = hashlib.sha256(b"machine-identity9r-cli-authlocal-cli-token").hexdigest()[:16]
    assert all(token == expected_token for _url, token in seen)
    assert [url for url, _token in seen] == [
        "http://127.0.0.1:20128/api/providers/client?page=1&pageSize=100&accountStatus=active&sort=priority",
        "http://127.0.0.1:20128/api/usage/claude-connection",
    ]


def test_neuralwatt_weekly_allowance_is_rendered_as_a_percent_window():
    snapshot = neuralwatt_quota_snapshot({
        "limits": {
            "weekly": {"limit": 80, "remaining": 20},
        },
    })

    assert snapshot is not None
    assert snapshot.provider == "neuralwatt"
    assert snapshot.windows[0].label == "Weekly"
    assert snapshot.windows[0].used_percent == 75


def test_neuralwatt_energy_subscription_is_rendered_as_the_usage_window():
    snapshot = neuralwatt_quota_snapshot({
        "subscription": {
            "plan": "basic",
            "kwh_included": 20.0,
            "kwh_used": 13.9023,
            "kwh_remaining": 6.0977,
            "current_period_end": "2026-05-11T05:05:25Z",
        },
        "usage": {"current_month": {"energy_kwh": 9.7278}},
    })

    assert snapshot is not None
    assert snapshot.plan == "Basic Plan"
    assert snapshot.windows[0].label == "Energy"
    assert snapshot.windows[0].used_percent == 69.5115
    assert snapshot.windows[0].reset_at is not None
    assert snapshot.windows[0].detail is None


def test_neuralwatt_quota_accepts_explicit_used_amounts():
    snapshot = neuralwatt_quota_snapshot({
        "quota": {"weekly": {"allowance": 100, "used": 5}},
    })

    assert snapshot is not None
    assert snapshot.windows[0].used_percent == 5


def test_neuralwatt_quota_reads_the_documented_weekly_key_allowance():
    snapshot = neuralwatt_quota_snapshot({
        "key": {"allowance": {
            "period": "weekly", "limit_usd": 40, "spent_usd": 2, "remaining_usd": 38,
        }},
        "subscription": None,
    })

    assert snapshot is not None
    assert snapshot.windows[0].label == "Weekly"
    assert snapshot.windows[0].used_percent == 5


def test_codex_desktop_usage_forwards_the_selected_account_id(monkeypatch):
    seen = {}

    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {"rate_limit": {
                "primary_window": {"used_percent": 55},
                "secondary_window": {"used_percent": 45},
            }}

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, url, headers):
            seen.update(url=url, headers=headers)
            return Response()

    monkeypatch.setattr(local_usage.httpx, "Client", lambda timeout: Client())

    snapshot = local_usage.fetch_codex_cli_account_usage({"access_token": "token", "account_id": "account"})

    assert snapshot is not None
    assert [window.used_percent for window in snapshot.windows] == [55, 45]
    assert seen["headers"]["ChatGPT-Account-Id"] == "account"


def test_codex_desktop_usage_preserves_epoch_reset_times(monkeypatch):
    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {"rate_limit": {
                "primary_window": {"used_percent": 55, "reset_at": 1_800_000_000},
            }}

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, *_args, **_kwargs): return Response()

    monkeypatch.setattr(local_usage.httpx, "Client", lambda timeout: Client())

    snapshot = local_usage.fetch_codex_cli_account_usage({"access_token": "token"})

    assert snapshot is not None
    assert snapshot.windows[0].reset_at is not None
    assert snapshot.windows[0].reset_at.year == 2027


def test_account_usage_resolves_an_auto_profile_to_codex_before_fetching(monkeypatch, tmp_path):
    """The literal config value ``auto`` must not bypass Codex account usage."""
    profile_home = tmp_path / "coding"
    profile_home.mkdir()
    (profile_home / "config.yaml").write_text("model:\n  provider: auto\n", encoding="utf-8")
    seen = []

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda _: profile_home)
    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", lambda _: Context())
    monkeypatch.setattr(routes, "j", lambda _handler, payload: seen.append(payload))

    agent_mod = types.ModuleType("agent")
    agent_mod.__path__ = []
    usage_mod = types.ModuleType("agent.account_usage")
    usage_mod.fetch_account_usage = lambda provider, **_: SimpleNamespace(
        available=True, provider=provider, plan=None,
        windows=(SimpleNamespace(label="Weekly", used_percent=95, reset_at=None, detail=None),),
    )
    runtime_mod = types.ModuleType("hermes_cli.runtime_provider")
    runtime_mod.resolve_runtime_provider = lambda **_: {"provider": "openai-codex", "base_url": None, "api_key": None}
    monkeypatch.setitem(sys.modules, "agent", agent_mod)
    monkeypatch.setitem(sys.modules, "agent.account_usage", usage_mod)
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", runtime_mod)

    assert routes._handle_account_usage(object(), SimpleNamespace(query="profile=coding")) is True
    assert seen[-1]["windows"][0]["used_percent"] == 95
    assert seen[-1]["provider"] == "openai-codex"


def test_account_usage_uses_neuralwatt_quota_when_agent_has_no_fetcher(monkeypatch, tmp_path):
    profile_home = tmp_path / "neural"
    profile_home.mkdir()
    (profile_home / "config.yaml").write_text(
        "model:\n  provider: custom:api-nw\n  base_url: https://api.neuralwatt.com/v1\n", encoding="utf-8"
    )
    seen = []

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda _: profile_home)
    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", lambda _: Context())
    monkeypatch.setattr(routes, "j", lambda _handler, payload: seen.append(payload))
    monkeypatch.setattr("api.account_usage.fetch_neuralwatt_account_usage", lambda *_: SimpleNamespace(
        available=True, provider="neuralwatt", plan=None,
        windows=(SimpleNamespace(label="Weekly", used_percent=25, reset_at=None, detail=None),),
    ))

    agent_mod = types.ModuleType("agent")
    agent_mod.__path__ = []
    usage_mod = types.ModuleType("agent.account_usage")
    usage_mod.fetch_account_usage = lambda *_args, **_kwargs: None
    runtime_mod = types.ModuleType("hermes_cli.runtime_provider")
    runtime_mod.resolve_runtime_provider = lambda **_: {
        "provider": "custom:api-nw", "base_url": "https://api.neuralwatt.com/v1", "api_key": "test-key",
    }
    monkeypatch.setitem(sys.modules, "agent", agent_mod)
    monkeypatch.setitem(sys.modules, "agent.account_usage", usage_mod)
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", runtime_mod)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=neural"))
    assert seen[-1]["provider"] == "neuralwatt"
    assert seen[-1]["windows"][0]["used_percent"] == 25


def test_account_usage_uses_profile_key_when_neuralwatt_runtime_resolution_fails(monkeypatch, tmp_path):
    profile_home = tmp_path / "neural-native"
    profile_home.mkdir()
    (profile_home / "config.yaml").write_text(
        "model:\n  provider: neuralwatt\n  api_key: profile-key\n", encoding="utf-8"
    )
    seen = []

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda _: profile_home)
    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", lambda _: Context())
    monkeypatch.setattr(routes, "j", lambda _handler, payload: seen.append(payload))
    monkeypatch.setattr("api.account_usage.fetch_neuralwatt_account_usage", lambda base, key: (
        AccountUsageSnapshot("neuralwatt", (AccountUsageWindow("Weekly", 12),))
        if base == "" and key == "profile-key" else None
    ))

    agent_mod = types.ModuleType("agent")
    agent_mod.__path__ = []
    usage_mod = types.ModuleType("agent.account_usage")
    usage_mod.fetch_account_usage = lambda *_args, **_kwargs: None
    runtime_mod = types.ModuleType("hermes_cli.runtime_provider")
    runtime_mod.resolve_runtime_provider = lambda **_: (_ for _ in ()).throw(RuntimeError("unavailable"))
    monkeypatch.setitem(sys.modules, "agent", agent_mod)
    monkeypatch.setitem(sys.modules, "agent.account_usage", usage_mod)
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", runtime_mod)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=neural-native"))
    assert seen[-1]["windows"][0]["used_percent"] == 12


def test_account_usage_reads_legacy_generic_key_for_neuralwatt_endpoint(monkeypatch, tmp_path):
    """Existing Profile-page saves under HERMES_API_KEY remain usable for quota."""
    profile_home = tmp_path / "neural-legacy"
    profile_home.mkdir()
    (profile_home / "config.yaml").write_text(
        "model:\n  provider: custom:api-nw\n  base_url: https://api.neuralwatt.com/v1\n",
        encoding="utf-8",
    )
    (profile_home / ".env").write_text("HERMES_API_KEY=legacy-profile-key\n", encoding="utf-8")
    seen = []

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda _: profile_home)
    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", lambda _: Context())
    monkeypatch.setattr(routes, "j", lambda _handler, payload: seen.append(payload))
    monkeypatch.setattr("api.account_usage.fetch_neuralwatt_account_usage", lambda _base, key: (
        AccountUsageSnapshot("neuralwatt", (AccountUsageWindow("Energy", 12),))
        if key == "legacy-profile-key" else None
    ))

    agent_mod = types.ModuleType("agent")
    agent_mod.__path__ = []
    usage_mod = types.ModuleType("agent.account_usage")
    usage_mod.fetch_account_usage = lambda *_args, **_kwargs: None
    runtime_mod = types.ModuleType("hermes_cli.runtime_provider")
    runtime_mod.resolve_runtime_provider = lambda **_: (_ for _ in ()).throw(RuntimeError("unavailable"))
    monkeypatch.setitem(sys.modules, "agent", agent_mod)
    monkeypatch.setitem(sys.modules, "agent.account_usage", usage_mod)
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", runtime_mod)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=neural-legacy"))

    assert seen[-1]["provider"] == "neuralwatt"
    assert seen[-1]["windows"][0]["used_percent"] == 12


def test_neuralwatt_account_usage_uses_a_short_profile_scoped_snapshot_cache(monkeypatch, tmp_path):
    """A profile switch must not repeatedly hit NeuralWatt's throttled quota endpoint."""
    profile_home = tmp_path / "neural-cache"
    profile_home.mkdir()
    (profile_home / "config.yaml").write_text(
        "model:\n  provider: custom:api-nw\n  base_url: https://api.neuralwatt.com/v1\n",
        encoding="utf-8",
    )
    (profile_home / ".env").write_text("HERMES_API_KEY=legacy-profile-key\n", encoding="utf-8")
    seen, calls = [], []

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda _: profile_home)
    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", lambda _: Context())
    monkeypatch.setattr(routes, "j", lambda _handler, payload: seen.append(payload))
    monkeypatch.setattr(routes, "_neuralwatt_usage_snapshot_cache", {})
    monkeypatch.setattr("api.account_usage.fetch_neuralwatt_account_usage", lambda *_: (
        calls.append(True) or AccountUsageSnapshot("neuralwatt", (AccountUsageWindow("Energy", 12),))
    ))

    agent_mod = types.ModuleType("agent")
    agent_mod.__path__ = []
    usage_mod = types.ModuleType("agent.account_usage")
    usage_mod.fetch_account_usage = lambda *_args, **_kwargs: None
    runtime_mod = types.ModuleType("hermes_cli.runtime_provider")
    runtime_mod.resolve_runtime_provider = lambda **_: (_ for _ in ()).throw(RuntimeError("unavailable"))
    monkeypatch.setitem(sys.modules, "agent", agent_mod)
    monkeypatch.setitem(sys.modules, "agent.account_usage", usage_mod)
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", runtime_mod)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=neural-cache"))
    routes._handle_account_usage(object(), SimpleNamespace(query="profile=neural-cache"))

    assert len(calls) == 1
    assert [payload["available"] for payload in seen] == [True, True]


def test_neuralwatt_rate_limit_keeps_a_visible_monthly_card_state(monkeypatch, tmp_path):
    """A first quota 429 is surfaced as temporary status, not indistinguishable disappearance."""
    profile_home = tmp_path / "neural-rate-limited"
    profile_home.mkdir()
    (profile_home / "config.yaml").write_text(
        "model:\n  provider: custom:api-nw\n  base_url: https://api.neuralwatt.com/v1\n",
        encoding="utf-8",
    )
    (profile_home / ".env").write_text("HERMES_API_KEY=legacy-profile-key\n", encoding="utf-8")
    seen = []

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda _: profile_home)
    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", lambda _: Context())
    monkeypatch.setattr(routes, "j", lambda _handler, payload: seen.append(payload))
    monkeypatch.setattr(routes, "_neuralwatt_usage_snapshot_cache", {})
    monkeypatch.setattr(
        "api.account_usage.fetch_neuralwatt_account_usage",
        lambda *_: (_ for _ in ()).throw(local_usage.NeuralWattQuotaRateLimited()),
    )

    agent_mod = types.ModuleType("agent")
    agent_mod.__path__ = []
    usage_mod = types.ModuleType("agent.account_usage")
    usage_mod.fetch_account_usage = lambda *_args, **_kwargs: None
    runtime_mod = types.ModuleType("hermes_cli.runtime_provider")
    runtime_mod.resolve_runtime_provider = lambda **_: (_ for _ in ()).throw(RuntimeError("unavailable"))
    monkeypatch.setitem(sys.modules, "agent", agent_mod)
    monkeypatch.setitem(sys.modules, "agent.account_usage", usage_mod)
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", runtime_mod)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=neural-rate-limited"))

    assert seen[-1] == {"available": False, "provider": "neuralwatt", "rate_limited": True}


def test_codex_profiles_prefer_the_read_only_codex_app_account_for_usage(monkeypatch, tmp_path):
    profile_home = tmp_path / "architecture"
    profile_home.mkdir()
    (profile_home / "config.yaml").write_text("model:\n  provider: auto\n", encoding="utf-8")
    seen = []

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): return False

    monkeypatch.setattr("api.profiles.get_hermes_home_for_profile", lambda _: profile_home)
    monkeypatch.setattr("api.profiles.cron_profile_context_for_home", lambda _: Context())
    monkeypatch.setattr(routes, "j", lambda _handler, payload: seen.append(payload))
    monkeypatch.setattr("api.account_usage.fetch_codex_cli_account_usage", lambda tokens: (
        AccountUsageSnapshot("openai-codex", (AccountUsageWindow("Weekly", 45),))
        if tokens.get("access_token") == "desktop-token" else None
    ))

    agent_mod = types.ModuleType("agent")
    agent_mod.__path__ = []
    usage_mod = types.ModuleType("agent.account_usage")
    fetch_calls = []
    usage_mod.fetch_account_usage = lambda provider, **kwargs: (
        fetch_calls.append((provider, kwargs)) or SimpleNamespace(
            available=True, provider=provider, plan=None,
            windows=(SimpleNamespace(label="Weekly", used_percent=45, reset_at=None, detail=None),),
        )
    )
    runtime_mod = types.ModuleType("hermes_cli.runtime_provider")
    runtime_mod.resolve_runtime_provider = lambda **_: {"provider": "openai-codex", "base_url": None, "api_key": None}
    codex_auth_mod = types.ModuleType("hermes_cli.auth_codex")
    codex_auth_mod._import_codex_cli_tokens = lambda: {"access_token": "desktop-token"}
    monkeypatch.setitem(sys.modules, "agent", agent_mod)
    monkeypatch.setitem(sys.modules, "agent.account_usage", usage_mod)
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", runtime_mod)
    monkeypatch.setitem(sys.modules, "hermes_cli.auth_codex", codex_auth_mod)

    routes._handle_account_usage(object(), SimpleNamespace(query="profile=architecture"))

    assert fetch_calls == []
    assert seen[-1]["windows"][0]["used_percent"] == 45
