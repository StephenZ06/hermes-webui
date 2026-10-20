"""Profiles page edits one profile's provider setup without switching to it."""

import json
import os
import stat
from pathlib import Path

import pytest
import yaml

from api import profile_providers as pp


@pytest.fixture
def homes(tmp_path, monkeypatch):
    import api.profiles as profiles

    root = tmp_path / "root"
    root.mkdir()
    (root / "profiles" / "docs").mkdir(parents=True)
    (root / "profiles" / "work").mkdir(parents=True)

    def home_for(name):
        return root if name in ("", "default", None) else root / "profiles" / name

    monkeypatch.setattr(profiles, "get_hermes_home_for_profile", home_for)
    monkeypatch.setattr(profiles, "_is_root_profile", lambda name: name in ("default",))
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", root)
    monkeypatch.setattr("api.config.invalidate_models_cache", lambda *a, **k: None)
    (root / "profiles" / "docs" / "config.yaml").write_text("model:\n  provider: opencode-go\n  default: glm-5\n")
    return root


def _cfg(home):
    return yaml.safe_load((home / "config.yaml").read_text())


def test_api_key_is_saved_to_that_profile_only_and_never_reaches_the_process_env(homes, monkeypatch):
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    docs = homes / "profiles" / "docs"

    assert pp.overview("docs")["main"]["status"]["state"] == "key"
    pp.set_api_key("docs", "opencode-go", "sk-123")

    env_file = docs / ".env"
    assert "OPENCODE_GO_API_KEY=sk-123" in env_file.read_text()
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert "OPENCODE_GO_API_KEY" not in os.environ
    assert not (homes / "profiles" / "work" / ".env").exists()
    view = pp.overview("docs")
    assert view["main"]["status"]["state"] == "ready"
    assert "sk-123" not in json.dumps(view)

    pp.set_api_key("docs", "opencode-go", None)
    assert "OPENCODE_GO_API_KEY" not in env_file.read_text()


def test_endpoint_preset_becomes_the_main_model_and_keeps_its_key_on_edit(homes):
    pp.save_endpoint("docs", {"display": "9Router", "base_url": "http://localhost:20128/v1/",
                              "api_key": "rk", "model": "cc/claude", "make_main": True})
    cfg = _cfg(homes / "profiles" / "docs")
    assert cfg["providers"]["9router"] == {"name": "9Router", "base_url": "http://localhost:20128/v1",
                                          "transport": "chat_completions", "default_model": "cc/claude", "api_key": "rk"}
    assert cfg["model"] == {"provider": "custom:9router", "default": "cc/claude", "base_url": "http://localhost:20128/v1"}

    pp.save_endpoint("docs", {"id": "9router", "display": "9Router", "base_url": "http://localhost:20128/v1", "model": "cc/other"})
    assert _cfg(homes / "profiles" / "docs")["providers"]["9router"]["api_key"] == "rk"
    view = pp.overview("docs")
    assert view["endpoints"][0]["has_key"] is True and "rk" not in json.dumps(view)

    with pytest.raises(pp.ProfileProviderError):
        pp.delete_endpoint("docs", "9router")  # still the main model


def test_fallback_chain_is_deduplicated_capped_and_carries_endpoint_urls(homes):
    pp.save_endpoint("docs", {"display": "LM Box", "base_url": "http://box:1234/v1", "model": "m"})
    items = [{"provider": "custom:lm-box", "model": "m"}, {"provider": "custom:lm-box", "model": "M"},
             {"provider": "openrouter", "model": "x"}, {"provider": "", "model": "y"}]
    pp.set_fallbacks("docs", items + [{"provider": f"p{i}", "model": "z"} for i in range(9)])

    chain = _cfg(homes / "profiles" / "docs")["fallback_providers"]
    assert chain[0] == {"provider": "custom:lm-box", "model": "m", "base_url": "http://box:1234/v1"}
    assert chain[1] == {"provider": "openrouter", "model": "x"}
    assert len(chain) == 5


def test_keys_and_endpoints_copy_between_profiles_but_sign_ins_do_not(homes):
    pp.set_api_key("work", "openrouter", "or-key")
    pp.copy_credentials("work", "docs", "openrouter")
    assert "OPENROUTER_API_KEY=or-key" in (homes / "profiles" / "docs" / ".env").read_text()

    with pytest.raises(pp.ProfileProviderError):
        pp.copy_credentials("work", "docs", "openai-codex")
    with pytest.raises(pp.ProfileProviderError):
        pp.copy_credentials("work", "docs", "anthropic-missing-key")


def test_bad_input_is_rejected(homes):
    with pytest.raises(pp.ProfileProviderError):
        pp.overview("ghost")
    with pytest.raises(pp.ProfileProviderError):
        pp.save_endpoint("docs", {"display": "x", "base_url": "file:///etc/passwd"})
    with pytest.raises(pp.ProfileProviderError):
        pp.set_api_key("docs", "openai-codex", "k")
    with pytest.raises(pp.ProfileProviderError):
        pp.set_api_key("docs", "openrouter", "a\nB=c")


def test_endpoint_test_reports_an_unreachable_server(homes):
    pp.save_endpoint("docs", {"display": "Dead", "base_url": "http://127.0.0.1:9/v1", "model": "m"})
    result = pp.test_route("docs", "custom:dead")
    assert result["ok"] is False and "Couldn't reach" in result["message"]
