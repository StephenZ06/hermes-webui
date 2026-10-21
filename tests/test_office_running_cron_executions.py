"""Scheduler-fired cron runs reach the Office (not only WebUI manual runs)."""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api.scheduled_tasks import load_running_executions


def _home(tmp_path: Path, rows):
    cron = tmp_path / "cron"
    cron.mkdir()
    (cron / "jobs.json").write_text(json.dumps({"jobs": [
        {"id": "live1", "name": "Nightly digest", "no_agent": False},
        {"id": "script1", "name": "Backup", "no_agent": True},
    ]}))
    db = sqlite3.connect(cron / "executions.db")
    db.execute("CREATE TABLE executions (id TEXT PRIMARY KEY, job_id TEXT, source TEXT, process_id TEXT, pid INTEGER,"
               " process_started_at INTEGER, status TEXT, claimed_at TEXT, started_at TEXT, finished_at TEXT, error TEXT)")
    for i, (job_id, pid, status, started) in enumerate(rows):
        db.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (f"e{i}", job_id, "builtin", "p", pid, 0, status, started, started, None, None))
    db.commit()
    db.close()
    return tmp_path


def test_only_live_running_executions_become_office_tasks(tmp_path):
    now = datetime.now(timezone.utc)
    recent = now.isoformat()
    old = (now - timedelta(days=2)).isoformat()
    dead_pid = 999_999_9
    home = _home(tmp_path, [
        ("live1", os.getpid(), "running", recent),   # shown
        ("script1", dead_pid, "running", recent),    # process gone: stale
        ("live1", os.getpid(), "claimed", recent),   # not started
        ("script1", os.getpid(), "running", old),    # too old
    ])

    tasks = load_running_executions(home, "default")

    assert [(t["job_id"], t["name"], t["mode"], t["status"], t["profile"]) for t in tasks] == [
        ("live1", "Nightly digest", "agent", "running", "default")]


def test_missing_or_broken_database_is_empty(tmp_path):
    assert load_running_executions(tmp_path, "default") == []
    (tmp_path / "cron").mkdir()
    (tmp_path / "cron" / "executions.db").write_text("not a database")
    assert load_running_executions(tmp_path, "default") == []
