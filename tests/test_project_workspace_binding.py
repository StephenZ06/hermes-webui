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
