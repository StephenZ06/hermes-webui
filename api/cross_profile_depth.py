"""Per-session cross-profile delegation depth.

hermes-agent's ``delegate_to_profile`` tool drives a target profile's whole
turn over loopback HTTP (``/api/profile/switch`` -> ``/api/session/new`` ->
``/api/chat``). The child turn runs on a brand-new ``AIAgent`` instance, so the
tool's own per-instance counter cannot survive that hop -- the depth travels as
the ``X-Hermes-Cross-Profile-Depth`` request header and has to be readable
again from inside the child's turn, where the tool decides whether a further
hop is allowed.

That used to be done by republishing the header into
``os.environ["HERMES_CROSS_PROFILE_DEPTH"]`` for the duration of the turn.
A process-global cannot express per-request state: a delegated child turn sets
it and holds it for its entire duration, so every other turn running
concurrently in the same process reads depth 1 and refuses its own first hop
with "depth limit reached (1/1)". Keying by session id fixes that, and the
registry already hands ``session_id`` to every tool handler, so the tool can
look up exactly its own turn.

The depth cap it feeds is not a policy nicety: ``_handle_chat_sync`` holds the
process-global ``CHAT_LOCK`` for a whole turn, so a hop issued from inside a
child's turn would block on a lock its own parent holds. Reads therefore fail
CLOSED -- a value we cannot parse reports as over-deep rather than as a
top-level turn.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

# Reported when a recorded depth cannot be parsed. Any sane cap is <= this, so
# the tool refuses rather than letting an unbounded chain block on CHAT_LOCK.
FAIL_CLOSED_DEPTH = 1_000_000

_lock = threading.Lock()
_depth_by_session: dict[str, int] = {}


def _coerce(raw) -> int | None:
    """Parse a header value into a depth, or None when there is nothing to record.

    Absent/blank means "no delegation happened", which is a top-level turn and
    deliberately records nothing. Anything present but unreadable becomes
    ``FAIL_CLOSED_DEPTH``: it is a depth we were told about and failed to
    understand, which must not read back as top-level.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = int(text)
    except (TypeError, ValueError):
        return FAIL_CLOSED_DEPTH
    if value < 0:
        return FAIL_CLOSED_DEPTH
    return value


def get_depth(session_id: str | None) -> int:
    """Current delegation depth for *session_id*; 0 when it is a top-level turn."""
    if not session_id:
        return 0
    with _lock:
        return _depth_by_session.get(str(session_id), 0)


@contextmanager
def for_session(session_id: str | None, raw_depth):
    """Record *raw_depth* for *session_id* for the duration of the block.

    Restores whatever was recorded before, so a nested scope on the same
    session unwinds correctly, and clears on exception so an aborted turn
    cannot strand a depth for the next turn in that session.
    """
    depth = _coerce(raw_depth)
    if not session_id or depth is None:
        yield
        return

    key = str(session_id)
    with _lock:
        previous = _depth_by_session.get(key)
        _depth_by_session[key] = depth
    try:
        yield
    finally:
        with _lock:
            if previous is None:
                _depth_by_session.pop(key, None)
            else:
                _depth_by_session[key] = previous


def _clear_all_for_tests() -> None:
    with _lock:
        _depth_by_session.clear()
