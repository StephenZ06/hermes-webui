"""Job OS settings: per-profile, validated, revisioned, and never holding secrets."""

from __future__ import annotations

import io
import json
from urllib.parse import urlparse

import pytest

from api import profiles, routes
from api.job_os.settings import SettingsConflict, SettingsError, default_settings, load_settings, save_settings


class _Handler:
    def __init__(self, body: bytes = b"{}") -> None:
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, *_):
        pass

    def end_headers(self):
        pass


@pytest.fixture
def home(tmp_path, monkeypatch):
    state = {"name": "research"}
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: state["name"])
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path / state["name"])
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path / "base")
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: state.get("isolated", False))
    monkeypatch.setattr(routes, "_check_csrf", lambda _h: True)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *a, **k: True)
    for key in ("FIRECRAWL_API_URL", "JOB_OS_GMAIL_ADDRESS", "JOB_OS_GMAIL_APP_PASSWORD", "HERMES_GMAIL_ADDRESS", "HERMES_GMAIL_APP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    return state, tmp_path


def test_defaults_are_safe(home):
    s = load_settings()
    assert s["revision"] == 0
    assert s["notifications"]["email_enabled"] is False
    assert s["ai"] == {"provider": "openai-codex", "model": "gpt-5.6-luna", "reasoning_effort": "medium", "auto_analyze": True}
    assert s["applicant"]["email"] == ""
    assert "auto_apply" not in s, "Auto-apply was removed"


def test_save_merges_validates_and_bumps_revision(home):
    saved = save_settings({"scout": {"schedule_hours": 4}, "notifications": {"min_fit_score": 60}}, expected_revision=0)
    assert saved["revision"] == 1
    assert saved["scout"]["schedule_hours"] == 4 and saved["notifications"]["min_fit_score"] == 60
    assert saved["notifications"]["digest_hour"] == default_settings()["notifications"]["digest_hour"]
    assert load_settings() == saved


@pytest.mark.parametrize("patch", [
    {"scout": {"schedule_hours": 0}},
    {"auto_apply": {"enabled": True}},
    {"notifications": {"min_fit_score": 120}},
    {"notifications": {"to_address": "not-an-email"}},
    {"notifications": {"digest_hour": 25}},
    {"firecrawl": {"api_url": "javascript:alert(1)"}},
    {"ai": {"reasoning_effort": "ludicrous"}},
    {"applicant": {"email": "nope"}},
    {"applicant": {"full_name": "line\nbreak"}},
    {"applicant": {"linkedin_url": "ftp://x"}},
    {"unknown_section": {}},
    {"notifications": {"app_password": "abcd efgh ijkl mnop"}},
])
def test_invalid_or_secret_fields_are_rejected(home, patch):
    with pytest.raises(SettingsError):
        save_settings(patch, expected_revision=0)
    assert load_settings()["revision"] == 0


def test_stale_revision_is_a_conflict(home):
    save_settings({"scout": {"schedule_hours": 4}}, expected_revision=0)
    with pytest.raises(SettingsConflict):
        save_settings({"scout": {"schedule_hours": 8}}, expected_revision=0)


def test_settings_are_global_across_profiles(home):
    state, _ = home
    save_settings({"scout": {"schedule_hours": 4}}, expected_revision=0)
    state["name"] = "other"
    assert load_settings()["scout"]["schedule_hours"] == 4


def test_isolated_deployments_keep_settings_per_profile(home):
    state, _ = home
    state["isolated"] = True
    save_settings({"scout": {"schedule_hours": 4}}, expected_revision=0)
    state["name"] = "other"
    assert load_settings()["scout"]["schedule_hours"] == default_settings()["scout"]["schedule_hours"]


def test_http_get_reports_status_with_booleans_only(home, monkeypatch):
    monkeypatch.setenv("JOB_OS_GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("JOB_OS_GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    h = _Handler()
    assert routes.handle_get(h, urlparse("/api/job-os/settings")) is True
    body = json.loads(h.wfile.getvalue())
    assert h.status == 200
    gmail_status = body["status"]["gmail"]
    assert gmail_status["address"] is True and gmail_status["app_password"] is True
    assert gmail_status["address_hint"] == "m***@gmail.com"
    assert body["status"]["firecrawl"]["state"] == "not_configured"
    assert "abcd efgh" not in h.wfile.getvalue().decode()


def test_http_post_saves_and_maps_errors(home):
    ok = _Handler(json.dumps({"settings": {"scout": {"schedule_hours": 12}}, "expected_revision": 0}).encode())
    assert routes.handle_post(ok, urlparse("/api/job-os/settings")) is True
    assert ok.status == 200 and json.loads(ok.wfile.getvalue())["settings"]["scout"]["schedule_hours"] == 12
    bad = _Handler(json.dumps({"settings": {"scout": {"schedule_hours": -1}}, "expected_revision": 1}).encode())
    routes.handle_post(bad, urlparse("/api/job-os/settings"))
    assert bad.status == 400
    stale = _Handler(json.dumps({"settings": {"scout": {"schedule_hours": 6}}, "expected_revision": 0}).encode())
    routes.handle_post(stale, urlparse("/api/job-os/settings"))
    assert stale.status == 409
