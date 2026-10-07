"""Built-in schedule for Scout.

When Jobs -> Settings -> Scout schedule is on, each enabled saved search runs
at set times of day (``run_times``, default 12:30 and 18:30, just after the
morning and afternoon waves of new job ads) in the search country's own clock
and working week (Qatar: Sunday to Thursday, UTC+3), or
in ``interval`` mode every ``schedule_hours``. Weekends get one Saturday run by
default, and after a run that found 0-1 new jobs the next run that same day
is skipped. One search is started per minute at most, so a long list never
hits a job site all at once. No AI is involved, so the schedule costs no tokens.

The same loop drives Job OS email (``notify.tick``): new-match alerts, the
daily digest, and checking for reply commands.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)
TICK_SECONDS = 60
_started = False
_start_lock = threading.Lock()


QUIET_RUN = 1  # a run that found at most this many new jobs is a quiet one


def _zone(scout: dict):
    try:
        return ZoneInfo(scout.get("timezone") or "Asia/Kuala_Lumpur")
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def next_slot(after: float, scout: dict, *, skip_same_day: bool = False, country: str = "") -> int | None:
    """The first scheduled time strictly after ``after`` (epoch seconds), in the
    search country's own clock and working week (``indeed.CLOCKS``; else the
    ``timezone`` setting and Monday to Friday). Off days get one run on
    Saturday when ``weekend`` is "saturday" (both Malaysia and Qatar rest then,
    and Qatar also on Friday). ``skip_same_day`` passes over the rest of the
    local day of ``after``."""
    from api.job_os.indeed import MON_FRI, clock

    own = clock(country)
    zone = ZoneInfo(own[0]) if own else _zone(scout)
    workdays = own[1] if own else MON_FRI
    times = sorted({tuple(int(p) for p in t.split(":")) for t in scout.get("run_times") or ["12:30", "18:30"]})
    weekend = scout.get("weekend") or "saturday"
    start = datetime.fromtimestamp(after, zone)
    for offset in range(15):
        day = (start + timedelta(days=offset)).date()
        if day.weekday() not in workdays:
            if weekend == "none" or (weekend == "saturday" and day.weekday() != 5):
                continue
            day_times = times[:1] if weekend == "saturday" else times
        else:
            day_times = times
        if skip_same_day and day == start.date():
            continue
        for hour, minute in day_times:
            slot = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone).timestamp()
            if slot > after:
                return int(slot)
    return None


def next_run_at(search: dict, settings: dict, *, now: float | None = None) -> int | None:
    """When the schedule will next run ``search`` (epoch seconds), or None."""
    scout = settings.get("scout") or {}
    if not scout.get("enabled") or not search.get("enabled"):
        return None
    last = search.get("last_run_at") or 0
    if scout.get("schedule_mode") == "interval":
        return int(last + int(scout.get("schedule_hours") or 6) * 3600) if last else int(time.time() if now is None else now)
    country = search.get("country") or ""
    if not last:
        return next_slot(time.time() if now is None else now, scout, country=country)
    quiet = bool(scout.get("quiet_skip")) and search.get("last_new") is not None and search["last_new"] <= QUIET_RUN
    return next_slot(last, scout, skip_same_day=quiet, country=country)


def tick(*, now: float | None = None, start: Callable | None = None) -> str | None:
    """Start the most overdue search, if any. Returns the started search id."""
    from api.job_os import scout
    from api.job_os.settings import load_settings

    settings = load_settings()
    if not (settings.get("scout") or {}).get("enabled"):
        return None
    now = time.time() if now is None else now
    active = {run["search_id"] for run in scout.list_runs(limit=50) if run["status"] in scout.ACTIVE_STATES}
    due = [(next_run_at(s, settings, now=now), s["id"]) for s in scout.list_searches()
           if s["enabled"] and s["id"] not in active]
    due = sorted((when, sid) for when, sid in due if when is not None and when <= now)
    if not due:
        return None
    search_id = due[0][1]
    (start or scout.start_discovery)(search_id, trigger="schedule")
    return search_id


def _loop() -> None:
    while True:
        time.sleep(TICK_SECONDS)
        try:
            tick()
        except Exception:  # the schedule must never take the server down
            logger.debug("Job OS scheduler tick failed", exc_info=True)
        try:
            from api.job_os import notify

            notify.tick()
        except Exception:
            logger.debug("Job OS notification tick failed", exc_info=True)


def start_scheduler() -> bool:
    """Start the background schedule once per process. Returns True if started now."""
    global _started
    with _start_lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_loop, name="job-os-scheduler", daemon=True).start()
    return True
