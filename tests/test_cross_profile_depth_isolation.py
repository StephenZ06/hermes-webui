"""Cross-profile delegation depth must be per-turn, not process-global.

The depth used to travel as ``os.environ["HERMES_CROSS_PROFILE_DEPTH"]``,
republished by ``_handle_chat_sync`` for the duration of a turn. That is a
process-global for per-request state, and it cross-talks: a delegated child
turn sets it and holds it for its entire duration, so every OTHER turn running
concurrently in the same process reads depth 1 and refuses its own first hop
with "depth limit reached (1/1)". Observed live -- a first-hop delegation in a
brand-new session was refused while an unrelated child turn was still running.

The depth is now keyed by the session it belongs to. Concurrent turns have
distinct session ids, so they cannot see each other's depth.
"""
import threading

import pytest

from api import cross_profile_depth as depth


@pytest.fixture(autouse=True)
def _clean_store():
    depth._clear_all_for_tests()
    yield
    depth._clear_all_for_tests()


def test_unset_session_reads_zero():
    """A turn nobody delegated into is a top-level turn."""
    assert depth.get_depth('session-a') == 0


def test_scope_sets_and_clears():
    with depth.for_session('session-a', '1'):
        assert depth.get_depth('session-a') == 1
    assert depth.get_depth('session-a') == 0


def test_scope_clears_on_exception():
    """An aborted turn must not leave its depth behind for the next one."""
    with pytest.raises(RuntimeError):
        with depth.for_session('session-a', '1'):
            raise RuntimeError('turn blew up')
    assert depth.get_depth('session-a') == 0


def test_concurrent_sessions_do_not_see_each_other():
    """The regression this module exists for.

    A delegated child turn holds depth 1 for its whole duration. A different
    session's turn running at the same time must still read 0, or its own
    first hop is refused for no reason.
    """
    child_entered = threading.Event()
    sibling_read = []
    release_child = threading.Event()

    def child():
        with depth.for_session('child-session', '1'):
            child_entered.set()
            release_child.wait(timeout=5)

    t = threading.Thread(target=child)
    t.start()
    assert child_entered.wait(timeout=5)
    try:
        # While the child turn is mid-flight and holding depth 1:
        sibling_read.append(depth.get_depth('sibling-session'))
        sibling_read.append(depth.get_depth('child-session'))
    finally:
        release_child.set()
        t.join(timeout=5)

    assert sibling_read == [0, 1]
    assert depth.get_depth('child-session') == 0


def test_absent_or_blank_header_is_not_recorded():
    """No header means top-level; the scope must not invent an entry."""
    for value in (None, '', '   '):
        with depth.for_session('session-a', value):
            assert depth.get_depth('session-a') == 0
        assert depth.get_depth('session-a') == 0


@pytest.mark.parametrize('raw', ['abc', '1.5', '-1', '99999999999999999999999999'])
def test_unparseable_depth_fails_closed(raw):
    """A depth we cannot read must never be treated as "top level".

    Reading garbage as 0 would let an unbounded delegation chain through, and
    each hop blocks on CHAT_LOCK. Refusing a legitimate hop is the cheap
    failure; deadlocking the server is not.
    """
    with depth.for_session('session-a', raw):
        assert depth.get_depth('session-a') >= depth.FAIL_CLOSED_DEPTH


def test_nested_scopes_restore_the_outer_value():
    with depth.for_session('session-a', '1'):
        with depth.for_session('session-a', '2'):
            assert depth.get_depth('session-a') == 2
        assert depth.get_depth('session-a') == 1
    assert depth.get_depth('session-a') == 0


def test_blank_session_id_is_inert():
    """A turn with no session id must not collide with other blank-id turns."""
    with depth.for_session('', '1'):
        assert depth.get_depth('') == 0
