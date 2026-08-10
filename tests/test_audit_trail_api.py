"""Audit Trail aggregation (Priority 3) + route wiring.

Read-only reduction over the existing turn/run journals -- no new storage.
See docs/HERMES_STUDIO_PARITY_PLAN.md, "Priority 3 -- Audit Trail UI".

Fixture pattern mirrors tests/test_turn_journal.py: build turn-journal
shards directly via append_turn_journal_event(session_dir=tmp_path) rather
than spinning up the live test HTTP server, since api.audit_trail's
functions are pure reductions over a session_dir.
"""
from pathlib import Path

from api.audit_trail import read_recent_audit_trail, read_session_audit_trail
from api.run_journal import append_run_event
from api.turn_journal import append_turn_journal_event

ROOT = Path(__file__).resolve().parent.parent


def _submit(session_dir, sid, turn_id, stream_id, content, *, created_at, model="claude-opus-5", model_provider="anthropic"):
    return append_turn_journal_event(
        sid,
        {
            "event": "submitted",
            "turn_id": turn_id,
            "stream_id": stream_id,
            "role": "user",
            "content": content,
            "model": model,
            "model_provider": model_provider,
            "created_at": created_at,
        },
        session_dir=session_dir,
    )


def _terminate(session_dir, sid, turn_id, stream_id, event_name, *, created_at):
    return append_turn_journal_event(
        sid,
        {
            "event": event_name,
            "turn_id": turn_id,
            "stream_id": stream_id,
            "created_at": created_at,
        },
        session_dir=session_dir,
    )


def test_single_turn_with_no_terminal_event_reads_as_running(tmp_path):
    _submit(tmp_path, "sid-1", "turn-1", "stream-1", "hello there", created_at=100.0)

    entries = read_session_audit_trail("sid-1", session_dir=tmp_path)

    assert len(entries) == 1
    assert entries[0]["status"] == "running"
    assert entries[0]["ended_at"] is None
    assert entries[0]["content_preview"] == "hello there"
    assert entries[0]["model"] == "claude-opus-5"


def test_completed_turn_keeps_submission_detail_and_gains_ended_at(tmp_path):
    _submit(tmp_path, "sid-1", "turn-1", "stream-1", "refactor the thing", created_at=100.0)
    _terminate(tmp_path, "sid-1", "turn-1", "stream-1", "completed", created_at=142.5)

    entries = read_session_audit_trail("sid-1", session_dir=tmp_path)

    assert len(entries) == 1
    entry = entries[0]
    # The completed event carries no content/model -- a plain latest-event
    # reduction would lose these. Proves _group_turn_events keeps `submitted`
    # separate from `terminal` instead of overwriting it.
    assert entry["content_preview"] == "refactor the thing"
    assert entry["model"] == "claude-opus-5"
    assert entry["status"] == "completed"
    assert entry["ended_at"] == 142.5
    assert entry["submitted_at"] == 100.0


def test_interrupted_terminal_state_surfaces_as_status(tmp_path):
    _submit(tmp_path, "sid-1", "turn-1", "stream-1", "long task", created_at=100.0)
    _terminate(tmp_path, "sid-1", "turn-1", "stream-1", "interrupted", created_at=110.0)

    entries = read_session_audit_trail("sid-1", session_dir=tmp_path)

    assert entries[0]["status"] == "interrupted"


def test_content_preview_truncated_at_200_chars_with_ellipsis(tmp_path):
    long_content = "x" * 500
    _submit(tmp_path, "sid-1", "turn-1", "stream-1", long_content, created_at=100.0)

    entries = read_session_audit_trail("sid-1", session_dir=tmp_path)

    preview = entries[0]["content_preview"]
    assert len(preview) == 203  # 200 chars + "..."
    assert preview.endswith("...")


def test_session_view_sorted_newest_first(tmp_path):
    _submit(tmp_path, "sid-1", "turn-1", "stream-1", "first", created_at=100.0)
    _submit(tmp_path, "sid-1", "turn-2", "stream-2", "second", created_at=200.0)
    _submit(tmp_path, "sid-1", "turn-3", "stream-3", "third", created_at=150.0)

    entries = read_session_audit_trail("sid-1", session_dir=tmp_path)

    assert [e["turn_id"] for e in entries] == ["turn-2", "turn-3", "turn-1"]


def test_session_view_enriches_with_run_summary_when_run_journal_exists(tmp_path):
    _submit(tmp_path, "sid-1", "turn-1", "stream-1", "do the run", created_at=100.0)
    append_run_event("sid-1", "stream-1", "done", session_dir=tmp_path)

    entries = read_session_audit_trail("sid-1", session_dir=tmp_path)

    assert "run_summary" in entries[0]
    assert entries[0]["run_summary"]["run_id"] == "stream-1"


def test_session_view_omits_run_summary_when_no_run_journal(tmp_path):
    _submit(tmp_path, "sid-1", "turn-1", "stream-1", "no run journal for this one", created_at=100.0)

    entries = read_session_audit_trail("sid-1", session_dir=tmp_path)

    assert "run_summary" not in entries[0]


def test_cross_session_view_merges_and_sorts_across_sessions(tmp_path):
    _submit(tmp_path, "sid-a", "turn-a1", "stream-a1", "from session a", created_at=100.0)
    _submit(tmp_path, "sid-b", "turn-b1", "stream-b1", "from session b", created_at=300.0)
    _submit(tmp_path, "sid-a", "turn-a2", "stream-a2", "second from a", created_at=200.0)

    entries = read_recent_audit_trail(session_dir=tmp_path)

    assert [e["session_id"] for e in entries] == ["sid-b", "sid-a", "sid-a"]


def test_cross_session_view_never_includes_run_summary(tmp_path):
    """Scope decision: run_summary enrichment is single-session-view only,
    to bound the cross-session view's per-request cost."""
    _submit(tmp_path, "sid-1", "turn-1", "stream-1", "content", created_at=100.0)
    append_run_event("sid-1", "stream-1", "done", session_dir=tmp_path)

    entries = read_recent_audit_trail(session_dir=tmp_path)

    assert "run_summary" not in entries[0]


def test_cross_session_limit_is_clamped(tmp_path):
    for i in range(5):
        _submit(tmp_path, "sid-1", f"turn-{i}", f"stream-{i}", f"turn {i}", created_at=float(i))

    assert len(read_recent_audit_trail(session_dir=tmp_path, limit=2)) == 2
    # Way over the max is clamped, not passed through raw.
    assert len(read_recent_audit_trail(session_dir=tmp_path, limit=10_000)) == 5
    # Non-numeric input falls back to the default rather than raising.
    assert len(read_recent_audit_trail(session_dir=tmp_path, limit="not-a-number")) == 5


def test_events_without_a_turn_id_are_ignored(tmp_path):
    append_turn_journal_event(
        "sid-1",
        {"event": "submitted", "turn_id": "", "content": "no turn id"},
        session_dir=tmp_path,
    )
    entries = read_session_audit_trail("sid-1", session_dir=tmp_path)
    assert entries == []


def test_deleted_session_does_not_appear_in_cross_session_view(tmp_path):
    """Regression guard: the read side must not cache/resurrect entries for
    a session whose turn-journal shard has been removed (the delete path
    api/routes.py calls on session delete, #3802)."""
    from api.turn_journal import delete_turn_journal

    _submit(tmp_path, "sid-1", "turn-1", "stream-1", "will be deleted", created_at=100.0)
    assert len(read_recent_audit_trail(session_dir=tmp_path)) == 1

    delete_turn_journal("sid-1", session_dir=tmp_path)

    assert read_recent_audit_trail(session_dir=tmp_path) == []


def test_route_wired():
    routes = (ROOT / "api" / "routes.py").read_text(encoding="utf-8")
    assert '"/api/audit"' in routes
    assert "def _handle_audit_trail_read(handler, parsed):" in routes
    idx = routes.index("def _handle_audit_trail_read(handler, parsed):")
    end = routes.index("\ndef ", idx + 10)
    block = routes[idx:end]
    assert "read_session_audit_trail" in block
    assert "read_recent_audit_trail" in block
    assert '"Session not found", 404' in block
