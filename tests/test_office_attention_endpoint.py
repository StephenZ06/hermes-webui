"""GET /api/office/attention: every WebUI chat waiting on the user, any profile.

The Office dashboard used to poll /api/approval/pending and /api/clarify/pending
once per delegating chat of the *active* profile only, so a chat on another
profile never reached the Attention card, and chats tagged with another
profile 404'd on every poll. This endpoint lists all of them in one call,
marks which belong to the active profile, and leaves out chats the WebUI does
not own.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import api.clarify as clarify
import api.routes as routes


def _call(sessions, active="alpha"):
    def fake_get_session(sid, metadata_only=False):
        if sid not in sessions:
            raise KeyError(sid)
        return SimpleNamespace(profile=sessions[sid][0], title=sessions[sid][1])

    with patch.object(routes, "get_session", side_effect=fake_get_session), \
         patch.object(routes, "_get_active_profile_name", return_value=active), \
         patch.object(routes, "j", side_effect=lambda handler, payload, **kw: payload):
        return routes._handle_office_attention(MagicMock(), urlparse("http://x/api/office/attention"))


def test_lists_waiting_chats_from_every_profile_and_skips_unknown_ones():
    here, there, cli = "aaaaaaaaaaa1", "bbbbbbbbbbb2", "ccccccccccc3"
    routes.submit_pending(here, {"command": "rm -rf /tmp/x", "pattern_key": "k", "pattern_keys": ["k"], "description": "d"})
    clarify.submit_pending(there, {"question": "Which file?", "choices_offered": ["a", "b"], "session_id": there})
    clarify.submit_pending(cli, {"question": "CLI only?", "session_id": cli})
    try:
        out = _call({here: ("alpha", "Here chat"), there: ("beta", "There chat")})
    finally:
        with routes._lock:
            routes._pending.pop(here, None)
        clarify.clear_pending(there)
        clarify.clear_pending(cli)
    by_id = {item["session_id"]: item for item in out["items"]}
    assert set(by_id) == {here, there}, "a chat with no WebUI session is left out"
    assert by_id[here]["kind"] == "approval" and by_id[here]["same_profile"] is True
    assert by_id[here]["pending"]["command"] == "rm -rf /tmp/x"
    assert by_id[there]["kind"] == "clarify" and by_id[there]["same_profile"] is False
    assert by_id[there]["profile"] == "beta" and by_id[there]["pending"]["question"] == "Which file?"


def test_nothing_waiting_is_an_empty_list():
    assert _call({}) == {"items": []}
