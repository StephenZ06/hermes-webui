"""A profile-bound delegation session must survive its own first request.

hermes-agent's ``delegate_to_profile`` mints a session bound to the TARGET
profile and drives that profile's turn over authenticated loopback HTTP
(``/api/profile/switch`` -> ``/api/session/new`` -> ``/api/chat``).

The ordering here is the whole trick, and it is not obvious. ``check_auth``
rejects a request whose session ``bound_profile`` does not match the request's
active profile, and ``server.py`` resolves that active profile from the signed
``hermes_profile`` cookie BEFORE dispatch. So a bound session that waited to
pick up its profile cookie from ``/api/profile/switch``'s ``Set-Cookie`` would
be 403'd on the very request that was supposed to establish it. The tool
therefore sends the pre-signed profile cookie from request one.

These tests pin that contract from the server side: with both cookies the
bound session is accepted for the target profile, and it is still refused for
every other profile -- which is what makes the credential safe to mint.
"""
from __future__ import annotations

import pytest


class _FakeHandler:
    def __init__(self, cookie_header: str = ""):
        self.headers = {"Cookie": cookie_header} if cookie_header else {}
        self.status = None
        self.body = bytearray()
        self.wfile = self

    # -- minimal BaseHTTPRequestHandler surface used by check_auth --
    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        pass

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)


@pytest.fixture
def auth_env(tmp_path, monkeypatch):
    """Auth enabled, isolated session store, request profile under our control."""
    import api.auth as auth
    import api.profiles as profiles

    monkeypatch.setattr(auth, "STATE_DIR", tmp_path)
    monkeypatch.setattr(auth, "_SESSIONS_FILE", tmp_path / ".sessions.json")
    monkeypatch.setattr(auth, "_sessions", {})
    monkeypatch.setattr(auth, "is_auth_enabled", lambda: True)
    monkeypatch.setattr(auth, "is_trusted_auth_enabled", lambda: False)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    yield auth
    profiles.clear_request_profile()


def _cookie_header(auth, session_cookie: str, profile: str | None) -> str:
    from api.helpers import get_profile_cookie_name

    parts = [f"{auth._resolve_cookie_name()}={session_cookie}"]
    if profile is not None:
        signed = auth.sign_profile_cookie_value(profile, session_cookie)
        parts.append(f"{get_profile_cookie_name()}={signed}")
    return "; ".join(parts)


def _run_check_auth(auth, handler) -> bool:
    """Mirror server.py: request profile from the cookie, then check_auth."""
    from urllib.parse import urlparse

    from api.helpers import get_profile_cookie
    from api.profiles import clear_request_profile, set_request_profile

    cookie_profile = get_profile_cookie(handler)
    if cookie_profile:
        set_request_profile(cookie_profile)
    try:
        return auth.check_auth(handler, urlparse("/api/profile/switch"))
    finally:
        clear_request_profile()


def test_bound_session_with_signed_profile_cookie_is_accepted(auth_env):
    session = auth_env.create_session(
        auth_type="cross_profile_delegation",
        username="delegate_to_profile:frontend",
        bound_profile="frontend",
        ttl_seconds=3600,
    )
    handler = _FakeHandler(_cookie_header(auth_env, session, "frontend"))

    assert _run_check_auth(auth_env, handler) is True
    assert handler.status is None


def test_bound_session_without_the_profile_cookie_is_refused(auth_env, monkeypatch):
    """The failure mode the pre-signed cookie exists to avoid."""
    import api.profiles as profiles

    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "default")
    session = auth_env.create_session(bound_profile="frontend", ttl_seconds=3600)
    handler = _FakeHandler(_cookie_header(auth_env, session, None))

    assert _run_check_auth(auth_env, handler) is False
    assert handler.status == 403


def test_bound_session_cannot_reach_another_profile(auth_env):
    """Credential scope: the mint is useless for any profile but the target."""
    session = auth_env.create_session(bound_profile="frontend", ttl_seconds=3600)
    handler = _FakeHandler(_cookie_header(auth_env, session, "docs-gits"))

    assert _run_check_auth(auth_env, handler) is False
    assert handler.status == 403


def test_profile_cookie_must_be_signed_for_this_session(auth_env):
    """A forged plain profile cookie does not authorize the bound session."""
    from api.helpers import get_profile_cookie_name

    session = auth_env.create_session(bound_profile="frontend", ttl_seconds=3600)
    handler = _FakeHandler(
        f"{auth_env._resolve_cookie_name()}={session}; "
        f"{get_profile_cookie_name()}=frontend"
    )

    assert _run_check_auth(auth_env, handler) is False
    assert handler.status == 403


def test_profile_cookie_signed_for_a_different_session_is_rejected(auth_env):
    other = auth_env.create_session(bound_profile="frontend", ttl_seconds=3600)
    session = auth_env.create_session(bound_profile="frontend", ttl_seconds=3600)
    from api.helpers import get_profile_cookie_name

    handler = _FakeHandler(
        f"{auth_env._resolve_cookie_name()}={session}; "
        f"{get_profile_cookie_name()}="
        f"{auth_env.sign_profile_cookie_value('frontend', other)}"
    )

    assert _run_check_auth(auth_env, handler) is False
    assert handler.status == 403


def test_revoked_delegation_session_stops_working(auth_env):
    session = auth_env.create_session(bound_profile="frontend", ttl_seconds=3600)
    header = _cookie_header(auth_env, session, "frontend")
    assert _run_check_auth(auth_env, _FakeHandler(header)) is True

    auth_env.invalidate_session(session)

    handler = _FakeHandler(header)
    assert _run_check_auth(auth_env, handler) is False
    assert handler.status == 401
