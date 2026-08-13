"""Regression coverage for the archive/move race in the chat sidebar.

The bug: archiving a session or moving it to a folder mutates `_allSessions`
locally and re-renders — but a concurrent 30s background poll
(`startStreamingPoll`) or any other in-flight `renderSessionList()` fetch can
resolve afterward with pre-mutation server data and silently overwrite it via
the wholesale `_allSessions = _mergeOptimisticFirstTurnSessions(serverSessions)`
assignment. The archived chat reappears (or never visibly disappears), and a
folder move looks like it never happened, until the next poll finally reflects
the true persisted state.

The fix mirrors the codebase's own existing pattern for this exact class of
problem (`_optimisticallyRemovedSessionIds`, used for in-flight deletes): a
`_optimisticSessionFieldOverrides` Map records the field(s) just set locally
and reapplies them onto any freshly-fetched session object until the server
itself reports the same value.

These are source-structure assertions (`static/sessions.js` is a large,
non-modular script with no test harness that constructs its functions in
isolation) — same precedent as `test_cross_session_message_load_isolation.py`.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
SESSIONS = (REPO / "static" / "sessions.js").read_text(encoding="utf-8")


def test_optimistic_override_map_and_helpers_exist():
    assert "const _optimisticSessionFieldOverrides = new Map();" in SESSIONS
    assert "function _setOptimisticSessionField(sid, field, value){" in SESSIONS
    assert "function _applyOptimisticSessionFieldOverrides(serverSessions){" in SESSIONS


def test_overrides_applied_before_wholesale_allsessions_assignment():
    # The override pass must run on the fetched list BEFORE it replaces
    # _allSessions, or the race it exists to close would still happen.
    apply_idx = SESSIONS.index("_applyOptimisticSessionFieldOverrides(")
    assign_idx = SESSIONS.index(
        "_allSessions = _mergeOptimisticFirstTurnSessions(serverSessions);"
    )
    assert apply_idx < assign_idx, (
        "_applyOptimisticSessionFieldOverrides must run before the wholesale "
        "_allSessions assignment, or a racing fetch can still overwrite an "
        "optimistic archive/move"
    )


def test_archive_sets_optimistic_override():
    start = SESSIONS.index("async function _archiveSession(")
    end = SESSIONS.index("\nfunction _openSessionActionMenu(", start)
    body = SESSIONS[start:end]
    assert "_setOptimisticSessionField(session.session_id,'archived',archived);" in body, (
        "_archiveSession must record its local mutation as an optimistic "
        "override so a racing background poll can't silently revert it"
    )


def test_all_four_single_session_move_sites_set_optimistic_override():
    # dropInto (pointer drag-to-folder), the "No project" picker option, a
    # named-project picker item, and the "+ New project" create-and-move
    # flow — all four call POST /api/session/move for a single session and
    # must each guard their local _allSessions mutation the same way.
    # (Two separate bulk-move call sites also exist, for multi-select; those
    # don't do a local optimistic mutation at all — they await their own
    # fresh renderSessionList() — so they aren't exposed to this race and
    # are intentionally excluded from this count.)
    occurrences = SESSIONS.count(
        "await api('/api/session/move',{method:'POST',"
    )
    override_calls = SESSIONS.count("_setOptimisticSessionField(session.session_id,'project_id'")
    assert occurrences == 4, (
        f"expected 4 single-session move call sites, found {occurrences} — "
        "if this changed, the override coverage below needs updating to match"
    )
    assert override_calls == 4, (
        "every single-session /api/session/move call site must set an "
        "optimistic project_id override, or that path is still exposed to the race"
    )


def test_override_self_clears_once_server_confirms_value():
    start = SESSIONS.index("function _applyOptimisticSessionFieldOverrides(serverSessions){")
    end = SESSIONS.index("\n}\n", start)
    body = SESSIONS[start:end]
    assert "if(allConfirmed) _optimisticSessionFieldOverrides.delete(s.session_id);" in body, (
        "an override must be dropped once the server's own value matches it — "
        "otherwise a stale override could mask a legitimate LATER external "
        "change to the same session"
    )
