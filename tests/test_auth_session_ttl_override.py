"""``create_session(ttl_seconds=...)`` mints a short-lived credential.

Cross-profile delegation runs inside the WebUI process and drives the target
profile's turn over authenticated loopback HTTP, so it has to mint a session
for itself. The default 30-day TTL is wrong for that: the credential is
persisted to ``.sessions.json``, so a crash between mint and revoke would
strand a month-long session on disk. Bounding the TTL at mint time caps the
blast radius even when the ``finally`` that revokes it never runs.

The TTL is an argument to the existing ``create_session`` rather than a second
minting function, so both callers share one signing/persistence path.
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture
def auth(tmp_path, monkeypatch):
    import api.auth as auth_mod

    monkeypatch.setattr(auth_mod, 'STATE_DIR', tmp_path)
    monkeypatch.setattr(auth_mod, '_SESSIONS_FILE', tmp_path / '.sessions.json')
    monkeypatch.setattr(auth_mod, '_sessions', {})
    return auth_mod


def _token(cookie_value: str) -> str:
    return cookie_value.rsplit('.', 1)[0]


def test_ttl_override_bounds_the_stored_expiry(auth):
    before = time.time()
    cookie = auth.create_session(ttl_seconds=300)
    after = time.time()

    record = auth._sessions[_token(cookie)]
    expiry = auth._session_expiry(record)

    assert before + 300 <= expiry <= after + 300
    assert auth.verify_session(cookie) is True


def test_ttl_override_is_far_shorter_than_the_default(auth):
    short = auth._session_expiry(auth._sessions[_token(auth.create_session(ttl_seconds=300))])
    default = auth._session_expiry(auth._sessions[_token(auth.create_session())])

    assert default - short > 86400


def test_expired_short_session_stops_verifying(auth, monkeypatch):
    cookie = auth.create_session(ttl_seconds=300)
    assert auth.verify_session(cookie) is True

    real_time = time.time
    monkeypatch.setattr(auth.time, 'time', lambda: real_time() + 301)

    assert auth.verify_session(cookie) is False
    assert _token(cookie) not in auth._sessions


def test_ttl_override_keeps_identity_fields(auth):
    cookie = auth.create_session(
        auth_type='delegation',
        username='delegate_to_profile',
        bound_profile='frontend',
        ttl_seconds=300,
    )

    info = auth.get_session_info(cookie)

    assert info['auth_type'] == 'delegation'
    assert info['username'] == 'delegate_to_profile'
    assert info['bound_profile'] == 'frontend'
    assert auth.session_bound_profile(cookie) == 'frontend'


@pytest.mark.parametrize('bad', [0, -1, None])
def test_non_positive_ttl_falls_back_to_the_default(auth, bad):
    cookie = auth.create_session(ttl_seconds=bad)
    expiry = auth._session_expiry(auth._sessions[_token(cookie)])

    assert expiry - time.time() > 86400
