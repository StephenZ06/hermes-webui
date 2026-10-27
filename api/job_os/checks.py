"""The checks shown on a job: one list, built here for the board card and the
job drawer alike, so both always say the same thing.

Each check is ``{"key", "tone", "short", "label", "detail", "quotes"}``:
``tone`` is ``danger`` (the job is held back from automation) or ``warn``
(worth a look). A held check can be ignored per job (``set_override``): you
know the posting better than the model does.
"""

from __future__ import annotations

import json
import time
import uuid

from api.job_os import posting_guard
from api.job_os.db import connect_job_os

# Checks that hold a job back and that you can ignore on a job.
OVERRIDABLE = ("eligibility", "language")


def _gate_checks(gates: dict, overrides: tuple) -> list[dict]:
    checks = []
    eligibility, language = gates.get("eligibility"), gates.get("language")
    if eligibility == "fail":
        checks.append({"key": "eligibility", "tone": "danger", "short": "Not eligible",
                       "label": "You may not be eligible to work in this job",
                       "detail": "The posting asks for a right to work your application answers don't show."})
    elif eligibility == "unverified":
        checks.append({"key": "eligibility", "tone": "warn", "short": "Right to work?",
                       "label": "The right to work isn't confirmed",
                       "detail": "The posting doesn't say whether visa holders can apply, or your answers don't say."})
    if language == "fail":
        checks.append({"key": "language", "tone": "danger", "short": "Language",
                       "label": "A required language isn't in your answers",
                       "detail": "The posting needs a language your application answers don't list."})
    elif language == "flag":
        checks.append({"key": "language", "tone": "warn", "short": "Language level",
                       "label": "The language level may be above yours",
                       "detail": "The posting asks for a higher level than your answers state."})
    for check in checks:
        quote = gates.get(f"{check['key']}_quote")
        check["quotes"] = [quote] if quote else []
        if check["tone"] == "danger":
            check["actions"] = [{"label": "Ignore this check", "action": "check-override", "value": "1"}]
            if check["key"] in overrides:
                check.update(tone="muted", short="", detail="You chose to ignore this check; the job is treated as eligible.",
                             actions=[{"label": "Check again", "action": "check-override", "value": "0"}])
    if gates.get("profile_missing") and any(c["tone"] == "warn" for c in checks):
        checks.append({"key": "profile", "tone": "warn", "short": "",
                       "label": "Add your work authorisation and languages in Settings",
                       "detail": "Luna judges these checks against Settings → Application answers.",
                       "actions": [{"label": "Open Settings", "view": "settings"}]})
    return checks


def job_checks(job, analysis: dict | None = None) -> list[dict]:
    """Every check on one job, most serious first."""
    checks: list[dict] = []
    guard = posting_guard.public(job.guard)
    if guard:
        checks.append({"key": "guard", "tone": "warn", "short": "Hidden text",
                       "label": "Hidden instructions found",
                       "detail": guard["summary"] + ". Luna was told to ignore it; check the posting yourself.",
                       "quotes": guard["excerpts"]})
    if analysis and analysis.get("status") == "done" and isinstance(analysis.get("gates"), dict):
        checks.extend(_gate_checks(analysis["gates"], tuple(job.overrides or ())))
    order = {"danger": 0, "warn": 1, "muted": 2}
    return sorted(checks, key=lambda c: order.get(c["tone"], 1))


def held_by(job, analysis: dict | None) -> list[str]:
    """The failed checks holding a job back from the inbox, the match email and
    Automate all (empty when nothing does, or every one was ignored)."""
    if not analysis or analysis.get("status", "done") != "done":
        return []
    gates = analysis.get("gates") if isinstance(analysis.get("gates"), dict) else {}
    overrides = set(job.overrides or ())
    return [key for key in OVERRIDABLE if gates.get(key) == "fail" and key not in overrides]


def set_override(job_id: str, key: str, on: bool) -> tuple:
    """Ignore (or stop ignoring) one check on one job; logged on the job."""
    if key not in OVERRIDABLE:
        raise ValueError("That check can't be ignored")
    conn = connect_job_os()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT overrides_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            conn.rollback()
            raise KeyError(job_id)
        current = [k for k in json.loads(row["overrides_json"] or "[]") if k in OVERRIDABLE]
        updated = sorted(set(current) | {key}) if on else [k for k in current if k != key]
        now = int(time.time())
        conn.execute("UPDATE jobs SET overrides_json=?, revision=revision+1, updated_at=? WHERE id=?",
                     (json.dumps(updated), now, job_id))
        conn.execute("INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), job_id, "check_ignored" if on else "check_restored",
                      json.dumps({"check": key}), now))
        conn.commit()
        return tuple(updated)
    finally:
        conn.close()
