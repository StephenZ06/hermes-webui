"""What one chat delegated to other profiles, so the Office can replay it.

The Office history sidebar answers "which chats delegated?" from hermes-agent's
own ``state.db``: ``delegate_task`` spawns its children inside that process, so
each one is a ``sessions`` row carrying ``parent_session_id``, and
``api/agent_sessions.py::list_parents_with_subagent_children`` groups them.

A ``delegate_to_profile`` child is a different animal. The tool creates it with
``POST /api/session/new``, so it lands in the TARGET profile's ``state.db`` as
an ordinary ``source='webui'`` row with ``parent_session_id`` NULL. Nothing
recorded that a chat caused it, and so a cross-profile run could be watched
live on the floor and then be gone from history the moment it ended — measured:
a three-profile fan-out left no trace the sidebar could find.

Writing that parent link into the child's ``state.db`` row was the other
option and is worse: the parent lives in a *different* profile's database, and
the grouping query is built on each database being a separate universe (a
session id in one never references a row in another). A cross-database parent
id would surface the child as its own top-level entry instead.

So this keeps the link on the WebUI side, where both ends are known — the tool
runs in this process.

Layout: one JSON file per child, ``<STATE_DIR>/cross_profile_delegations/
<parent_session_id>/<child_session_id>.json``. Per child rather than per
parent because siblings now run in parallel: a file per parent would make
three concurrent delegations read-modify-write the same file and lose each
other's rows.

Every function here is best-effort and returns rather than raises. It runs
inside a delegating turn and behind a supplementary sidebar; losing a history
entry is an acceptable cost, losing the delegation is not.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Both ids become a path segment. Session ids are hex-ish or
# ``20260909_115725_526495``-shaped; nothing else may be written or read, so a
# traversal cannot be spelled at all rather than being stripped after the fact.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_DIR_NAME = "cross_profile_delegations"


def _ledger_dir() -> Path:
    from api.config import STATE_DIR

    return STATE_DIR / _DIR_NAME


def _safe(value: Any) -> Optional[str]:
    text = str(value or "")
    return text if _SAFE_ID.match(text) else None


def _record_path(parent_session_id: str, child_session_id: str) -> Optional[Path]:
    parent = _safe(parent_session_id)
    child = _safe(child_session_id)
    if not parent or not child:
        logger.debug("refusing cross-profile ledger path for %r/%r", parent_session_id, child_session_id)
        return None
    return _ledger_dir() / parent / f"{child}.json"


def _write_record(path: Path, record: dict) -> None:
    """Atomically replace *path* with *record*, so a reader never sees a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_record(path: Path) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError):
        # A truncated or hand-edited file costs one desk, not the whole view.
        logger.debug("unreadable cross-profile ledger record %s", path, exc_info=True)
        return None
    return record if isinstance(record, dict) else None


def record_start(
    parent_session_id: str,
    child_session_id: str,
    *,
    profile: str,
    goal: str,
    model: Optional[str],
    started_at: float,
) -> None:
    """Note that *parent_session_id* has handed *goal* to *profile*.

    Written before the child's turn runs, not after it: a run that is
    interrupted still delegated, and a delegation with no end is exactly what
    the history should show (the replay reads that as 'interrupted').
    """
    path = _record_path(parent_session_id, child_session_id)
    if path is None:
        return
    try:
        _write_record(path, {
            "session_id": str(child_session_id),
            "parent_session_id": str(parent_session_id),
            # The floor's nameplate. `delegate_task` rows carry a
            # 'Subagent: ...' title that the replay strips; a goal needs no
            # such treatment, so it is stored as the title outright.
            "title": str(goal or ""),
            # What the LIVE floor seats this child under. Storing it means the
            # replay rebuilds the same per-profile pod instead of dropping
            # every cross-profile child onto the conductor.
            "cluster": f"profile:{profile}",
            "profile": str(profile or ""),
            "model": model,
            "started_at": float(started_at),
            "ended_at": None,
            "status": "running",
        })
    except Exception:
        logger.debug("failed to record cross-profile delegation start", exc_info=True)


def record_finish(
    parent_session_id: str,
    child_session_id: str,
    *,
    status: str,
    ended_at: float,
    input_tokens: Any = None,
    output_tokens: Any = None,
    reasoning_tokens: Any = None,
    cost_usd: Any = None,
    api_call_count: Any = None,
    tool_call_count: Any = None,
) -> None:
    """Fill in how the delegation went. A child nobody started is ignored."""
    path = _record_path(parent_session_id, child_session_id)
    if path is None:
        return
    try:
        record = _read_record(path)
        if record is None:
            # Never invent a delegation from its ending: without the start we
            # have no goal, no profile and no start time, so the entry would be
            # a desk with a blank nameplate.
            return
        record.update({
            "status": str(status or "completed"),
            "ended_at": float(ended_at),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cost_usd": cost_usd,
            "api_call_count": api_call_count,
            "tool_call_count": tool_call_count,
        })
        _write_record(path, record)
    except Exception:
        logger.debug("failed to record cross-profile delegation finish", exc_info=True)


def children_for_parent(parent_session_id: str) -> list[dict]:
    """Every delegation *parent_session_id* made, oldest first.

    Shaped like ``api/agent_sessions.py::_session_node_dict`` so the sidebar
    and the replay cannot tell a cross-profile child from a subagent one,
    apart from the ``cluster`` that is the point of the distinction.
    """
    parent = _safe(parent_session_id)
    if not parent:
        return []
    directory = _ledger_dir() / parent
    try:
        entries = sorted(directory.glob("*.json"))
    except OSError:
        return []
    children = []
    for entry in entries:
        record = _read_record(entry)
        if record and record.get("session_id"):
            children.append(record)
    children.sort(key=lambda row: row.get("started_at") or 0.0)
    return children


def parents_with_delegations(limit: int = 200) -> list[dict]:
    """Every chat that delegated across profiles, newest run first.

    Same entry shape ``list_parents_with_subagent_children`` returns, so the
    endpoint can merge the two lists without translating either.
    """
    try:
        directories = sorted(p for p in _ledger_dir().iterdir() if p.is_dir())
    except OSError:
        return []
    parents = []
    for directory in directories:
        children = children_for_parent(directory.name)
        if not children:
            continue
        parents.append({
            "parent_session_id": directory.name,
            "children": children,
            "latest_at": max((c.get("started_at") or 0.0) for c in children),
        })
    parents.sort(key=lambda entry: entry["latest_at"], reverse=True)
    return parents[:limit]
