"""Closing dates, expiry and stale postings.

A job's closing date (``jobs.deadline``) comes from the job site, the posting's
structured data (``validThrough``) or Luna's reading of the text. Once a day,
in your Scout time zone:

- a job not yet applied for whose closing date has passed moves to Closed as
  ``expired`` (logged with the date; drag it back if it is still open);
- a closing date within ``CLOSING_SOON_DAYS`` flags the job "Closes in N days";
- a job with no closing date is never expired by date.

Every job not yet applied for is also read again once a day (through
Firecrawl when it is set up, otherwise straight from the job site): a 410, a
"no longer available" page, or a redirect to a page that is no longer a single
posting means expired, and the job moves to Closed with that reason. A 404,
403, a sign-in or bot-check page, or a timeout means "couldn't check" and
changes nothing (the ``expired`` versus ``unreachable`` rule). A posting more
than ``STALE_DAYS`` old gets an age label, a signal and never a veto.

Adapted from ai-job-search (github.com/ai-job-search-dev/ai-job-search, MIT).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
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
RECHECK_DAYS = 1
RECHECK_PER_DAY = 200
# Not applied for yet: these can expire by date, and their postings are read
# again each day. Once applied for, a job's outcome comes from the employer.
OPEN = (JobStatus.DISCOVERED, JobStatus.SCRAPED, JobStatus.ANALYZED, JobStatus.SHORTLISTED,
        JobStatus.RESUME_READY, JobStatus.APPLICATION_READY)
RECHECKED = OPEN
# A redirect to one of these is a wall in front of the posting, not its end.
_WALL = re.compile(r"authwall|login|log-in|signin|sign-in|signup|captcha|challenge|checkpoint|cf_chl|consent", re.I)
_WALL_TEXT = re.compile(r"just a moment\.\.\.|verify you are (a )?human|are you a robot|enable javascript and cookies|"
                        r"unusual traffic|access denied", re.I)
_CLOSED_TEXT = re.compile(
    r"no longer (available|accepting( applications)?|active|open)|position (has been|is) (filled|closed)|job (has )?expired|"
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


# LinkedIn job pages answer a script with a sign-in wall or 429; the guest
# page for the same job id is what its public job search reads.
_LINKEDIN_JOB = re.compile(r"^https://(?:[a-z]{2,3}\.|www\.)?linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d{6,})(?:[/?#]|$)", re.I)
_GUEST_PAGE = re.compile(r"^https://www\.linkedin\.com/jobs-guest/jobs/api/jobPosting/\d+$")


def page_url(url: str) -> str:
    """The address to read a posting from: LinkedIn's guest page, else the posting."""
    match = _LINKEDIN_JOB.match(url)
    return f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{match.group(1)}" if match else url


def _same_page(url: str) -> tuple[str, str, str]:
    """A page's identity, ignoring the scheme, a ``www.`` and a trailing slash."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    return host, parts.path.rstrip("/"), parts.query


def classify(page: dict, url: str) -> str:
    """``expired``, ``open`` or ``unknown`` for one re-read posting page."""
    return classify_with_reason(page, url)[0]


def classify_with_reason(page: dict, url: str) -> tuple[str, str]:
    """``(result, reason)``: the reason says, in words, why a posting is closed."""
    from api.job_os.extract import extract_job_posting

    status = page.get("status")
    if status == 410:
        return "expired", "The job site says the posting has been removed"
    if status is not None and status != 200:
        return "unknown", ""  # 404, 403, 5xx: couldn't check, change nothing
    html = str(page.get("html") or "")
    if not html:
        return "unknown", ""
    final = str(page.get("final_url") or "")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    if (final and _WALL.search(urllib.parse.urlsplit(final).path + "?" + urllib.parse.urlsplit(final).query)) or _WALL_TEXT.search(text[:4000]):
        return "unknown", ""  # a sign-in or bot check stood in front of it
    if _GUEST_PAGE.match(url):
        # LinkedIn's guest page has no structured data: a closed posting says
        # so in its top card, an open one shows the card alone. The phrase is
        # only looked for above the description, which can say anything.
        if "top-card-layout__title" not in html:
            return "unknown", ""
        top = html.split("show-more-less-html", 1)[0]
        closed = _CLOSED_TEXT.search(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", top)))
        if closed:
            return "expired", f"The posting says “{closed.group(0).strip()}”"
        return "open", ""
    if extract_job_posting(html, url):
        return "open", ""
    closed = _CLOSED_TEXT.search(text)
    if closed:
        return "expired", f"The posting says “{closed.group(0).strip()}”"
    if final and urllib.parse.urlsplit(url).path.strip("/") and _same_page(final) != _same_page(url):
        return "expired", "The posting link now leads to another page"  # sent on to a listing page
    return "unknown", ""


# Read straight from the job site when Firecrawl is not set up: each redirect
# is followed by hand so every hop passes the same public-address check.
MAX_REDIRECTS = 5
MAX_BYTES = 2_000_000
FETCH_TIMEOUT = 15
SAME_HOST_GAP_S = 2.0
# LinkedIn turns a quicker reader away with 429s.
_HOST_GAPS = {"www.linkedin.com": 8.0}


def host_gap(host: str) -> float:
    return _HOST_GAPS.get(host, SAME_HOST_GAP_S)
_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/141.0 Safari/537.36")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DirectPageClient:
    """``scrape(url)`` -> ``{"status", "html", "final_url"}`` without Firecrawl."""

    def __init__(self, *, opener=None, validate=None, sleep=time.sleep, clock=time.monotonic):
        self._opener = opener or urllib.request.build_opener(_NoRedirect)
        self._validate = validate
        self._sleep, self._clock = sleep, clock
        self._last: dict[str, float] = {}

    def _pause(self, url: str) -> None:
        host = urllib.parse.urlsplit(url).hostname or ""
        if host in self._last:
            wait = host_gap(host) - (self._clock() - self._last[host])
            if wait > 0:
                self._sleep(wait)
        self._last[host] = self._clock()

    def scrape(self, url: str) -> dict:
        validate = self._validate
        if validate is None:
            from api.job_os.network_policy import validate_external_job_url as validate
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            current = validate(current)
            self._pause(current)
            request = urllib.request.Request(current, headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*;q=0.8",
                                                               "Accept-Language": "en"})
            try:
                with self._opener.open(request, timeout=FETCH_TIMEOUT) as response:  # noqa: S310 - validated public URL
                    body = response.read(MAX_BYTES)
                    charset = response.headers.get_content_charset() or "utf-8"
                    return {"status": getattr(response, "status", 200), "html": body.decode(charset, "replace"), "final_url": current}
            except urllib.error.HTTPError as error:
                location = error.headers.get("Location") if error.headers else None
                if error.code in (301, 302, 303, 307, 308) and location:
                    current = urllib.parse.urljoin(current, location)
                    continue
                return {"status": error.code, "html": "", "final_url": current}
        return {"status": None, "html": "", "final_url": current}


def closed_reason(payload: dict) -> str:
    """Why a job was moved to Closed, in words, from its status-change event."""
    by = (payload or {}).get("by")
    if by == "deadline":
        return f"Its closing date ({payload.get('deadline', '')}) passed"
    if by == "recheck":
        return payload.get("reason") or "The posting is no longer open"
    return ""


def closed_reasons(job_ids) -> dict[str, str]:
    """``{job_id: reason}`` for jobs this module moved to Closed."""
    ids = [str(i) for i in job_ids]
    if not ids:
        return {}
    conn = connect_job_os()
    try:
        out: dict[str, str] = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            rows = conn.execute(
                f"SELECT job_id, payload_json FROM job_events WHERE event_type='status_changed' AND job_id IN ({','.join('?' * len(chunk))}) "
                "ORDER BY created_at", chunk).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except ValueError:
                    continue
                if payload.get("to") == JobStatus.EXPIRED.value:
                    out[row["job_id"]] = closed_reason(payload)
                elif row["job_id"] in out:
                    out.pop(row["job_id"])  # moved on again since
        return {k: v for k, v in out.items() if v}
    finally:
        conn.close()


def _last_checks(conn) -> dict[str, int]:
    return {r["job_id"]: r["at"] for r in conn.execute(
        "SELECT job_id, MAX(created_at) AS at FROM job_events WHERE event_type='posting_checked' GROUP BY job_id")}


# ---- Re-reading through Apify ---------------------------------------------------
# Indeed and SEEK turn a direct reader away (401/403), so their postings are
# re-read by an Apify actor that takes posting URLs, once a day in one run per
# site. A posting the actor marks expired is closed. One it stops returning is
# only closed after MISSING_RUNS runs in a row that did return other postings,
# since a single missing record could be the actor's fault.
MISSING_RUNS = 3
# Left untouched each month so Scout's own Apify searches keep working.
APIFY_RESERVE_USD = 2.0
# Postings per actor run, so one run finishes inside Apify's synchronous limit.
APIFY_CHUNK = 20


@dataclass(frozen=True)
class Reread:
    site: str
    actor: str
    posting_id: Callable[[str], str]     # posting URL -> id, "" when not this site's
    actor_url: Callable[[str, str], str]  # (posting URL, id) -> the URL the actor reads
    make_input: Callable[[list[str]], dict]
    item_id: Callable[[dict], str]
    item_expired: Callable[[dict], bool]
    start_usd: float
    usd_per_posting: float


_INDEED_POSTING = re.compile(r"^https://(?:[a-z]{2,12}\.)?indeed\.com/viewjob\?jk=([0-9A-Za-z]{1,40})$")
_SEEK_POSTING = re.compile(r"^https://(?:www\.seek\.com\.au|www\.seek\.co\.nz|(au|nz)\.seek\.com)/job/(\d{5,})(?:[/?#]|$)")


def _seek_id(url: str) -> str:
    match = _SEEK_POSTING.match(url)
    return match.group(2) if match else ""


def _seek_url(url: str, posting_id: str) -> str:
    # The actor was tried with SEEK's older addresses, which still serve the posting.
    host = "www.seek.co.nz" if ".co.nz/" in url or "//nz.seek.com/" in url else "www.seek.com.au"
    return f"https://{host}/job/{posting_id}"


REREADS = (
    Reread("Indeed", "misceres/indeed-scraper",
           lambda url: (_INDEED_POSTING.match(url) or [None, ""])[1], lambda url, _id: url,
           lambda urls: {"startUrls": [{"url": u} for u in urls], "maxItemsPerSearch": 1, "saveOnlyUniqueItems": True},
           lambda item: str(item.get("id") or ""), lambda item: item.get("isExpired") is True,
           0.0, 0.006),
    Reread("SEEK", "blackfalcondata/seek-scraper", _seek_id, _seek_url,
           lambda urls: {"startUrls": urls, "maxResults": len(urls), "compact": True, "includeDetails": False},
           lambda item: str(item.get("seekJobId") or ""), lambda item: False,
           0.01, 0.002),
)


def _apify():
    from api.job_os import apify

    return apify


def _missing_streak(conn, job_id: str) -> int:
    streak = 0
    for row in conn.execute("SELECT payload_json FROM job_events WHERE job_id=? AND event_type='posting_checked' "
                            "ORDER BY created_at DESC LIMIT ?", (job_id, MISSING_RUNS)):
        if json.loads(row["payload_json"] or "{}").get("result") != "missing":
            break
        streak += 1
    return streak


def _reread_with_apify(site: Reread, jobs: list, apify) -> dict[str, tuple[str, str]]:
    """job id -> (result, reason) for one site's postings, from one actor run."""
    unknown = {job.id: ("unknown", "") for job in jobs}
    headroom = apify.monthly_headroom_usd()
    cost = site.start_usd + site.usd_per_posting * len(jobs)
    if headroom is None or headroom - cost < APIFY_RESERVE_USD:
        logger.info("posting re-check: %s skipped, Apify headroom %s for a $%.3f run", site.site, headroom, cost)
        return unknown
    ids = {job.id: site.posting_id(job.canonical_url) for job in jobs}
    try:
        items = apify.run_actor(site.actor, site.make_input([site.actor_url(job.canonical_url, ids[job.id]) for job in jobs]))
    except Exception:
        logger.warning("posting re-check: %s run failed", site.site, exc_info=True)
        return unknown
    found = {site.item_id(item): item for item in items}
    found.pop("", None)
    if not found:
        return unknown  # a run that returns nothing proves nothing
    out = {}
    for job in jobs:
        item = found.get(ids[job.id])
        if item is None:
            out[job.id] = ("missing", "")
        elif site.item_expired(item):
            out[job.id] = ("expired", f"{site.site} marks the posting as expired")
        else:
            out[job.id] = ("open", "")
    return out


def _record(job, result: str, reason: str, now: int, out: dict) -> None:
    conn = connect_job_os()
    try:
        if result == "missing" and _missing_streak(conn, job.id) >= MISSING_RUNS - 1:
            site = next(s.site for s in REREADS if s.posting_id(job.canonical_url))
            result, reason = "expired", f"{site} no longer shows the posting (checked {MISSING_RUNS} days running)"
            recorded = "missing"
        else:
            recorded = result
        _event(conn, job.id, "posting_checked", {"result": recorded}, now)
        conn.commit()
    finally:
        conn.close()
    out["checked"] += 1
    if result == "expired" and _expire(job, {"by": "recheck", "reason": reason}):
        out["expired"] += 1
    elif result != "expired" and result != "open":
        out["unknown"] += 1


def recheck(*, client=None, now: float | None = None, limit: int = RECHECK_PER_DAY) -> dict:
    """Read again the postings of jobs not yet applied for, not checked today."""
    now = int(time.time() if now is None else now)
    conn = connect_job_os()
    try:
        last = _last_checks(conn)
    finally:
        conn.close()
    # A day less an hour, so a check that ran a little later yesterday is due again.
    due = [job for job in list_jobs() if job.status in RECHECKED and job.canonical_url
           and now - last.get(job.id, 0) >= RECHECK_DAYS * 86400 - 3600]
    due.sort(key=lambda job: last.get(job.id, 0))
    due = due[:limit]
    out = {"checked": 0, "expired": 0, "unknown": 0}
    if not due:
        return out
    apify = _apify()
    direct = due
    if apify.token():
        direct = []
        batches: dict[str, list] = {}
        for job in due:
            site = next((s for s in REREADS if s.posting_id(job.canonical_url)), None)
            if site:
                batches.setdefault(site.site, []).append(job)
            else:
                direct.append(job)
        for site in REREADS:
            jobs = batches.get(site.site) or []
            for start in range(0, len(jobs), APIFY_CHUNK):
                chunk = jobs[start:start + APIFY_CHUNK]
                results = _reread_with_apify(site, chunk, apify)
                for job in chunk:
                    _record(job, *results[job.id], now, out)
    if direct and client is None:
        if _firecrawl_ready():
            from api.job_os.scout import _default_client

            client = _default_client()
        else:
            client = DirectPageClient()
    from api.job_os.network_policy import validate_external_job_url

    for job in direct:
        try:
            url = validate_external_job_url(page_url(job.canonical_url))
            result, reason = classify_with_reason(client.scrape(url), url)
        except Exception:
            result, reason = "unknown", ""
        _record(job, result, reason, now, out)
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
    if recheck_with is not None:
        try:
            recheck_with(now=now)
        except Exception:
            logger.debug("posting re-check failed", exc_info=True)
    else:
        _recheck_in_background(now)
    return True


# Reading every posting takes minutes (a pause between pages on one site), so
# it runs beside the scheduler instead of holding up Scout and the emails.
_RECHECK_LOCK = threading.Lock()


def _recheck_in_background(now: float | None) -> None:
    def run():
        if not _RECHECK_LOCK.acquire(blocking=False):
            return  # yesterday's is somehow still going
        try:
            recheck(now=now)
        except Exception:
            logger.debug("posting re-check failed", exc_info=True)
        finally:
            _RECHECK_LOCK.release()

    threading.Thread(target=run, name="job-os-posting-recheck", daemon=True).start()
