"""Profiles page can sign any profile in to its provider (own auth.json)."""

import json
from pathlib import Path

import pytest

from api import oauth


@pytest.fixture
def homes(tmp_path, monkeypatch):
    root = tmp_path / "profiles"

    def home_for(name):
        return tmp_path / "default" if name in ("", "default", None) else root / name

    import api.profiles as profiles

    monkeypatch.setattr(profiles, "get_hermes_home_for_profile", home_for)
    for name in ("docs-gits", "local-model"):
        (root / name).mkdir(parents=True)
    (tmp_path / "default").mkdir()
    (root / "docs-gits" / "config.yaml").write_text("model:\n  provider: openai-codex\n  default: gpt-5\n")
    (root / "local-model" / "config.yaml").write_text("model:\n  provider: custom:lm-studio\n")
    return tmp_path


def test_status_reports_a_codex_profile_without_credentials(homes):
    status = oauth.profile_oauth_status("docs-gits")

    assert status == {"profile": "docs-gits", "provider": "openai-codex", "oauth_supported": True, "signed_in": False}


def test_status_sees_a_pool_credential_and_never_returns_tokens(homes):
    auth = {"credential_pool": {"openai-codex": [{"access_token": "secret-token", "source": "manual:device_code"}]}}
    (homes / "profiles" / "docs-gits" / "auth.json").write_text(json.dumps(auth))

    status = oauth.profile_oauth_status("docs-gits")

    assert status["signed_in"] is True
    assert "secret-token" not in json.dumps(status)


def test_non_oauth_provider_is_not_offered_a_sign_in(homes):
    assert oauth.profile_oauth_status("local-model")["oauth_supported"] is False


def test_sign_in_targets_the_named_profile_and_rejects_unknown_ones(homes):
    assert oauth._oauth_target_home({"profile": "docs-gits"}) == homes / "profiles" / "docs-gits"
    with pytest.raises(ValueError):
        oauth._oauth_target_home({"profile": "missing"})


def test_codex_tokens_are_written_to_the_chosen_profile(homes, monkeypatch):
    monkeypatch.setattr(oauth, "_invalidate_provider_state_caches", lambda provider: None)
    target = oauth._oauth_target_home({"profile": "docs-gits"})
    oauth._persist_codex_credentials(target, {"access_token": "a", "refresh_token": "r"})

    assert oauth.profile_oauth_status("docs-gits")["signed_in"] is True
    assert not (homes / "default" / "auth.json").exists()
