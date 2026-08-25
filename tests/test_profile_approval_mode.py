"""Coverage for the per-profile approval-mode Settings toggle.

Mirrors tests/test_profile_update_endpoint.py's TestReasoningEffortReadWrite
shape: api.profiles._read_profile_approval_mode / _write_approval_mode_to_config
round-trip a profile's config.yaml the same way the reasoning-effort pair
does, just keyed on approvals.mode instead of agent.reasoning_effort.
"""
import io
import json
from urllib.parse import urlparse

import yaml

import api.profiles as profiles


class TestApprovalModeReadWrite:
    def test_read_defaults_to_smart_when_unset(self, tmp_path):
        assert profiles._read_profile_approval_mode(tmp_path) == "smart"

    def test_write_then_read_round_trips(self, tmp_path):
        profiles._write_approval_mode_to_config(tmp_path, "off")
        assert profiles._read_profile_approval_mode(tmp_path) == "off"
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["approvals"]["mode"] == "off"

    def test_write_preserves_other_approvals_and_top_level_keys(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            yaml.dump({
                "approvals": {"timeout": 300, "cron_mode": "deny"},
                "model": {"default": "gpt-5.5"},
            }),
            encoding="utf-8",
        )
        profiles._write_approval_mode_to_config(tmp_path, "manual")
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["approvals"]["mode"] == "manual"
        assert cfg["approvals"]["timeout"] == 300
        assert cfg["approvals"]["cron_mode"] == "deny"
        assert cfg["model"]["default"] == "gpt-5.5"

    def test_read_ignores_invalid_stored_value(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            yaml.dump({"approvals": {"mode": "bogus"}}), encoding="utf-8",
        )
        assert profiles._read_profile_approval_mode(tmp_path) == "smart"

    def test_read_missing_config_file_returns_smart(self, tmp_path):
        assert profiles._read_profile_approval_mode(tmp_path / "does-not-exist") == "smart"


class TestValidApprovalModesConstant:
    def test_matches_hermes_agent_valid_modes(self):
        # hermes_cli/approval_mode.py: VALID_APPROVAL_MODES = ("manual", "smart", "off")
        assert profiles.VALID_APPROVAL_MODES == ("manual", "smart", "off")


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


def _post_set_approval_mode(body: dict):
    from api.routes import handle_post

    handler = _FakeHandler(json.dumps(body).encode("utf-8"))
    handle_post(handler, urlparse("http://example.com/api/profiles/set_approval_mode"))
    return handler


class TestSetApprovalModeRoute:
    def test_route_requires_profile_and_mode(self):
        handler = _post_set_approval_mode({})
        assert handler.status == 400

    def test_route_rejects_invalid_mode(self, monkeypatch):
        monkeypatch.setattr(
            "api.profiles.list_profiles_api",
            lambda: [{"name": "research", "path": "/tmp/does-not-matter"}],
        )
        handler = _post_set_approval_mode({"profile": "research", "mode": "bogus"})
        assert handler.status == 400

    def test_route_rejects_unknown_profile(self, monkeypatch):
        monkeypatch.setattr("api.profiles.list_profiles_api", lambda: [])
        handler = _post_set_approval_mode({"profile": "ghost", "mode": "off"})
        assert handler.status == 404

    def test_route_writes_mode_and_returns_ok(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "api.profiles.list_profiles_api",
            lambda: [{"name": "research", "path": str(tmp_path)}],
        )
        handler = _post_set_approval_mode({"profile": "research", "mode": "off"})
        assert handler.status == 200
        payload = handler.json_body()
        assert payload["ok"] is True
        assert payload["profile"] == "research"
        assert payload["mode"] == "off"
        assert profiles._read_profile_approval_mode(tmp_path) == "off"
