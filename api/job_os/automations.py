"""What Job OS does on its own, and when (Settings -> Automations).

Read-only summary of the background work driven by the scheduler loop
(scheduler.py): Scout runs, Luna analysis, match alerts, the daily digest,
reply checks and auto-apply. Nothing here starts work; it reports settings
and the last/next run times so the schedule is visible in one place.
"""

from __future__ import annotations

import time

from api import mailer


def _next_digest(hour: int, last: str | None, now: float) -> int:
    local = time.localtime(now)
    today = time.strftime("%Y-%m-%d", local)
    start = time.mktime(local[:3] + (hour, 0, 0, 0, 0, -1))
    if last == today:
        start += 86400  # today's has gone out
    elif now >= start:
        start = now + 60  # due now: the next scheduler tick sends it
    return int(start)


def summary(*, now: float | None = None) -> list[dict]:
    from api.job_os import autoapply, notify, scheduler, scout
    from api.job_os.analysis import queue_counts
    from api.job_os.settings import load_settings

    now = time.time() if now is None else now
    settings = load_settings()
    n, auto = settings["notifications"], settings["auto_apply"]
    email = bool(n["email_enabled"] and n["to_address"] and all(mailer.credentials()))
    state = notify.load_state()
    searches = [s for s in scout.list_searches() if s["enabled"]]
    next_scout = min((t for t in (scheduler.next_run_at(s, settings) for s in searches) if t), default=None)
    last_scout = max((s.get("last_run_at") or 0 for s in searches), default=0) or None
    queue = queue_counts()
    return [
        {"key": "scout", "label": "Scout searches", "on": bool(settings["scout"]["enabled"] and searches),
         "schedule": f"Every {settings['scout']['schedule_hours']} h · {len(searches)} saved search{'es' if len(searches) != 1 else ''}",
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
        {"key": "auto_apply", "label": "Auto-apply", "on": bool(auto["enabled"]),
         "schedule": f"Up to {auto['daily_cap']} a day · fit {auto['min_fit_score']}+", "last": None, "next": None,
         "detail": f"{autoapply.submitted_today(now)} sent today" if auto["enabled"] else "",
         "off_reason": "" if auto["enabled"] else "Turn it on under Auto-apply", "view": "applications"},
    ]
