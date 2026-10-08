"""What Job OS does on its own, and when (Settings -> Automations).

Read-only summary of the background work driven by the scheduler loop
(scheduler.py): Scout runs, Luna analysis, match alerts, the daily digest
and reply checks. Nothing here starts work; it reports settings
and the last/next run times so the schedule is visible in one place.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api import mailer

HISTORY_DAYS = 14


def _next_digest(hour: int, last: str | None, now: float) -> int:
    local = time.localtime(now)
    today = time.strftime("%Y-%m-%d", local)
    start = time.mktime(local[:3] + (hour, 0, 0, 0, 0, -1))
    if last == today:
        start += 86400  # today's has gone out
    elif now >= start:
        start = now + 60  # due now: the next scheduler tick sends it
    return int(start)


def _scout_when(scout: dict) -> str:
    if scout.get("schedule_mode") == "interval":
        return f"Every {scout['schedule_hours']} h"
    weekend = {"saturday": ", Saturday once", "same": " daily", "none": " on weekdays"}.get(scout.get("weekend"), "")
    return f"At {' and '.join(scout.get('run_times') or [])}{weekend}"


def summary(*, now: float | None = None) -> list[dict]:
    from api.job_os import notify, scheduler, scout
    from api.job_os.analysis import queue_counts
    from api.job_os.settings import load_settings

    now = time.time() if now is None else now
    settings = load_settings()
    n = settings["notifications"]
    email = bool(n["email_enabled"] and n["to_address"] and all(mailer.credentials()))
    state = notify.load_state()
    searches = [s for s in scout.list_searches() if s["enabled"]]
    next_scout = min((t for t in (scheduler.next_run_at(s, settings) for s in searches) if t), default=None)
    last_scout = max((s.get("last_run_at") or 0 for s in searches), default=0) or None
    queue = queue_counts()
    past = history(now=now, settings=settings)
    items = [
        {"key": "scout", "label": "Scout searches", "on": bool(settings["scout"]["enabled"] and searches),
         "schedule": f"{_scout_when(settings['scout'])} · {len(searches)} saved search{'es' if len(searches) != 1 else ''}",
         "last": last_scout, "next": next_scout if settings["scout"]["enabled"] else None,
         "off_reason": "" if settings["scout"]["enabled"] else "Turn on Run Scout automatically", "view": "scout"},
        {"key": "analysis", "label": "Luna fit analysis", "on": bool(settings["ai"]["auto_analyze"]),
         "schedule": "After each Scout run", "last": None, "next": None,
         "detail": f"{queue.get('pending', 0) + queue.get('running', 0)} in the queue",
         "off_reason": "" if settings["ai"]["auto_analyze"] else "Turn on Analyse new finds automatically"},
        {"key": "alerts", "label": "Match alert emails", "on": email and bool(n["notify_new_matches"]),
         "schedule": f"When a job scores {n['min_fit_score']}+", "last": None, "next": None,
         "off_reason": "" if email else "Connect Gmail and turn on Email me"},
        {"key": "digest", "label": "Daily digest", "on": email and bool(n["daily_digest"]),
         "schedule": f"Daily at {n['digest_hour']:02d}:00", "last": state.get("last_digest"),
         "next": _next_digest(n["digest_hour"], state.get("last_digest"), now) if email and n["daily_digest"] else None,
         "off_reason": "" if email else "Connect Gmail and turn on Email me"},
        {"key": "replies", "label": "Reply commands", "on": email and bool(n["reply_actions"]),
         "schedule": f"Inbox checked every {notify.POLL_EVERY // 60} min", "last": state.get("last_poll"),
         "next": int((state.get("last_poll") or now) + notify.POLL_EVERY) if email and n["reply_actions"] else None,
         "detail": state.get("last_poll_error") or "", "off_reason": "" if email else "Connect Gmail and turn on Email me"},
        ]
    for item in items:
        item["history"] = past.get(item["key"], [])
    return items


def history(*, now: float | None = None, settings: dict | None = None, days: int = HISTORY_DAYS) -> dict[str, list[dict]]:
    """The last ``days`` days of each automation, oldest first, on your clock:
    one entry per day with how many runs went well and how many failed (a
    status-page row of ticks). Scout: finished runs; Luna: finished analyses;
    alerts and the digest: emails sent; replies: replies acted on."""
    from api.job_os.db import connect_job_os
    from api.job_os.settings import load_settings

    settings = settings or load_settings()
    try:
        zone = ZoneInfo(settings["scout"]["timezone"])
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        zone = ZoneInfo("UTC")
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, zone).date()
    first = today - timedelta(days=days - 1)
    since = int(datetime(first.year, first.month, first.day, tzinfo=zone).timestamp())
    tally: dict[str, dict] = {}

    def add(key: str, at: int | None, ok: bool | None) -> None:
        if not at or ok is None:
            return
        day = datetime.fromtimestamp(at, zone).date().isoformat()
        entry = tally.setdefault(key, {}).setdefault(day, {"ok": 0, "failed": 0})
        entry["ok" if ok else "failed"] += 1

    conn = connect_job_os()
    try:
        for row in conn.execute("SELECT status, COALESCE(finished_at, created_at) AS at FROM discovery_runs WHERE created_at >= ?", (since,)):
            add("scout", row["at"], {"completed": True, "failed": False, "interrupted": False}.get(row["status"]))
        for row in conn.execute("SELECT status, finished_at FROM job_analyses WHERE finished_at >= ?", (since,)):
            add("analysis", row["finished_at"], {"done": True, "failed": False}.get(row["status"]))
        for row in conn.execute("SELECT kind, status, created_at FROM email_log WHERE created_at >= ?", (since,)):
            key = {"matches": "alerts", "digest": "digest", "reply": "replies"}.get(row["kind"])
            if key:
                add(key, row["created_at"], {"sent": True, "handled": True, "failed": False}.get(row["status"]))
    finally:
        conn.close()
    out: dict[str, list[dict]] = {}
    for key in ("scout", "analysis", "alerts", "digest", "replies"):
        rows = []
        for n in range(days):
            day = (first + timedelta(days=n)).isoformat()
            counts = tally.get(key, {}).get(day, {"ok": 0, "failed": 0})
            state = "none" if not counts["ok"] + counts["failed"] else "fail" if not counts["ok"] else "mixed" if counts["failed"] else "ok"
            rows.append({"day": day, "state": state, **counts})
        out[key] = rows
    return out
