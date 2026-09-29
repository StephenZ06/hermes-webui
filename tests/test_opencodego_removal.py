"""Regression coverage for retiring the local OpenCode Go integration."""

import json

import api.providers as providers
from api.opencodego_cleanup import remove_opencodego_state


def test_retired_opencodego_is_not_returned_by_provider_api(monkeypatch):
    monkeypatch.setattr(providers, "get_config", lambda: {})
    providers.invalidate_providers_cache()

    result = providers.get_providers()

    assert all(row["id"] != "opencode-go" for row in result["providers"])


def test_cleanup_removes_only_opencodego_state(tmp_path):
    home = tmp_path / ".hermes"
    profile = home / "profiles" / "coding"
    profile.mkdir(parents=True)
    (home / ".env").write_text(
        "OPENCODE_GO_API_KEY=remove-me\nOPENCODE_API_KEY=keep-me\n", encoding="utf-8"
    )
    (profile / "auth.json").write_text(
        json.dumps({"credential_pool": {"opencode-go": [{"token": "remove"}], "openai": [{"token": "keep"}]}}),
        encoding="utf-8",
    )
    (profile / "config.yaml").write_text(
        "model:\n  provider: opencode-go\n  default: glm-5\nproviders:\n  opencode-go:\n    api_key: remove\n  openai:\n    api_key: keep\n",
        encoding="utf-8",
    )

    summary = remove_opencodego_state(home)

    assert summary["env_entries_removed"] == 1
    assert "OPENCODE_GO_API_KEY" not in (home / ".env").read_text(encoding="utf-8")
    assert "OPENCODE_API_KEY=keep-me" in (home / ".env").read_text(encoding="utf-8")
    auth = json.loads((profile / "auth.json").read_text(encoding="utf-8"))
    assert "opencode-go" not in auth["credential_pool"]
    assert "openai" in auth["credential_pool"]
    config = (profile / "config.yaml").read_text(encoding="utf-8")
    assert "opencode-go" not in config
    assert "provider:" not in config
