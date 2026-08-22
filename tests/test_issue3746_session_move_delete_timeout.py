"""Regression tests for #3746 — timeouts on session move / project delete
during active streaming.

Two distinct root causes, two fixes:

A) /api/session/move acquired the per-session agent lock with a bare, unbounded
   `with _get_session_agent_lock(sid):`. The streaming thread holds that same
   lock during checkpoint saves, so on slow file I/O (WSL/DrvFs) the move could
   block past the client's 30s abort and surface as a silent "Request timed out"
   toast. Fix: bounded `acquire(timeout=5)` → HTTP 503 on contention.

B) /api/projects/delete unlinked every assigned session with a full
   get_session() + s.save() (O(N) full-messages reserialize). For a project with
   many messageful sessions that throughput alone blows past 30s. Fix: skip
   actively-streaming sessions (largest arrays + race the writer) and guard each
   per-session save so one slow/failing session can't abort the whole request.
"""
import threading
from pathlib import Path

ROUTES_SRC = (Path(__file__).parent.parent / "api" / "routes.py").read_text(encoding="utf-8")


# ── A) Behavioral: the bounded lock acquire actually returns instead of blocking ──

class TestBoundedLockAcquire:
    """The fix relies on threading.Lock.acquire(timeout=...) returning False
    promptly when the lock is held, instead of blocking forever. Pin that
    primitive behavior so the move handler's 503 path is reachable."""

    def test_acquire_timeout_returns_false_when_held(self):
        lock = threading.Lock()
        lock.acquire()  # simulate the streaming thread holding it
        try:
            import time
            t0 = time.monotonic()
            acquired = lock.acquire(timeout=0.2)
            elapsed = time.monotonic() - t0
            assert acquired is False, "bounded acquire must give up, not block, when the lock is held"
            assert elapsed < 1.0, f"bounded acquire must return near its timeout, took {elapsed:.2f}s"
        finally:
            lock.release()

    def test_acquire_succeeds_when_free(self):
        lock = threading.Lock()
        acquired = lock.acquire(timeout=0.2)
        assert acquired is True
        lock.release()


# ── A) Structural: the move handler uses a bounded acquire + 503, not a bare `with` ──

def _move_block():
    idx = ROUTES_SRC.find('"/api/session/move"')
    assert idx > 0, "session/move handler not found"
    end = ROUTES_SRC.find('"/api/projects/create"', idx)
    return ROUTES_SRC[idx:end]


def test_move_uses_bounded_lock_acquire():
    block = _move_block()
    assert ".acquire(timeout=" in block, (
        "session/move must acquire the agent lock with a bounded timeout, not block forever (#3746)"
    )
    # Must NOT still use the bare blocking `with _get_session_agent_lock(...)` form
    # around the save (that's the regression we're removing).
    assert "with _get_session_agent_lock(body[\"session_id\"]):" not in block, (
        "session/move must not use a bare unbounded `with` lock acquire anymore (#3746)"
    )


def test_move_returns_503_on_lock_contention():
    block = _move_block()
    assert "status=503" in block, (
        "session/move must return HTTP 503 when the lock can't be acquired in time (#3746)"
    )


def test_move_releases_lock_in_finally():
    block = _move_block()
    # The lock must be released on every path once acquired.
    assert "finally:" in block and ".release()" in block, (
        "session/move must release the agent lock in a finally block (#3746)"
    )


# ── B) Structural: project delete skips streaming sessions + guards each save ──
#
# This logic used to live inline in the /api/projects/delete handler. It was
# factored out into `_reassign_project_sessions` (2026-08-19) so
# /api/projects/merge could reuse the exact same lock-sensitive behavior
# instead of duplicating it — see test_project_merge_reassigns_sessions.py.
# These tests now pin the HELPER's source block; delete just calls it.

def _delete_block():
    idx = ROUTES_SRC.find('"/api/projects/delete"')
    assert idx > 0, "projects/delete handler not found"
    end = ROUTES_SRC.find('"/api/projects/merge"', idx)
    return ROUTES_SRC[idx:end]


def _reassign_helper_block():
    idx = ROUTES_SRC.find("def _reassign_project_sessions(")
    assert idx > 0, "_reassign_project_sessions helper not found"
    end = ROUTES_SRC.find("\ndef handle_post(", idx)
    return ROUTES_SRC[idx:end]


def test_delete_delegates_to_shared_reassign_helper():
    block = _delete_block()
    assert "_reassign_project_sessions({body[\"project_id\"]}, None)" in block, (
        "projects/delete must reassign (unassign) via the shared helper, not "
        "an inline duplicate of the streaming-session-safe logic (#3746)"
    )


def test_reassign_helper_clears_project_id_on_streaming_sessions_in_cache():
    block = _reassign_helper_block()
    assert "_active_stream_ids()" in block, (
        "the reassign helper must compute the active stream set to special-case streaming sessions (#3746)"
    )
    assert 'entry.get("active_stream_id") in active_ids' in block, (
        "the reassign helper must detect sessions whose active_stream_id is currently streaming (#3746)"
    )
    # The streaming session's project_id must be updated on the LIVE CACHED object
    # (so the streaming thread persists it) — NOT left dangling, and NOT given a
    # competing s.save() that races the streaming writer.
    assert "cached.project_id = new_project_id" in block, (
        "the reassign helper must update project_id on the live cached streaming session so the "
        "streaming thread persists it — not leave a dangling pointer (#3746)"
    )
    assert "with LOCK:" in block, (
        "the cached-object mutation must happen under the session cache LOCK (#3746)"
    )


def test_reassign_helper_guards_each_session_save():
    block = _reassign_helper_block()
    # Each per-session update stays wrapped in try/except so one slow/failing
    # session can't abort the whole batch.
    assert "try:" in block and "except Exception:" in block, (
        "the reassign helper must guard each per-session update (#3746)"
    )


# ── Frontend: the '+ New project and move' shortcut guards the new 503 ──

SESSIONS_JS = (Path(__file__).parent.parent / "static" / "sessions.js").read_text(encoding="utf-8")


def test_new_project_and_move_shortcut_guards_503():
    """The '+ New project and move' shortcut must catch a failed move (e.g. 503
    when the session is streaming) instead of leaving an unhandled rejection (#3746)."""
    idx = SESSIONS_JS.find("Guard the move so a 503")
    assert idx > 0, "the new-project-and-move shortcut guard not found"
    block = SESSIONS_JS[idx:idx + 800]
    assert "try{" in block and "}catch(e){" in block, (
        "the new-project-and-move move call must be wrapped in try/catch (#3746)"
    )
    assert "move failed" in block.lower(), (
        "a failed move must surface an actionable toast (#3746)"
    )
    # The authoritative refetch (#2551) must remain in the success path.
    assert "await renderSessionList()" in block, (
        "the shortcut must keep its authoritative /api/sessions refetch (#2551)"
    )
