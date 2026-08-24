"""POST /api/chat must republish the cross-profile delegation depth header.

hermes-agent's ``delegate_to_profile`` tool drives a target profile's whole
turn through this endpoint. Because ``_handle_chat_sync`` holds the
process-global ``CHAT_LOCK`` for the entire turn, a nested delegation issued
from inside a child profile's turn would deadlock on that lock (observed live:
two delegation-edge records stuck at exactly 300-302s). The tool's own depth
counter cannot survive the HTTP hop — the child turn runs on a brand-new
``AIAgent`` instance — so the depth travels as the
``X-Hermes-Cross-Profile-Depth`` request header and this handler republishes it
as ``HERMES_CROSS_PROFILE_DEPTH`` for the duration of the turn, exactly
mirroring the existing ``TERMINAL_CWD`` threading.
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
            # Snapshot the env exactly as the delegated turn would observe it.
            seen["depth"] = os.environ.get("HERMES_CROSS_PROFILE_DEPTH")
            seen["cwd"] = os.environ.get("TERMINAL_CWD")
            return {"messages": [], "final_response": "ok", "completed": True}

    monkeypatch.setitem(sys.modules, "run_agent", SimpleNamespace(AIAgent=FakeAgent))

    handler = _FakePostHandler(request_headers)
    routes._handle_chat_sync(
        handler,
        {"session_id": session.session_id, "message": "hi", "workspace": str(tmp_path)},
    )
    return handler


def test_depth_header_is_published_to_the_turn_and_restored_after(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_CROSS_PROFILE_DEPTH", raising=False)
    seen = {}
    handler = _run_chat_sync(
        tmp_path, monkeypatch, {"X-Hermes-Cross-Profile-Depth": "1"}, seen
    )

    assert handler.status == 200
    assert seen["depth"] == "1"
    assert seen["cwd"] == str(tmp_path)
    # Must not leak into unrelated later requests on this shared process.
    assert os.environ.get("HERMES_CROSS_PROFILE_DEPTH") is None


def test_absent_depth_header_leaves_the_env_var_unset(tmp_path, monkeypatch):
    """A top-level (non-delegated) chat request must leave the var unset, so
    delegate_to_profile's os.environ.get(...) correctly reads None and falls
    back to its per-agent-instance counter — same contract as TERMINAL_CWD."""
    monkeypatch.delenv("HERMES_CROSS_PROFILE_DEPTH", raising=False)
    seen = {}
    handler = _run_chat_sync(tmp_path, monkeypatch, {}, seen)

    assert handler.status == 200
    assert seen["depth"] is None
    assert os.environ.get("HERMES_CROSS_PROFILE_DEPTH") is None


def test_prior_depth_value_is_restored_not_clobbered(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_CROSS_PROFILE_DEPTH", "7")
    seen = {}
    handler = _run_chat_sync(
        tmp_path, monkeypatch, {"X-Hermes-Cross-Profile-Depth": "1"}, seen
    )

    assert handler.status == 200
    assert seen["depth"] == "1"
    assert os.environ.get("HERMES_CROSS_PROFILE_DEPTH") == "7"
