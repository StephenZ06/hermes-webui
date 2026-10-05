"""Connect Gmail: verify first, save to the shared secrets file, never echo the password."""

from __future__ import annotations

import io
import json
from urllib.parse import urlparse

import pytest

from api import profiles, routes, shared_env
from api.job_os import gmail


class _Handler:
    def __init__(self, body=b"{}"):
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
def base(tmp_path, monkeypatch):
    work = tmp_path / "profiles" / "work"
    work.mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "secrets.env").write_text("")
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: work)
    monkeypatch.setattr(routes, "_check_csrf", lambda _h: True)
    monkeypatch.setattr(routes, "_guard_request_session_visibility", lambda *a, **k: True)
    for key in (gmail.ADDRESS_KEY, gmail.PASSWORD_KEY):
        monkeypatch.delenv(key, raising=False)
    return tmp_path, work


def test_connect_verifies_then_writes_the_shared_file(base):
    root, work = base
    seen = []
    result = gmail.connect(" me@gmail.com ", "abcd efgh ijkl mnop", verify=lambda a, p: seen.append((a, p)))
    assert seen == [("me@gmail.com", "abcdefghijklmnop")]
    assert result == {"address": True, "app_password": True, "address_hint": "m***@gmail.com", "scope": "shared"}
    stored = shared_env.parse_env_file(root / "shared" / "secrets.env")
    assert stored[gmail.ADDRESS_KEY] == "me@gmail.com" and stored[gmail.PASSWORD_KEY] == "abcdefghijklmnop"
    assert not (work / ".env").exists()


def test_failed_verification_writes_nothing(base):
    root, _ = base

    def reject(*_):
        raise gmail.GmailError("Gmail rejected this address and app password.")

    with pytest.raises(gmail.GmailError):
        gmail.connect("me@gmail.com", "abcdefghijklmnop", verify=reject)
    assert gmail.ADDRESS_KEY not in shared_env.parse_env_file(root / "shared" / "secrets.env")


@pytest.mark.parametrize("address,password", [("nope", "abcdefghijklmnop"), ("me@gmail.com", "short"), ("me@gmail.com", "abcd-efgh-ijkl-mnop")])
def test_bad_input_is_rejected_before_any_login(base, address, password):
    with pytest.raises(gmail.GmailError):
        gmail.connect(address, password, verify=lambda *_: pytest.fail("must not log in"))


def test_disconnect_removes_both_values(base):
    gmail.connect("me@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    assert gmail.disconnect() == {"address": False, "app_password": False, "address_hint": "", "scope": "shared"}


def test_test_email_goes_to_the_connected_account_by_default(base):
    gmail.connect("me@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    sent = []
    to = gmail.send_test(sender=lambda msg, a, p: sent.append((msg["To"], msg["Subject"], msg["From"], a)))
    assert to == "me@gmail.com"
    assert sent == [("me@gmail.com", "Hermes Jobs: test notification", "Hermes Jobs <me@gmail.com>", "me@gmail.com")]


def test_test_email_goes_to_the_send_to_address_when_set(base):
    gmail.connect("bot@gmail.com", "abcdefghijklmnop", verify=lambda *_: None)
    sent = []
    assert gmail.send_test("main@gmail.com", sender=lambda msg, a, p: sent.append((msg["From"], msg["To"]))) == "main@gmail.com"
    assert sent == [("Hermes Jobs <bot@gmail.com>", "main@gmail.com")]


def test_http_connect_never_returns_the_password(base, monkeypatch):
    monkeypatch.setattr(gmail, "verify_login", lambda *_: None)
    body = json.dumps({"address": "me@gmail.com", "app_password": "abcd efgh ijkl mnop"}).encode()
    h = _Handler(body)
    assert routes.handle_post(h, urlparse("/api/job-os/gmail")) is True
    assert h.status == 200
    text = h.wfile.getvalue().decode()
    assert "abcd" not in text and "efgh" not in text
    assert json.loads(text)["gmail"]["address"] is True


def test_http_connect_maps_rejection_to_400(base, monkeypatch):
    def reject(*_):
        raise gmail.GmailError("Gmail rejected this address and app password.")

    monkeypatch.setattr(gmail, "verify_login", reject)
    h = _Handler(json.dumps({"address": "me@gmail.com", "app_password": "abcdefghijklmnop"}).encode())
    routes.handle_post(h, urlparse("/api/job-os/gmail"))
    assert h.status == 400 and "rejected" in json.loads(h.wfile.getvalue())["error"]
