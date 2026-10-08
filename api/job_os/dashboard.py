"""Server-owned, profile-scoped Job OS dashboard projections."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api.job_os.models import JobStatus
from api.job_os.repository import list_jobs

_ACTIVE_WORK_STATUSES = frozenset(
    {
        JobStatus.TAILORING,
        JobStatus.RESUME_READY,
        JobStatus.APPLICATION_READY,
        JobStatus.AWAITING_APPROVAL,
        JobStatus.APPLYING,
    }
)


def build_dashboard() -> dict[str, Any]:
    """Build current metrics exclusively from canonical active-profile records."""
    jobs = list_jobs()
    by_status: dict[str, int] = {}
    for job in jobs:
        by_status[job.status.value] = by_status.get(job.status.value, 0) + 1
    from api.job_os.applications import board, funnel

    # Every card the board flags, wherever it sits (a follow-up nudge stays in Applied).
    attention = sum(1 for column in board()["columns"] for card in column["jobs"]
                    if card["attention"] or column["key"] == "attention")
    return {
        "total_jobs": len(jobs),
        "by_status": by_status,
        "active_work": sum(job.status in _ACTIVE_WORK_STATUSES for job in jobs),
        "needs_attention": attention,
        "funnel": funnel(),
        "activity": activity(),
    }


ACTIVITY_DAYS = 190  # this month and the five before it


def activity(*, now: float | None = None) -> dict[str, Any]:
    """What happened each day, on your clock, for the dashboard calendars:
    jobs found, resumes tailored, applications sent, and the replies
    (interviews, rejections)."""
    from api.job_os.db import connect_job_os
    from api.job_os.settings import load_settings

    try:
        zone = ZoneInfo(load_settings()["scout"]["timezone"])
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        zone = ZoneInfo("UTC")
    now = time.time() if now is None else now
    since = int(now) - ACTIVITY_DAYS * 86400
    days: dict[str, dict[str, int]] = {}

    def add(at: int, kind: str) -> None:
        day = datetime.fromtimestamp(at, zone).strftime("%Y-%m-%d")
        days.setdefault(day, {})[kind] = days.get(day, {}).get(kind, 0) + 1

    conn = connect_job_os()
    try:
        for row in conn.execute("SELECT created_at FROM jobs WHERE created_at >= ?", (since,)):
            add(row["created_at"], "found")
        for row in conn.execute("SELECT created_at FROM job_documents WHERE kind='resume' AND status IN ('ready', 'needs_review')"
                                " AND created_at >= ?", (since,)):
            add(row["created_at"], "tailored")
        for row in conn.execute("SELECT event_type, payload_json, created_at FROM job_events WHERE created_at >= ?"
                                " AND event_type IN ('application_submitted', 'status_changed')", (since,)):
            if row["event_type"] == "application_submitted":
                add(row["created_at"], "applied")
                continue
            to = (json.loads(row["payload_json"] or "{}") or {}).get("to")
            if to in ("screening", "interviewing"):
                add(row["created_at"], "interview")
            elif to == "rejected":
                add(row["created_at"], "rejected")
    finally:
        conn.close()
    return {"today": datetime.fromtimestamp(now, zone).strftime("%Y-%m-%d"), "days": days}
