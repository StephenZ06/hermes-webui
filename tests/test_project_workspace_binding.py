"""Regression coverage for binding a workspace path to a sidebar Project.

Mirrors tests/test_project_merge_reassigns_sessions.py's fake-session /
monkeypatch shape: `_apply_project_workspace` reuses the same
active-stream-safe update pattern as `_reassign_project_sessions`, just
setting `.workspace` instead of `.project_id`.
"""
import json

from api import routes


def _write_index(tmp_path, entries):
    index_file = tmp_path / "_index.json"
    index_file.write_text(json.dumps(entries), encoding="utf-8")
    return index_file


class _FakeSession:
    def __init__(self, session_id, project_id, workspace="/old/path"):
        self.session_id = session_id
        self.project_id = project_id
        self.workspace = workspace
        self.saved_workspace = None

    def save(self):
        self.saved_workspace = self.workspace


def test_apply_project_workspace_updates_non_streaming_sessions(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "s1", "project_id": "proj-a", "active_stream_id": None},
        {"session_id": "s2", "project_id": "proj-a", "active_stream_id": None},
        {"session_id": "s3", "project_id": "other", "active_stream_id": None},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: set())

    fake_sessions = {
        "s1": _FakeSession("s1", "proj-a"),
        "s2": _FakeSession("s2", "proj-a"),
    }
    monkeypatch.setattr(routes, "get_session", lambda sid: fake_sessions[sid])

    updated = routes._apply_project_workspace("proj-a", "/bound/path")

    assert updated == 2
    assert fake_sessions["s1"].saved_workspace == "/bound/path"
    assert fake_sessions["s2"].saved_workspace == "/bound/path"


def test_apply_project_workspace_updates_streaming_session_in_cache(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "live1", "project_id": "proj-a", "active_stream_id": "stream-1"},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: {"stream-1"})

    cached = _FakeSession("live1", "proj-a")
    monkeypatch.setattr(routes, "SESSIONS", {"live1": cached})

    def _boom(sid):
        raise AssertionError("must not call get_session for a live-cached streaming session")
    monkeypatch.setattr(routes, "get_session", _boom)

    updated = routes._apply_project_workspace("proj-a", "/bound/path")

    assert updated == 1
    assert cached.workspace == "/bound/path"
    # Streaming session: the worker's own next save persists it -- we must
    # NOT have called .save() ourselves (that would race the writer).
    assert cached.saved_workspace is None


def test_apply_project_workspace_ignores_other_projects(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "s1", "project_id": "proj-a", "active_stream_id": None},
        {"session_id": "s2", "project_id": "proj-b", "active_stream_id": None},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: set())
    fake_sessions = {"s1": _FakeSession("s1", "proj-a")}
    monkeypatch.setattr(routes, "get_session", lambda sid: fake_sessions[sid])

    updated = routes._apply_project_workspace("proj-a", "/bound/path")

    assert updated == 1


def test_bound_project_workspace_returns_none_when_unbound():
    assert routes._bound_project_workspace(
        "proj-a", load_projects=lambda: [{"project_id": "proj-a", "name": "A"}]
    ) is None


def test_bound_project_workspace_returns_path_when_set():
    assert routes._bound_project_workspace(
        "proj-a",
        load_projects=lambda: [{"project_id": "proj-a", "name": "A", "workspace_path": "/bound/path"}],
    ) == "/bound/path"


def test_apply_session_move_project_workspace_sets_workspace_from_bound_project():
    """Moving a session into a Project that has a bound workspace_path
    should set that session's workspace immediately (single-session path,
    distinct from the bulk _apply_project_workspace helper used at bind
    time)."""

    class _MoveFakeSession:
        def __init__(self):
            self.project_id = None
            self.workspace = "/original/workspace"

    fake = _MoveFakeSession()
    body = {"session_id": "s1", "project_id": "proj-bound"}
    load_projects = lambda: [
        {"project_id": "proj-bound", "name": "Bound", "workspace_path": "/bound/path"}
    ]

    result = routes._apply_session_move_project_workspace(fake, body, load_projects=load_projects)

    assert result is fake
    assert fake.project_id == "proj-bound"
    assert fake.workspace == "/bound/path"


def test_apply_session_move_project_workspace_leaves_workspace_when_unbound():
    class _MoveFakeSession:
        def __init__(self):
            self.project_id = None
            self.workspace = "/original/workspace"

    fake = _MoveFakeSession()
    body = {"session_id": "s1", "project_id": "proj-plain"}
    load_projects = lambda: [{"project_id": "proj-plain", "name": "Plain"}]

    routes._apply_session_move_project_workspace(fake, body, load_projects=load_projects)

    assert fake.project_id == "proj-plain"
    assert fake.workspace == "/original/workspace"


def test_apply_session_move_project_workspace_unassign_clears_project_id():
    class _MoveFakeSession:
        def __init__(self):
            self.project_id = "old-proj"
            self.workspace = "/original/workspace"

    fake = _MoveFakeSession()
    body = {"session_id": "s1", "project_id": None}
    load_projects = lambda: []

    routes._apply_session_move_project_workspace(fake, body, load_projects=load_projects)

    assert fake.project_id is None
    assert fake.workspace == "/original/workspace"


# ── A bound project must actually reach the new conversation ────────────────
#
# The binding saved fine and /api/session/new had a fallback for it, but the
# fallback only fired when the request carried no workspace at all -- and the
# New Chat path always sends one (S._profileDefaultWorkspace is always set).
# So every new conversation in a bound project opened in the profile default
# instead, and the agent reported that as its working folder.

import pathlib

SESSIONS_JS = (pathlib.Path(__file__).parent.parent / "static" / "sessions.js").read_text(encoding="utf-8")


def _new_chat_request_builder():
    start = SESSIONS_JS.index("const inheritWs=switchWs")
    return SESSIONS_JS[start : SESSIONS_JS.index("const data=await api('/api/session/new'", start)]


def test_new_chat_sends_the_bound_project_workspace():
    body = _new_chat_request_builder()
    assert "_boundProj.workspace_path" in body
    assert "reqBody.workspace=_boundProj.workspace_path" in body


def test_bound_workspace_is_only_applied_when_a_project_is_attached():
    body = _new_chat_request_builder()
    assert "if(!switchWs&&reqBody.project_id)" in body


def test_an_explicit_profile_switch_workspace_still_wins():
    # switchWs is a deliberate "open this workspace" action, not an inherited
    # default, so a project binding must not override it.
    body = _new_chat_request_builder()
    guard = body[body.index("if(!switchWs&&reqBody.project_id)") :]
    assert "switchWs" in guard.split("\n")[0]


def test_server_fallback_still_covers_a_request_with_no_workspace():
    # The client-side precedence is the fix; the server fallback stays as the
    # safety net for any caller that omits workspace entirely.
    routes_src = (pathlib.Path(__file__).parent.parent / "api" / "routes.py").read_text(encoding="utf-8")
    assert 'if not workspace and body.get("project_id"):' in routes_src
    assert "_bound_project_workspace" in routes_src


# ── Unbinding must not break the chats already in the Project ───────────────
#
# POST /api/projects/set_workspace with a null workspace_path used to push
# that null down onto every session in the project. Session.__init__ resolves
# the workspace with Path(), so Path(None) raised and those chats returned 500
# on every route that loaded them -- unreachable from the UI, with the only
# clue being a TypeError in the container log.

def test_clearing_a_binding_does_not_touch_session_workspaces(monkeypatch, tmp_path):
    index = tmp_path / "_index.json"
    index.write_text(json.dumps([{"session_id": "s1", "project_id": "p1"}]), encoding="utf-8")
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index)

    touched = []
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: set())
    monkeypatch.setattr(routes, "get_session", lambda sid: touched.append(sid))

    for empty in (None, "", 0):
        assert routes._apply_project_workspace("p1", empty) == 0
    assert touched == [], "no session may be loaded, let alone rewritten, on unbind"


def test_binding_a_real_path_still_updates_sessions(monkeypatch, tmp_path):
    index = tmp_path / "_index.json"
    index.write_text(json.dumps([{"session_id": "s1", "project_id": "p1"}]), encoding="utf-8")
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: set())

    class _S:
        workspace = None
        def save(self):
            pass

    session = _S()
    monkeypatch.setattr(routes, "get_session", lambda sid: session)
    assert routes._apply_project_workspace("p1", "/workspace/bound") == 1
    assert session.workspace == "/workspace/bound"


class TestSessionSurvivesANullWorkspace:
    """A session must always be constructible, whatever is on disk."""

    def test_none_workspace_falls_back_to_the_default(self):
        from api.config import DEFAULT_WORKSPACE
        from api.models import Session

        assert Session(session_id="t", workspace=None).workspace == str(
            pathlib.Path(DEFAULT_WORKSPACE).expanduser().resolve()
        )

    def test_blank_workspace_falls_back_to_the_default(self):
        from api.config import DEFAULT_WORKSPACE
        from api.models import Session

        assert Session(session_id="t", workspace="").workspace == str(
            pathlib.Path(DEFAULT_WORKSPACE).expanduser().resolve()
        )

    def test_a_real_workspace_is_still_honoured(self, tmp_path):
        from api.models import Session

        assert Session(session_id="t", workspace=str(tmp_path)).workspace == str(
            tmp_path.resolve()
        )
