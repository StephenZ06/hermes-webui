"""Every WebUI reader/writer of profile env honours the shared secrets file."""

from __future__ import annotations

import pytest

from api import profiles, providers, shared_env


@pytest.fixture
def home(tmp_path, monkeypatch):
    work = tmp_path / "profiles" / "work"
    work.mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "secrets.env").write_text("OPENROUTER_API_KEY=sk-or-v1-sharedsharedshared\nJOB_OS_GMAIL_ADDRESS=me@gmail.com\n")
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: work)
    monkeypatch.setattr(providers, "_get_hermes_home", lambda: work)
    for key in ("OPENROUTER_API_KEY", "JOB_OS_GMAIL_ADDRESS"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path, work


def test_provider_key_in_shared_file_counts_as_configured(home):
    assert providers._provider_has_key("openrouter") is True
    assert providers._get_provider_api_key("openrouter") == "sk-or-v1-sharedsharedshared"


def test_agent_runtime_env_includes_shared_keys(home):
    _, work = home
    env = profiles.get_profile_runtime_env(work)
    assert env.get("OPENROUTER_API_KEY") == "sk-or-v1-sharedsharedshared"


def test_job_os_reads_shared_gmail(home):
    from api.job_os.env import profile_env_value
    assert profile_env_value("JOB_OS_GMAIL_ADDRESS") == ("me@gmail.com", "profile")


def test_saving_a_provider_key_writes_the_shared_file(home, monkeypatch):
    base, work = home
    monkeypatch.setattr(providers, "invalidate_models_cache", lambda: None, raising=False)
    result = providers.set_provider_key("openrouter", "sk-or-v1-newnewnewnew")
    assert result.get("ok") is True, result
    assert shared_env.parse_env_file(base / "shared" / "secrets.env")["OPENROUTER_API_KEY"] == "sk-or-v1-newnewnewnew"
    assert "OPENROUTER_API_KEY" not in shared_env.parse_env_file(work / ".env")
