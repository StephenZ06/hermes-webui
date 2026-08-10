"""Read-only Audit Trail aggregation over the existing turn/run journals.

No new storage: reduces api.turn_journal's per-turn lifecycle events
(submitted -> completed/interrupted) into a browsable list, optionally
enriched per-turn with api.run_journal's run summary. See
docs/HERMES_STUDIO_PARITY_PLAN.md, "Priority 3 -- Audit Trail UI".

Scope note baked in here, not just the doc: both journals are deleted
alongside their session (privacy-driven, #3802 -- they hold plaintext
message/request/response content), so this is a recent-activity trail for
sessions currently on disk, not a permanent audit log independent of
session lifetime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from api.run_journal import find_run_summary
from api.turn_journal import TURN_JOURNAL_DIR_NAME, is_terminal_turn_event, read_turn_journal

_CONTENT_PREVIEW_MAX_CHARS = 200
_CROSS_SESSION_SHARD_SCAN_CAP = 200
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def _truncate_preview(text: Any) -> str:
    text = str(text or "").strip()
    if len(text) <= _CONTENT_PREVIEW_MAX_CHARS:
        return text
    return text[:_CONTENT_PREVIEW_MAX_CHARS].rstrip() + "..."


def _group_turn_events(events: list[dict]) -> dict[str, dict[str, Any]]:
    """Group raw turn-journal events by turn_id.

    Keeps the original ``submitted`` event (content/model/attachments/
    workspace) separate from the latest terminal event (completed/
    interrupted). A plain latest-event-wins reduction (like
    derive_turn_journal_states) would lose the submission's detail the
    moment a turn goes terminal, since completed/interrupted events don't
    carry that payload.
    """
    groups: dict[str, dict[str, Any]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        turn_id = str(event.get("turn_id") or "").strip()
        if not turn_id:
            continue
        group = groups.setdefault(turn_id, {"submitted": None, "terminal": None, "latest": None})
        if str(event.get("event") or "") == "submitted" and group["submitted"] is None:
            group["submitted"] = event
        if is_terminal_turn_event(event):
            prev_terminal = group["terminal"]
            if prev_terminal is None or float(event.get("created_at") or 0) >= float(prev_terminal.get("created_at") or 0):
                group["terminal"] = event
        prev_latest = group["latest"]
        if prev_latest is None or float(event.get("created_at") or 0) >= float(prev_latest.get("created_at") or 0):
            group["latest"] = event
    return groups


def _entry_from_group(
    session_id: str,
    turn_id: str,
    group: dict[str, Any],
    *,
    include_run_summary: bool,
    session_dir: Path,
) -> dict[str, Any]:
    submitted = group.get("submitted")
    terminal = group.get("terminal")
    latest = group.get("latest") or {}
    stream_id = str((submitted or terminal or latest).get("stream_id") or "") or None
    entry: dict[str, Any] = {
        "session_id": session_id,
        "turn_id": turn_id,
        "stream_id": stream_id,
        "submitted_at": (submitted or {}).get("created_at"),
        "role": (submitted or {}).get("role") or "user",
        "content_preview": _truncate_preview((submitted or {}).get("content")) if submitted else "",
        "model": (submitted or {}).get("model"),
        "model_provider": (submitted or {}).get("model_provider"),
        "status": str(terminal.get("event")) if terminal else "running",
        "ended_at": (terminal or {}).get("created_at"),
    }
    if include_run_summary and stream_id:
        try:
            summary = find_run_summary(stream_id, session_dir=session_dir)
        except ValueError:
            summary = None
        if summary is not None:
            entry["run_summary"] = {
                "run_id": summary.get("run_id"),
                "terminal_state": summary.get("terminal_state"),
                "event_count": summary.get("event_count"),
                "last_event": summary.get("last_event"),
            }
    return entry


def _sort_key(entry: dict[str, Any]) -> float:
    for field in ("submitted_at", "ended_at"):
        value = entry.get(field)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def read_session_audit_trail(session_id: str, *, session_dir: Path) -> list[dict[str, Any]]:
    """Every turn for one session, newest first.

    Enriched with a best-effort run_summary per turn -- affordable here
    since one session has a bounded number of turns. The cross-session view
    (read_recent_audit_trail) intentionally skips this enrichment.
    """
    journal = read_turn_journal(session_id, session_dir=session_dir)
    groups = _group_turn_events(journal.get("events") or [])
    entries = [
        _entry_from_group(session_id, turn_id, group, include_run_summary=True, session_dir=session_dir)
        for turn_id, group in groups.items()
    ]
    entries.sort(key=_sort_key, reverse=True)
    return entries


def _recent_turn_journal_session_ids(session_dir: Path, *, cap: int) -> list[str]:
    """Distinct session_ids with a turn-journal shard, most-recently-modified
    shard first, capped so a profile with many old sessions can't make the
    cross-session view stat-and-parse every shard on every request."""
    journal_dir = Path(session_dir) / TURN_JOURNAL_DIR_NAME
    if not journal_dir.exists():
        return []
    try:
        shards = sorted(
            (p for p in journal_dir.glob("*.jsonl") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []
    session_ids: list[str] = []
    seen: set[str] = set()
    for shard in shards:
        stem = shard.stem
        tilde = stem.find("~")
        sid = stem[:tilde] if tilde > 0 else stem
        if sid in seen:
            continue
        seen.add(sid)
        session_ids.append(sid)
        if len(session_ids) >= cap:
            break
    return session_ids


def read_recent_audit_trail(*, session_dir: Path, limit: int = _DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Cross-session recent activity, newest first, capped at `limit`.

    Does not enrich with run_summary -- that's an extra find_run_summary
    glob per turn, affordable for one session's detail view but not
    unconditionally across every session on every poll of this list.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = _DEFAULT_LIMIT
    limit = max(1, min(limit, _MAX_LIMIT))
    entries: list[dict[str, Any]] = []
    for session_id in _recent_turn_journal_session_ids(session_dir, cap=_CROSS_SESSION_SHARD_SCAN_CAP):
        journal = read_turn_journal(session_id, session_dir=session_dir)
        groups = _group_turn_events(journal.get("events") or [])
        for turn_id, group in groups.items():
            entries.append(
                _entry_from_group(session_id, turn_id, group, include_run_summary=False, session_dir=session_dir)
            )
    entries.sort(key=_sort_key, reverse=True)
    return entries[:limit]
