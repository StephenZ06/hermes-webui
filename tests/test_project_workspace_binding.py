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
