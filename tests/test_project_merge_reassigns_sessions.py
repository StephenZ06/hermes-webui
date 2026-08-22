"""Regression test for /api/projects/merge and its shared reassignment helper.

Before this, several profiles could each independently create their own
project row for the same real-world project (e.g. "Triple S POS") back when
project visibility was still profile-scoped -- once folders became globally
visible (see test_project_folders_visible_across_profiles.py), that left
multiple duplicate folders showing for what the user considers ONE project.

`_reassign_project_sessions` (factored out of the old /api/projects/delete
inline loop) is the shared primitive: given a set of old project_ids and a
new one (or None), it repoints every matching session. `/api/projects/merge`
uses it to fold several source project rows into one target, deleting the
source rows and reassigning their sessions in one call.
"""
import json

from api import routes


def _write_index(tmp_path, entries):
    index_file = tmp_path / "_index.json"
    index_file.write_text(json.dumps(entries), encoding="utf-8")
    return index_file


class _FakeSession:
    def __init__(self, session_id, project_id):
        self.session_id = session_id
        self.project_id = project_id
        self.saved_project_id = None

    def save(self):
        self.saved_project_id = self.project_id


def test_reassign_project_sessions_updates_non_streaming_sessions(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "s1", "project_id": "old-a", "active_stream_id": None},
        {"session_id": "s2", "project_id": "old-b", "active_stream_id": None},
        {"session_id": "s3", "project_id": "unrelated", "active_stream_id": None},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: set())

    fake_sessions = {"s1": _FakeSession("s1", "old-a"), "s2": _FakeSession("s2", "old-b")}
    monkeypatch.setattr(routes, "get_session", lambda sid: fake_sessions[sid])

    updated = routes._reassign_project_sessions({"old-a", "old-b"}, "canonical")

    assert updated == 2
    assert fake_sessions["s1"].saved_project_id == "canonical"
    assert fake_sessions["s2"].saved_project_id == "canonical"


def test_reassign_project_sessions_updates_streaming_session_in_cache(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "live1", "project_id": "old-a", "active_stream_id": "stream-1"},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: {"stream-1"})

    cached = _FakeSession("live1", "old-a")
    monkeypatch.setattr(routes, "SESSIONS", {"live1": cached})

    def _boom(sid):
        raise AssertionError("must not call get_session for a live-cached streaming session")
    monkeypatch.setattr(routes, "get_session", _boom)

    updated = routes._reassign_project_sessions({"old-a"}, "canonical")

    assert updated == 1
    assert cached.project_id == "canonical"
    # Streaming session: the worker's own next save persists it -- we must
    # NOT have called .save() ourselves (that would race the writer).
    assert cached.saved_project_id is None


def test_reassign_project_sessions_handles_none_target_like_delete(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "s1", "project_id": "doomed", "active_stream_id": None},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: set())
    fake = _FakeSession("s1", "doomed")
    monkeypatch.setattr(routes, "get_session", lambda sid: fake)

    updated = routes._reassign_project_sessions({"doomed"}, None)

    assert updated == 1
    assert fake.saved_project_id is None


def test_merge_scenario_reassigns_sessions_from_multiple_duplicate_projects(tmp_path, monkeypatch):
    """End-to-end shape of the real "Triple S POS" cleanup: two duplicate
    project rows (created independently on different profiles) each own a
    few sessions -- one of them mid-stream. A single
    `_reassign_project_sessions({src1, src2}, target)` call, as
    /api/projects/merge issues, must repoint all of them at once.
    """
    index_file = _write_index(tmp_path, [
        {"session_id": "default-chat-1", "project_id": "src1", "active_stream_id": None},
        {"session_id": "debugging-chat-1", "project_id": "src2", "active_stream_id": "stream-live"},
        {"session_id": "unrelated-chat", "project_id": "other", "active_stream_id": None},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: {"stream-live"})

    fake_get = _FakeSession("default-chat-1", "src1")
    monkeypatch.setattr(routes, "get_session", lambda sid: fake_get)
    live_cached = _FakeSession("debugging-chat-1", "src2")
    monkeypatch.setattr(routes, "SESSIONS", {"debugging-chat-1": live_cached})

    merged = routes._reassign_project_sessions({"src1", "src2"}, "target")

    assert merged == 2
    assert fake_get.saved_project_id == "target"
    assert live_cached.project_id == "target"
    assert live_cached.saved_project_id is None  # streaming: worker persists it, not us
