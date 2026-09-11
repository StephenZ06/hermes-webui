"""An unfoldered ("General" in the new-chat destination picker) chat is not
profile-scoped: it appears in the sidebar and in session search no matter
which profile is active. A chat filed under a project stays profile-scoped
(project folders are a per-profile organizing concept, #1614) — only the
project-less "General" list is exempt.

Reported: a user's loose, unfiled chats from profile B disappeared from the
sidebar while on profile A, even though nothing about a General chat is
profile-specific the way a project folder is.
"""
import api.routes as routes


def _session(sid, profile, project_id=None, **extra):
    row = {
        "session_id": sid,
        "profile": profile,
        "project_id": project_id,
        "title": sid,
        "message_count": 1,
        "last_message_at": 100.0,
        "updated_at": 100.0,
    }
    row.update(extra)
    return row


def _fake_all_sessions_factory(rows):
    def _fake(*args, **kwargs):
        return list(rows)
    return _fake


def test_unfoldered_session_from_another_profile_is_listed(monkeypatch):
    rows = [
        _session("general-default", "default"),
        _session("general-other", "coding-opencode"),
        _session("foldered-other", "coding-opencode", project_id="p1"),
    ]
    monkeypatch.setattr(routes, "all_sessions", _fake_all_sessions_factory(rows))
    monkeypatch.setattr(routes, "_is_isolated_profile_mode", lambda: False)

    payload = routes._build_session_list_cache_payload(
        active_profile="default",
        all_profiles=False,
        show_cli_sessions=False,
        show_previous_messaging_sessions=False,
        show_cron_sessions=False,
    )
    ids = {s["session_id"] for s in payload["sessions"]}

    assert "general-default" in ids
    assert "general-other" in ids, "an unfoldered chat must not be hidden by profile scoping"
    assert "foldered-other" not in ids, "a chat filed under a project stays profile-scoped"


def test_other_profile_count_reflects_only_foldered_hides(monkeypatch):
    rows = [
        _session("general-default", "default"),
        _session("general-other", "coding-opencode"),
        _session("foldered-other", "coding-opencode", project_id="p1"),
    ]
    monkeypatch.setattr(routes, "all_sessions", _fake_all_sessions_factory(rows))
    monkeypatch.setattr(routes, "_is_isolated_profile_mode", lambda: False)

    payload = routes._build_session_list_cache_payload(
        active_profile="default",
        all_profiles=False,
        show_cli_sessions=False,
        show_previous_messaging_sessions=False,
        show_cron_sessions=False,
    )
    # Only the foldered other-profile row is actually hidden; the unfoldered
    # other-profile row is visible and must not inflate the "N from other
    # profiles" count the UI would otherwise offer to reveal.
    assert payload["other_profile_count"] == 1


def test_all_profiles_flag_is_unaffected():
    # Sanity: ?all_profiles=1 already returned everything; the General
    # exception must not change that path.
    rows = [
        _session("a", "default"),
        _session("b", "coding-opencode", project_id="p1"),
    ]
    import api.routes as r

    orig = r.all_sessions
    r.all_sessions = _fake_all_sessions_factory(rows)
    try:
        payload = r._build_session_list_cache_payload(
            active_profile="default",
            all_profiles=True,
            show_cli_sessions=False,
            show_previous_messaging_sessions=False,
            show_cron_sessions=False,
        )
    finally:
        r.all_sessions = orig
    ids = {s["session_id"] for s in payload["sessions"]}
    assert ids == {"a", "b"}
    assert payload["other_profile_count"] == 0


def test_search_endpoint_lists_an_unfoldered_session_from_another_profile(monkeypatch):
    from unittest.mock import MagicMock
    from urllib.parse import urlparse
    import api.profiles as profiles_api

    rows = [
        _session("general-other", "coding-opencode"),
        _session("foldered-other", "coding-opencode", project_id="p1"),
    ]
    monkeypatch.setattr(routes, "all_sessions", lambda *a, **k: list(rows))
    monkeypatch.setattr(profiles_api, "get_active_profile_name", lambda: "default")
    monkeypatch.setattr(routes, "_all_profiles_enabled", lambda parsed: False)
    monkeypatch.setattr(routes, "load_settings", lambda: {"api_redact_enabled": False})

    sent = {}
    monkeypatch.setattr(routes, "j", lambda h, body, **kw: sent.setdefault("body", body))

    # An empty query hits the "list everything visible" branch — no content
    # scan needed to prove the profile-scope filter's shape.
    parsed = urlparse("/api/sessions/search?q=&content=0")
    routes._handle_sessions_search(MagicMock(), parsed)

    ids = {s["session_id"] for s in sent["body"]["sessions"]}
    assert "general-other" in ids, "search must not hide an unfoldered session from another profile"
    assert "foldered-other" not in ids, "a foldered session from another profile stays hidden"
