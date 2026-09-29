"""Read-only, profile-scoped scheduled-task runtime projection."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


_RUNTIME_LEDGER = ("cron", "runtime-jobs.json")
_MAX_LEDGER_AGE = timedelta(hours=24)
_COMPLETED_TASK_RETENTION = timedelta(minutes=5)
_MAX_TASKS = 100
_MAX_TEXT = 200
_ledger_lock = threading.Lock()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def validate_scheduled_tasks(rows: object, profile_name: str) -> list[dict]:
    """Fail closed over untrusted gateway or on-disk scheduler rows."""
    if not isinstance(rows, list) or len(rows) > _MAX_TASKS:
        return []
    wanted_profile = str(profile_name or "").strip()
    if not wanted_profile:
        return []
    accepted: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        job_id = row.get("job_id")
        name = row.get("name")
        mode = row.get("mode")
        started_at = row.get("started_at")
        profile = row.get("profile")
        status = row.get("status", "running")
        completed_at = row.get("completed_at")
        if not all(isinstance(value, str) and value.strip() for value in (job_id, name, started_at, profile)):
            continue
        if len(job_id) > _MAX_TEXT or len(name) > _MAX_TEXT or len(profile) > 80:
            continue
        if mode not in {"agent", "script"} or profile != wanted_profile:
            continue
        if status not in {"running", "completed", "failed"}:
            continue
        if _parse_time(started_at) is None:
            continue
        entry = {
            "job_id": job_id,
            "name": name,
            "mode": mode,
            "started_at": started_at,
            "profile": profile,
            "status": status,
        }
        if status != "running":
            if _parse_time(completed_at) is None:
                continue
            entry["completed_at"] = completed_at
        accepted.append(entry)
    return accepted


def _read_ledger(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {"version": 1, "jobs": []}
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("jobs"), list):
        return {"version": 1, "jobs": []}
    return raw


def _write_ledger(path: Path, jobs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "jobs": jobs,
    }, ensure_ascii=False, separators=(",", ":"))
    fd, temp_name = tempfile.mkstemp(prefix=".runtime-jobs-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def publish_scheduled_task_started(profile_home: Path, job: dict) -> None:
    """Publish non-secret manual-run activity to its owning profile ledger."""
    job_id = str((job or {}).get("id") or "").strip()
    if not job_id:
        return
    path = Path(profile_home).joinpath(*_RUNTIME_LEDGER)
    row = {
        "job_id": job_id,
        "name": str(job.get("name") or job_id)[:_MAX_TEXT],
        "mode": "script" if job.get("no_agent") else "agent",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "profile": str(job.get("profile") or "default")[:80],
        "status": "running",
    }
    with _ledger_lock:
        ledger = _read_ledger(path)
        jobs = [item for item in ledger["jobs"] if isinstance(item, dict) and item.get("job_id") != job_id]
        jobs.append(row)
        _write_ledger(path, jobs)


def publish_scheduled_task_finished(profile_home: Path, job_id: str, *, success: bool) -> None:
    """Keep a terminal manual-run record long enough for the Office to render it."""
    job_id = str(job_id or "").strip()
    if not job_id:
        return
    path = Path(profile_home).joinpath(*_RUNTIME_LEDGER)
    with _ledger_lock:
        ledger = _read_ledger(path)
        jobs = []
        for item in ledger["jobs"]:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            if row.get("job_id") == job_id:
                row["status"] = "completed" if success else "failed"
                row["completed_at"] = datetime.now(timezone.utc).isoformat()
            jobs.append(row)
        _write_ledger(path, jobs)


def load_scheduled_tasks(profile_home: Path, profile_name: str) -> list[dict]:
    """Return valid, current scheduled rows for one profile or an empty list."""
    path = Path(profile_home).joinpath(*_RUNTIME_LEDGER)
    raw = _read_ledger(path)
    if not isinstance(raw, dict) or raw.get("version") != 1:
        return []
    updated_at = _parse_time(raw.get("updated_at"))
    if updated_at is None or datetime.now(timezone.utc) - updated_at > _MAX_LEDGER_AGE:
        return []
    tasks = validate_scheduled_tasks(raw.get("jobs"), profile_name)
    now = datetime.now(timezone.utc)
    return [
        task for task in tasks
        if task["status"] == "running"
        or now - _parse_time(task["completed_at"]) <= _COMPLETED_TASK_RETENTION
    ]
