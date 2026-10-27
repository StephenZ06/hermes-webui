"""Closing dates, expiry and stale postings.

A job's closing date (``jobs.deadline``) comes from the job site, the posting's
structured data (``validThrough``) or Luna's reading of the text. Once a day,
in your Scout time zone:

- a job not yet applied for whose closing date has passed moves to Closed as
  ``expired`` (logged with the date; drag it back if it is still open);
- a closing date within ``CLOSING_SOON_DAYS`` flags the job "Closes in N days";
- a job with no closing date is never expired by date.

With Firecrawl set up, Favorite and Ready-to-apply postings are also read again
once a week: a 410, a "no longer available" page, or a redirect to a page that
is no longer a single posting means expired. A 404, 403 or timeout means
"couldn't check" and changes nothing (the ``expired`` versus ``unreachable``
rule). A posting more than ``STALE_DAYS`` old gets an age label, a signal and
never a veto.

Adapted from ai-job-search (github.com/ai-job-search-dev/ai-job-search, MIT).
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.paths import job_os_state_dir
from api.job_os.repository import list_jobs, parse_deadline

logger = logging.getLogger(__name__)
CLOSING_SOON_DAYS = 7
STALE_DAYS = 30
RECHECK_DAYS = 7
RECHECK_PER_DAY = 5
# Not applied for yet: these can expire by date.
OPEN = (JobStatus.DISCOVERED, JobStatus.SCRAPED, JobStatus.ANALYZED, JobStatus.SHORTLISTED,
        JobStatus.RESUME_READY, JobStatus.APPLICATION_READY)
# Read again each week: the jobs you mean to apply for.
RECHECKED = (JobStatus.SHORTLISTED, JobStatus.RESUME_READY, JobStatus.APPLICATION_READY)
_CLOSED_TEXT = re.compile(
    r"no longer (available|accepting|active|open)|position (has been|is) (filled|closed)|job (has )?expired|"
    r"this job (is|has been) (closed|removed)|applications? (are |is )?(now )?closed|job not found|"
    r"lowongan (ini )?(sudah )?(ditutup|tidak tersedia)", re.I)


def today(now: float | None = None) -> date:
    """Today on the person's clock (Settings → Scout schedule → time zone)."""
    from api.job_os.settings import load_settings

    try:
        zone = ZoneInfo(load_settings()["scout"]["timezone"])
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        zone = ZoneInfo("UTC")
    return datetime.fromtimestamp(time.time() if now is None else now, zone).date()


def days_left(deadline: str, on: date) -> int | None:
    value = parse_deadline(deadline)
    return (date.fromisoformat(value) - on).days if value else None


def closing_label(days: int) -> str:
    return "Closes today" if days == 0 else "Closes tomorrow" if days == 1 else f"Closes in {days} days"


def age_days(posted_at: str, on: date) -> int | None:
    value = parse_deadline(posted_at)  # the same YYYY-MM-DD reading
    return (on - date.fromisoformat(value)).days if value else None


def _event(conn, job_id: str, event_type: str, payload: dict, now: int) -> None:
    conn.execute("INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                 (str(uuid.uuid4()), job_id, event_type, json.dumps(payload, separators=(",", ":")), now))


def _expire(job, payload: dict) -> bool:
    from api.job_os.lifecycle import move_job

    try:
        move_job(job.id, JobStatus.EXPIRED, expected_revision=job.revision, payload=payload)
        return True
    except Exception:  # the job changed meanwhile; the next sweep looks again
        logger.debug("expiry skipped for %s", job.id, exc_info=True)
        return False


def sweep(*, on: date | None = None) -> dict:
    """Expire open jobs whose closing date has passed. Returns counts."""
    on = on or today()
    expired = closing = 0
    for job in list_jobs():
        if job.status not in OPEN:
            continue
        left = days_left(job.deadline, on)
        if left is None:
            continue  # no date: never expired by date
        if left < 0:
            expired += _expire(job, {"by": "deadline", "deadline": job.deadline})
        elif left <= CLOSING_SOON_DAYS:
            closing += 1
    return {"expired": expired, "closing": closing}


def classify(page: dict, url: str) -> str:
    """``expired``, ``open`` or ``unknown`` for one re-read posting page."""
    from api.job_os.extract import extract_job_posting

    status = page.get("status")
    if status == 410:
        return "expired"
    if status is not None and status != 200:
        return "unknown"  # 404, 403, 5xx: couldn't check, change nothing
    html = str(page.get("html") or "")
    if not html:
        return "unknown"
    if extract_job_posting(html, url):
        return "open"
    text = re.sub(r"<[^>]+>", " ", html)
    if _CLOSED_TEXT.search(text):
        return "expired"
    final = str(page.get("final_url") or "")
    if final and final.rstrip("/") != url.rstrip("/"):
        return "expired"  # sent on to a listing page: the posting is gone
    return "unknown"


def _last_checks(conn) -> dict[str, int]:
    return {r["job_id"]: r["at"] for r in conn.execute(
        "SELECT job_id, MAX(created_at) AS at FROM job_events WHERE event_type='posting_checked' GROUP BY job_id")}


def recheck(*, client=None, now: float | None = None, limit: int = RECHECK_PER_DAY) -> dict:
    """Read again the Favorite and Ready-to-apply postings not checked this week."""
    now = int(time.time() if now is None else now)
    conn = connect_job_os()
    try:
        last = _last_checks(conn)
    finally:
        conn.close()
    due = [job for job in list_jobs() if job.status in RECHECKED and now - last.get(job.id, 0) >= RECHECK_DAYS * 86400]
    due.sort(key=lambda job: last.get(job.id, 0))
    out = {"checked": 0, "expired": 0, "unknown": 0}
    if not due:
        return out
    if client is None:
        from api.job_os.scout import _default_client

        client = _default_client()
    from api.job_os.network_policy import validate_external_job_url

    for job in due[:limit]:
        try:
            url = validate_external_job_url(job.canonical_url)
            result = classify(client.scrape(url), url)
        except Exception:
            result = "unknown"
        conn = connect_job_os()
        try:
            _event(conn, job.id, "posting_checked", {"result": result}, now)
            conn.commit()
        finally:
            conn.close()
        out["checked"] += 1
        if result == "expired" and _expire(job, {"by": "recheck"}):
            out["expired"] += 1
        elif result == "unknown":
            out["unknown"] += 1
    return out


def _state_path():
    return job_os_state_dir() / "expiry.json"


def _firecrawl_ready() -> bool:
    try:
        from api.job_os.firecrawl import resolve_firecrawl_config
        from api.job_os.settings import load_settings

        override = (load_settings().get("firecrawl") or {}).get("api_url") or None
        return bool(resolve_firecrawl_config(override).base_url)
    except Exception:
        return False


def tick(*, now: float | None = None, recheck_with: Callable | None = None) -> bool:
    """Run the day's sweep once per local day. Returns whether it ran."""
    on = today(now)
    path = _state_path()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if state.get("last_sweep") == on.isoformat():
        return False
    path.write_text(json.dumps({**state, "last_sweep": on.isoformat()}), encoding="utf-8")
    sweep(on=on)
    if recheck_with is not None or _firecrawl_ready():
        try:
            (recheck_with or recheck)(now=now)
        except Exception:
            logger.debug("posting re-check failed", exc_info=True)
    return True
