"""POST /api/chat must republish the cross-profile delegation depth header.

hermes-agent's ``delegate_to_profile`` tool drives a target profile's whole
turn through this endpoint. Because ``_handle_chat_sync`` holds the
process-global ``CHAT_LOCK`` for the entire turn, a nested delegation issued
from inside a child profile's turn would deadlock on that lock (observed live:
two delegation-edge records stuck at exactly 300-302s). The tool's own depth
counter cannot survive the HTTP hop — the child turn runs on a brand-new
``AIAgent`` instance — so the depth travels as the
``X-Hermes-Cross-Profile-Depth`` request header and this handler republishes it
against the session for the duration of the turn, via
``api.cross_profile_depth``.

It is deliberately NOT republished into ``os.environ``. That was the original
implementation and it cross-talks: a delegated child turn holds its depth for
its entire duration, so any turn running concurrently in the same process read
that depth and refused its own first hop. See
``tests/test_cross_profile_depth_isolation.py`` for the isolation contract.
"""
import json
import os
import sys
from types import SimpleNamespace

from api.models import Session


class _FakePostHandler:
    def __init__(self, request_headers=None):
        self.status = None
        self.headers = dict(request_headers or {})
        self.body = bytearray()
        self.wfile = self

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)


def _run_chat_sync(tmp_path, monkeypatch, request_headers, seen):
    import api.config as config
    import api.models as models
    import api.routes as routes

    state_dir = tmp_path / "state"
    session_dir = state_dir / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", state_dir / "session_index.json")
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", state_dir / "session_index.json")
    monkeypatch.setattr(routes, "get_session", models.get_session)
    monkeypatch.setattr(routes, "title_from", models.title_from)
    monkeypatch.setattr(config, "get_config", lambda: {"model": "test-model", "provider": "test-provider"})
    monkeypatch.setattr(routes, "get_config", lambda: {"model": "test-model", "provider": "test-provider"})
    monkeypatch.setattr(routes, "resolve_trusted_workspace", lambda value: tmp_path)
    monkeypatch.setattr(routes, "load_settings", lambda: {})
    monkeypatch.setattr(routes, "_resolve_cli_toolsets", lambda: [])

    session = Session(
        session_id="xprofile_depth_hdr",
        workspace=str(tmp_path),
        messages=[],
        context_messages=[],
        model="test-model",
        model_provider="test-provider",
    )
    session.save(touch_updated_at=False)

    class FakeAgent:
        def __init__(self, **_kwargs):
            pass

        def run_conversation(self, **_kwargs):
            # Snapshot state exactly as the delegated turn's tool would read it:
            # the tool receives session_id from the registry and looks the depth
            # up by it.
            from api import cross_profile_depth

            seen["depth"] = cross_profile_depth.get_depth("xprofile_depth_hdr")
            seen["other_session_depth"] = cross_profile_depth.get_depth("unrelated")
            seen["env"] = os.environ.get("HERMES_CROSS_PROFILE_DEPTH")
            seen["cwd"] = os.environ.get("TERMINAL_CWD")
            return {"messages": [], "final_response": "ok", "completed": True}

    monkeypatch.setitem(sys.modules, "run_agent", SimpleNamespace(AIAgent=FakeAgent))

    handler = _FakePostHandler(request_headers)
    routes._handle_chat_sync(
        handler,
        {"session_id": session.session_id, "message": "hi", "workspace": str(tmp_path)},
    )
    return handler


def test_depth_header_is_published_to_the_turn_and_cleared_after(tmp_path, monkeypatch):
    from api import cross_profile_depth

    monkeypatch.delenv("HERMES_CROSS_PROFILE_DEPTH", raising=False)
    seen = {}
    handler = _run_chat_sync(
        tmp_path, monkeypatch, {"X-Hermes-Cross-Profile-Depth": "1"}, seen
    )

    assert handler.status == 200
    assert seen["depth"] == 1
    assert seen["cwd"] == str(tmp_path)
    # Scoped to this turn's session: a concurrent turn must read 0, not 1.
    assert seen["other_session_depth"] == 0
    # The process environment is not the transport any more.
    assert seen["env"] is None
    assert os.environ.get("HERMES_CROSS_PROFILE_DEPTH") is None
    # Must not leak into a later turn on this session.
    assert cross_profile_depth.get_depth("xprofile_depth_hdr") == 0


def test_absent_depth_header_records_nothing(tmp_path, monkeypatch):
    """A top-level (non-delegated) chat request records no depth at all, so
    delegate_to_profile reads 0 and correctly treats the turn as a first hop."""
    monkeypatch.delenv("HERMES_CROSS_PROFILE_DEPTH", raising=False)
    seen = {}
    handler = _run_chat_sync(tmp_path, monkeypatch, {}, seen)

    assert handler.status == 200
    assert seen["depth"] == 0
    assert seen["env"] is None
    assert os.environ.get("HERMES_CROSS_PROFILE_DEPTH") is None


def test_a_stale_env_var_no_longer_influences_a_turn(tmp_path, monkeypatch):
    """The old transport must not be able to poison a turn any more.

    A leftover ``HERMES_CROSS_PROFILE_DEPTH`` in the process environment -- from
    an older build, a wrapper script, or a shell -- used to be read as this
    turn's depth. It is now inert, and the handler neither reads nor rewrites
    it.
    """
    monkeypatch.setenv("HERMES_CROSS_PROFILE_DEPTH", "7")
    seen = {}
    handler = _run_chat_sync(
        tmp_path, monkeypatch, {"X-Hermes-Cross-Profile-Depth": "1"}, seen
    )

    assert handler.status == 200
    assert seen["depth"] == 1
    # Left exactly as found: not consumed, not rewritten.
    assert os.environ.get("HERMES_CROSS_PROFILE_DEPTH") == "7"
