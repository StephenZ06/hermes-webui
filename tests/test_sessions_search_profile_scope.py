"""Session search stays profile-scoped for chats filed under a project.

An unfoldered ("General") chat is the deliberate exception — see
tests/test_general_chat_visible_across_profiles.py — so every row here that
must stay hidden across profiles carries a project_id. Rows with no
project_id are General chats and are expected to surface regardless of the
active profile.
"""
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse


def _run_search(query):
    import api.routes as routes
    sessions_meta = [
        {"session_id": "active-s", "title": "boring", "profile": "default"},
        {"session_id": "other-s", "title": "secret needle title", "profile": "other", "project_id": "p1"},
        {"session_id": "other-content-s", "title": "boring", "profile": "other", "project_id": "p1"},
        {"session_id": "other-general-s", "title": "unfiled needle chat", "profile": "other"},
    ]
    sessions = {
        "other-content-s": SimpleNamespace(messages=[{"role": "user", "content": "secret needle body"}]),
        "active-s": SimpleNamespace(messages=[{"role": "user", "content": "nothing"}]),
        "other-s": SimpleNamespace(messages=[]),
        "other-general-s": SimpleNamespace(messages=[]),
    }
    captured = {}
    def fake_j(handler, payload, status=200, extra_headers=None):
        captured["status"] = status
        captured["payload"] = payload
    with patch("api.routes.all_sessions", return_value=list(sessions_meta)), \
         patch("api.routes.get_session", side_effect=lambda sid: sessions[sid]), \
         patch("api.profiles.get_active_profile_name", return_value="default"), \
         patch("api.routes.j", side_effect=fake_j):
        routes._handle_sessions_search(SimpleNamespace(), urlparse(query))
    return captured


def test_empty_session_search_scopes_foldered_chats_to_active_profile():
    captured = _run_search("/api/sessions/search")
    ids = {s["session_id"] for s in captured["payload"]["sessions"]}
    assert ids == {"active-s", "other-general-s"}, (
        "a foldered chat from another profile must stay hidden; an unfoldered "
        "(General) chat from another profile must still be listed"
    )


def test_title_search_should_not_return_other_profiles_foldered_rows():
    captured = _run_search("/api/sessions/search?q=needle&content=0")
    ids = {s["session_id"] for s in captured["payload"]["sessions"]}
    assert ids == {"other-general-s"}, (
        "the foldered other-profile title match must be excluded; the "
        "unfoldered other-profile title match must still be found"
    )


def test_content_search_should_not_return_other_profiles_foldered_rows():
    captured = _run_search("/api/sessions/search?q=needle&content=1&depth=0")
    ids = {s["session_id"] for s in captured["payload"]["sessions"]}
    assert "other-content-s" not in ids, "the foldered other-profile content match must be excluded"


def test_all_profiles_opt_in_keeps_aggregate_session_search():
    captured = _run_search("/api/sessions/search?all_profiles=1")
    assert captured["payload"]["all_profiles"] is True
    assert {s["session_id"] for s in captured["payload"]["sessions"]} == {
        "active-s",
        "other-s",
        "other-content-s",
        "other-general-s",
    }
