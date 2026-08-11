"""Coverage for the profile-edit feature: update_profile_api() and the new
POST /api/profile/update route.

Before this change there was no update-profile capability anywhere in the
WebUI — only create and delete. This adds:
  - api.profiles._validate_profile_reasoning_effort / _write_reasoning_effort_to_config
    (shared by update_profile_api and reused by the read side via
    _read_profile_reasoning_effort so list/detail/edit all agree on the
    same agent.reasoning_effort key the CLI's /reasoning command writes).
  - api.profiles._read_profile_base_url (list_profiles_api() rows never
    exposed base_url at all; the edit form needs it to pre-fill).
  - api.profiles.update_profile_api() — the actual update logic.
  - POST /api/profile/update in api/routes.py.
"""
import io
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

import api.profiles as profiles


# ─────────────────────────────────────────────────────────────────────────────
# _validate_profile_reasoning_effort
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateProfileReasoningEffort:
    def test_none_stays_none(self):
        assert profiles._validate_profile_reasoning_effort(None) is None

    def test_blank_normalizes_to_none(self):
        assert profiles._validate_profile_reasoning_effort("") is None
        assert profiles._validate_profile_reasoning_effort("   ") is None

    def test_default_normalizes_to_none(self):
        assert profiles._validate_profile_reasoning_effort("default") is None
        assert profiles._validate_profile_reasoning_effort("DEFAULT") is None

    def test_valid_efforts_pass_through_lowercased(self):
        assert profiles._validate_profile_reasoning_effort("HIGH") == "high"
        assert profiles._validate_profile_reasoning_effort("none") == "none"
        assert profiles._validate_profile_reasoning_effort("xhigh") == "xhigh"

    def test_unknown_value_raises(self):
        with pytest.raises(ValueError, match="Unknown reasoning effort"):
            profiles._validate_profile_reasoning_effort("bogus")


# ─────────────────────────────────────────────────────────────────────────────
# _write_reasoning_effort_to_config / _read_profile_reasoning_effort round-trip
# ─────────────────────────────────────────────────────────────────────────────

class TestReasoningEffortReadWrite:
    def test_read_defaults_to_default_string_when_unset(self, tmp_path):
        assert profiles._read_profile_reasoning_effort(tmp_path) == "default"

    def test_write_then_read_round_trips(self, tmp_path):
        profiles._write_reasoning_effort_to_config(tmp_path, "high")
        assert profiles._read_profile_reasoning_effort(tmp_path) == "high"
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["agent"]["reasoning_effort"] == "high"

    def test_write_none_clears_existing_override(self, tmp_path):
        profiles._write_reasoning_effort_to_config(tmp_path, "high")
        profiles._write_reasoning_effort_to_config(tmp_path, None)
        assert profiles._read_profile_reasoning_effort(tmp_path) == "default"
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert "reasoning_effort" not in (cfg.get("agent") or {})

    def test_write_preserves_other_agent_and_top_level_keys(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            yaml.dump({"agent": {"max_turns": 90}, "model": {"default": "gpt-5.5"}}),
            encoding="utf-8",
        )
        profiles._write_reasoning_effort_to_config(tmp_path, "medium")
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["agent"]["max_turns"] == 90
        assert cfg["agent"]["reasoning_effort"] == "medium"
        assert cfg["model"]["default"] == "gpt-5.5"


# ─────────────────────────────────────────────────────────────────────────────
# _read_profile_base_url
# ─────────────────────────────────────────────────────────────────────────────

class TestReadProfileBaseUrl:
    def test_missing_config_returns_none(self, tmp_path):
        assert profiles._read_profile_base_url(tmp_path) is None

    def test_reads_configured_value(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            yaml.dump({"model": {"base_url": "https://gateway.example/v1"}}),
            encoding="utf-8",
        )
        assert profiles._read_profile_base_url(tmp_path) == "https://gateway.example/v1"


# ─────────────────────────────────────────────────────────────────────────────
# update_profile_api
# ─────────────────────────────────────────────────────────────────────────────

def _fake_row(profile_dir: Path, name: str) -> dict:
    """Build a list_profiles_api()-shaped row that reflects the CURRENT
    on-disk config.yaml, so update_profile_api's re-lookup after writing
    genuinely proves the write happened rather than echoing a stale fixture.
    """
    cfg = {}
    cfg_path = profile_dir / "config.yaml"
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            cfg = loaded
    model_cfg = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    return {
        "name": name,
        "path": str(profile_dir),
        "is_default": False,
        "is_active": False,
        "gateway_running": False,
        "model": model_cfg.get("default"),
        "provider": model_cfg.get("provider"),
        "base_url": profiles._read_profile_base_url(profile_dir),
        "has_env": (profile_dir / ".env").exists(),
        "visible": True,
        "skill_count": 0,
        "enabled_skills": 0,
        "total_skills": 0,
        "reasoning_effort": profiles._read_profile_reasoning_effort(profile_dir),
    }


@pytest.fixture
def existing_profile(tmp_path, monkeypatch):
    profile_dir = tmp_path / "profiles" / "research"
    profile_dir.mkdir(parents=True)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(profiles, "list_profiles_api", lambda: [_fake_row(profile_dir, "research")])
    monkeypatch.setattr(profiles, "_validate_profile_model_selection", lambda *a, **k: None)
    monkeypatch.setattr(profiles, "_SKILLS_STATS_CACHE", {})
    monkeypatch.setattr(profiles, "_invalidate_list_profiles_cache", lambda: None)
    return profile_dir


class TestUpdateProfileApi:
    def test_happy_path_writes_model_provider_base_url_and_reasoning_effort(self, existing_profile):
        result = profiles.update_profile_api(
            "research",
            base_url="https://gateway.example/v1",
            default_model="anthropic/claude-opus-4.6",
            model_provider="nous",
            reasoning_effort="high",
        )
        cfg = yaml.safe_load((existing_profile / "config.yaml").read_text())
        assert cfg["model"]["base_url"] == "https://gateway.example/v1"
        assert cfg["model"]["default"] == "anthropic/claude-opus-4.6"
        assert cfg["model"]["provider"] == "nous"
        assert cfg["agent"]["reasoning_effort"] == "high"
        assert result["name"] == "research"
        assert result["reasoning_effort"] == "high"
        assert result["base_url"] == "https://gateway.example/v1"

    def test_name_is_not_editable_input(self, existing_profile):
        """The route/API only ever accept name as a lookup key -- there is no
        field that renames a profile. Calling update on a profile that exists
        under a different name raises rather than silently creating one."""
        with pytest.raises(ValueError, match="does not exist"):
            profiles.update_profile_api("does-not-exist", base_url="http://x")

    def test_reasoning_effort_omitted_leaves_existing_value_untouched(self, existing_profile):
        profiles.update_profile_api("research", reasoning_effort="high")
        # A second update that doesn't mention reasoning_effort must not clear it.
        profiles.update_profile_api("research", base_url="http://localhost:11434")
        assert profiles._read_profile_reasoning_effort(existing_profile) == "high"

    def test_reasoning_effort_default_clears_existing_override(self, existing_profile):
        profiles.update_profile_api("research", reasoning_effort="high")
        profiles.update_profile_api("research", reasoning_effort="default")
        assert profiles._read_profile_reasoning_effort(existing_profile) == "default"

    def test_rejects_invalid_reasoning_effort_before_writing_anything(self, existing_profile):
        with pytest.raises(ValueError, match="Unknown reasoning effort"):
            profiles.update_profile_api(
                "research",
                base_url="http://localhost:11434",
                reasoning_effort="not-a-real-level",
            )
        # Nothing should have been written to disk -- validation happens
        # before any config.yaml mutation.
        assert not (existing_profile / "config.yaml").exists()

    def test_blocked_in_isolated_profile_mode(self, existing_profile, monkeypatch):
        monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: True)
        with pytest.raises(PermissionError):
            profiles.update_profile_api("research", reasoning_effort="high")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/profile/update route
# ─────────────────────────────────────────────────────────────────────────────

class _FakeHandler:
    def __init__(self, body_bytes: bytes = b""):
        self.status = None
        self.sent_headers = []
        self.body = bytearray()
        self.wfile = self
        self.rfile = io.BytesIO(body_bytes)
        self.headers = {"Content-Length": str(len(body_bytes))}
        self.request = None
        self.client_address = ("127.0.0.1", 0)

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)

    def json_body(self):
        return json.loads(bytes(self.body).decode("utf-8"))


def _post_profile_update(body: dict):
    from api.routes import handle_post

    handler = _FakeHandler(json.dumps(body).encode("utf-8"))
    handle_post(handler, urlparse("http://example.com/api/profile/update"))
    return handler


class TestProfileUpdateRoute:
    def test_route_requires_name(self):
        handler = _post_profile_update({})
        assert handler.status == 400

    def test_route_rejects_invalid_base_url(self):
        handler = _post_profile_update({"name": "research", "base_url": "ftp://nope"})
        assert handler.status == 400

    def test_route_calls_update_profile_api_and_returns_ok(self, monkeypatch):
        captured = {}

        def fake_update(name, **kwargs):
            captured["name"] = name
            captured["kwargs"] = kwargs
            return {"name": name, "reasoning_effort": kwargs.get("reasoning_effort")}

        monkeypatch.setattr("api.profiles.update_profile_api", fake_update)
        handler = _post_profile_update({
            "name": "research",
            "base_url": "https://gateway.example/v1",
            "default_model": "gpt-5.5",
            "model_provider": "openai-codex",
            "reasoning_effort": "high",
        })
        assert handler.status == 200
        payload = handler.json_body()
        assert payload["ok"] is True
        assert payload["profile"]["name"] == "research"
        assert captured["name"] == "research"
        assert captured["kwargs"]["base_url"] == "https://gateway.example/v1"
        assert captured["kwargs"]["default_model"] == "gpt-5.5"
        assert captured["kwargs"]["model_provider"] == "openai-codex"
        assert captured["kwargs"]["reasoning_effort"] == "high"

    def test_route_omitted_reasoning_effort_passes_none(self, monkeypatch):
        captured = {}

        def fake_update(name, **kwargs):
            captured["kwargs"] = kwargs
            return {"name": name}

        monkeypatch.setattr("api.profiles.update_profile_api", fake_update)
        handler = _post_profile_update({"name": "research"})
        assert handler.status == 200
        assert captured["kwargs"]["reasoning_effort"] is None

    def test_route_blank_reasoning_effort_is_passed_through_not_dropped(self, monkeypatch):
        """An explicit '' means 'clear the override' -- the route must forward
        it rather than treating it the same as an omitted field (None)."""
        captured = {}

        def fake_update(name, **kwargs):
            captured["kwargs"] = kwargs
            return {"name": name}

        monkeypatch.setattr("api.profiles.update_profile_api", fake_update)
        handler = _post_profile_update({"name": "research", "reasoning_effort": ""})
        assert handler.status == 200
        assert captured["kwargs"]["reasoning_effort"] == ""

    def test_route_maps_permission_error_to_403(self, monkeypatch):
        def fake_update(name, **kwargs):
            raise PermissionError("nope")

        monkeypatch.setattr("api.profiles.update_profile_api", fake_update)
        handler = _post_profile_update({"name": "research"})
        assert handler.status == 403

    def test_route_maps_value_error_to_400(self, monkeypatch):
        def fake_update(name, **kwargs):
            raise ValueError("Unknown reasoning effort 'bogus'.")

        monkeypatch.setattr("api.profiles.update_profile_api", fake_update)
        handler = _post_profile_update({"name": "research", "reasoning_effort": "bogus"})
        assert handler.status == 400
