"""Built-in schedule for Scout.

When Jobs -> Settings -> Scout schedule is on, each enabled saved search runs
again once ``schedule_hours`` have passed since its last run. One search is
started per minute at most, so a long list never hits Firecrawl all at once.
No AI is involved, so the schedule costs no tokens.

The same loop drives Job OS email (``notify.tick``): new-match alerts, the
daily digest, and checking for reply commands.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)
TICK_SECONDS = 60
_started = False
_start_lock = threading.Lock()


def next_run_at(search: dict, settings: dict) -> int | None:
    """When the schedule will next run ``search`` (epoch seconds), or None."""
    scout = settings.get("scout") or {}
    if not scout.get("enabled") or not search.get("enabled"):
        return None
    last = search.get("last_run_at") or 0
    return int(last + int(scout.get("schedule_hours") or 6) * 3600) if last else int(time.time())


def tick(*, now: float | None = None, start: Callable | None = None) -> str | None:
    """Start the most overdue search, if any. Returns the started search id."""
    from api.job_os import scout
    from api.job_os.settings import load_settings

    settings = load_settings()
    if not (settings.get("scout") or {}).get("enabled"):
        return None
    now = time.time() if now is None else now
    active = {run["search_id"] for run in scout.list_runs(limit=50) if run["status"] in scout.ACTIVE_STATES}
    due = [(next_run_at(s, settings), s["id"]) for s in scout.list_searches()
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
            from api.job_os import autoapply, notify

            notify.tick()
            autoapply.tick()
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
