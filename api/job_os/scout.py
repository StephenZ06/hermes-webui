"""Scout: saved searches and durable Firecrawl discovery runs.

A run is persisted before any external work and after every page, so the
browser can show live progress by polling, a cancel takes effect between
pages, and a WebUI restart mid-run leaves a terminal ``interrupted`` run
instead of one that claims to be running forever. Firecrawl never owns state:
it is asked for search results and pages; Job OS decides what is a posting
and what is saved.

Scout searches Indeed only: each saved search names an Indeed country site
and, optionally, cities. A run opens the country's results page for every
city (``indeed.search_url``), collects the postings it links to, and reads
each one. When the results page itself is refused, the run falls back to a
web search restricted to that Indeed site.

Flow: queued -> searching (results pages) -> scraping (each posting; read
from its JSON-LD) -> completed | cancelled | failed | interrupted.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import replace
from typing import Callable
from urllib.parse import urlsplit

from api.job_os import apify, indeed
from api.job_os.db import connect_job_os
from api.job_os.extract import (extract_job_posting, indeed_posting_links, indeed_posting_url, is_indeed,
                                 looks_like_single_posting)
from api.job_os.models import DuplicateJobError, JobStatus, JobValidationError
from api.job_os.network_policy import UnsafeJobUrl, validate_external_job_url
from api.job_os.repository import create_job, normalize_job_input

ACTIVE_STATES = ("queued", "searching", "scraping")
TERMINAL_STATES = ("completed", "cancelled", "failed", "interrupted")
# Indeed refuses a reader that asks for pages back to back (observed: every
# request failed after a burst, and succeeded again 5s apart after a pause).
INDEED_GAP_S = 5.0
MAX_INDEED_RESULT_PAGES = 4  # pages found by the fallback web search
PAGES_PER_LOCATION = 3  # results pages read per city (10 postings each)
# Once Indeed starts refusing it keeps refusing for minutes (observed), so this
# many failed postings in a row end the run instead of waiting on the rest.
REFUSALS_BEFORE_STOP = 4
_sleep = time.sleep
_apify_run = apify.run_actor  # tests replace it
_monotonic = time.monotonic
MAX_ERRORS = 20
MAX_LOCATIONS = 10
# Job sites a search can cover (apify.SITES). Indeed can also be read directly;
# the others only through Apify (LinkedIn refuses a self-hosted reader outright).
JOB_SITES = tuple(apify.SITES)
_EMPTY_COUNTS = {"queries": 0, "found": 0, "candidates": 0, "scraped": 0, "saved": 0,
                 "duplicates": 0, "not_postings": 0, "filtered": 0, "blocked": 0, "unsafe": 0, "closed": 0, "errors": 0}
_COMPANY_SUFFIX = re.compile(r"\b(inc|incorporated|ltd|limited|llc|plc|gmbh|ag|sa|bv|co|corp|corporation|company|pty)\b\.?", re.I)
SIMILAR_WINDOW = 60 * 86400


def company_key(name: object) -> str:
    """'Acme, Inc.' and 'ACME' compare equal."""
    text = _COMPANY_SUFFIX.sub(" ", str(name or "").lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _title_key(title: object) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).split())


def similar_job_exists(company: object, title: object, *, now: float | None = None) -> bool:
    """A recent job with the same employer and title, whatever site it came from."""
    ckey, tkey = company_key(company), _title_key(title)
    if not ckey or not tkey:
        return False
    since = int((time.time() if now is None else now) - SIMILAR_WINDOW)
    conn = connect_job_os()
    try:
        rows = conn.execute("SELECT company, title FROM jobs WHERE created_at>=?", (since,)).fetchall()
    finally:
        conn.close()
    return any(company_key(r["company"]) == ckey and _title_key(r["title"]) == tkey for r in rows)


# Runs with a live worker in this process (threaded or inline).
_LIVE_RUNS: set[str] = set()
_LOCK = threading.Lock()


class ScoutError(ValueError):
    """Invalid input for a search or run (HTTP 400)."""


class ScoutConflict(ValueError):
    """Acting on an older revision (HTTP 409)."""


# ---- saved searches --------------------------------------------------------

def _split(value, *, limit: int, field: str) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[\n,]", value)
    elif isinstance(value, list):
        items = [str(v) for v in value]
    elif value in (None, ""):
        items = []
    else:
        raise ScoutError(f"{field} must be a list")
    out = [item.strip() for item in items if item and item.strip()]
    if len(out) > limit:
        raise ScoutError(f"{field}: at most {limit} entries")
    return list(dict.fromkeys(out))


MAX_QUERIES = 5


def _queries_of(keywords: str) -> list[str]:
    """Comma-separated job titles: each is searched on its own."""
    return list(dict.fromkeys(q.strip() for q in str(keywords or "").split(",") if q.strip()))


_WORD = re.compile(r"[a-z0-9+#]+")


def title_matches(title: str, phrases: list[str]) -> bool:
    """True when the title has every word of at least one phrase (any order);
    an empty filter keeps everything."""
    if not phrases:
        return True
    words = set(_WORD.findall(str(title or "").lower()))
    return any(set(_WORD.findall(p)) <= words for p in phrases if _WORD.findall(p))


def normalize_search(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ScoutError("search must be an object")
    name = str(payload.get("name") or "").strip()
    keywords = str(payload.get("keywords") or "").strip()
    if not keywords or len(keywords) > 200:
        raise ScoutError("Keywords are required (up to 200 characters)")
    if len(_queries_of(keywords)) > MAX_QUERIES:
        raise ScoutError(f"At most {MAX_QUERIES} job titles per search (comma-separated)")
    title_filter = [p.lower() for p in _split(payload.get("title_filter"), limit=10, field="Title must contain")]
    if any(len(p) > 60 for p in title_filter):
        raise ScoutError("A title phrase is too long")
    if len(name) > 80:
        raise ScoutError("Name is too long")
    country = str(payload.get("country") or "").strip().lower()
    if country not in indeed.COUNTRIES:
        raise ScoutError("Choose the Indeed country to search")
    try:
        posted = int(payload.get("posted_within_days") or 0)
    except (TypeError, ValueError):
        posted = -1
    if posted not in indeed.POSTED_WITHIN_DAYS:
        raise ScoutError("Date posted must be any time, or the last 1, 3, 7 or 14 days")
    locations = _split(payload.get("locations"), limit=MAX_LOCATIONS, field="locations")
    if any(len(location) > 80 for location in locations):
        raise ScoutError("A location is too long")
    sites = [str(s).strip().lower() for s in _split(payload.get("sites"), limit=len(JOB_SITES), field="sites")] or ["indeed"]
    unknown = [s for s in sites if s not in JOB_SITES]
    if unknown:
        raise ScoutError(f"Unknown job site: {unknown[0][:40]}. Choose {' or '.join(apify.SITE_NAMES.values())}.")
    elsewhere = [apify.SITE_NAMES[s] for s in sites if not apify.covers(s, country)]
    if elsewhere:
        raise ScoutError(f"{elsewhere[0]} doesn't cover {indeed.country_name(country)}")
    return {
        "name": name or keywords[:80],
        "keywords": keywords,
        "country": country,
        "locations": locations,
        "sites": [s for s in JOB_SITES if s in sites],
        "title_filter": title_filter,
        "posted_within_days": posted,
        "remote_only": bool(payload.get("remote_only")),
        "enabled": bool(payload.get("enabled", True)),
    }


def _search_row(row) -> dict:
    return {
        "id": row["id"], "name": row["name"], "keywords": row["keywords"],
        "locations": json.loads(row["locations"] or "[]"),
        # Older rows hold the retired application-tracking domains here; they read as Indeed.
        "sites": [s for s in JOB_SITES if s in (json.loads(row["sites"] or "[]") or [])] or ["indeed"],
        "title_filter": json.loads(row["title_filter"] or "[]"),
        "queries": _queries_of(row["keywords"]),
        "country": row["country"], "country_name": indeed.country_name(row["country"]),
        "posted_within_days": row["posted_within_days"],
        "remote_only": bool(row["remote_only"]), "enabled": bool(row["enabled"]),
        "revision": row["revision"], "last_run_at": row["last_run_at"],
        # New jobs saved by the latest finished run (the schedule skips a run after a quiet one).
        "last_new": json.loads(row["last_counts"]).get("saved", 0) if row["last_counts"] else None,
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


_SEARCH_COLUMNS = ("s.*, (SELECT r.counts_json FROM discovery_runs r WHERE r.search_id = s.id AND r.status = 'completed'"
                   " ORDER BY r.created_at DESC LIMIT 1) AS last_counts")


def list_searches() -> list[dict]:
    conn = connect_job_os()
    try:
        return [_search_row(r) for r in conn.execute(f"SELECT {_SEARCH_COLUMNS} FROM searches s ORDER BY created_at ASC, id ASC")]
    finally:
        conn.close()


def get_search(search_id: str) -> dict | None:
    conn = connect_job_os()
    try:
        row = conn.execute(f"SELECT {_SEARCH_COLUMNS} FROM searches s WHERE id = ?", (search_id,)).fetchone()
        return _search_row(row) if row else None
    finally:
        conn.close()


def create_search(payload: dict) -> dict:
    data = normalize_search(payload)
    now = int(time.time())
    search_id = str(uuid.uuid4())
    conn = connect_job_os()
    try:
        conn.execute(
            "INSERT INTO searches (id, name, keywords, locations, sites, title_filter, country, posted_within_days, remote_only,"
            " enabled, revision, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (search_id, data["name"], data["keywords"], json.dumps(data["locations"]), json.dumps(data["sites"]),
             json.dumps(data["title_filter"]), data["country"],
             data["posted_within_days"], int(data["remote_only"]), int(data["enabled"]), now, now))
        conn.commit()
    finally:
        conn.close()
    return get_search(search_id)


def update_search(search_id: str, payload: dict, *, expected_revision: int) -> dict:
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise ScoutError("expected_revision must be an integer")
    current = get_search(search_id)
    if current is None:
        raise KeyError(search_id)
    merged = {**current, **(payload if isinstance(payload, dict) else {})}
    data = normalize_search(merged)
    conn = connect_job_os()
    try:
        cur = conn.execute(
            "UPDATE searches SET name=?, keywords=?, locations=?, sites=?, title_filter=?, country=?, posted_within_days=?,"
            " remote_only=?, enabled=?, revision=revision+1, updated_at=? WHERE id=? AND revision=?",
            (data["name"], data["keywords"], json.dumps(data["locations"]), json.dumps(data["sites"]),
             json.dumps(data["title_filter"]), data["country"],
             data["posted_within_days"], int(data["remote_only"]), int(data["enabled"]), int(time.time()),
             search_id, expected_revision))
        conn.commit()
        if cur.rowcount != 1:
            raise ScoutConflict("This search changed in another tab; reload and try again")
    finally:
        conn.close()
    return get_search(search_id)


def delete_search(search_id: str) -> bool:
    """Remove a saved search. Jobs it found stay; an active run is cancelled first."""
    for run in list_runs(search_id=search_id, limit=5):
        if run["status"] in ACTIVE_STATES:
            cancel_run(run["id"])
    conn = connect_job_os()
    try:
        cur = conn.execute("DELETE FROM searches WHERE id = ?", (search_id,))
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


# ---- runs ------------------------------------------------------------------

def _run_row(row) -> dict:
    return {
        "id": row["id"], "search_id": row["search_id"], "status": row["status"],
        "stage_detail": row["stage_detail"], "trigger": row["trigger"], "revision": row["revision"],
        "counts": {**_EMPTY_COUNTS, **json.loads(row["counts_json"] or "{}")},
        "errors": json.loads(row["errors_json"] or "[]"),
        "new_job_ids": json.loads(row["new_job_ids_json"] or "[]"),
        "cancel_requested": bool(row["cancel_requested"]),
        "created_at": row["created_at"], "started_at": row["started_at"], "finished_at": row["finished_at"],
    }


def recover_interrupted_runs() -> int:
    """Mark runs that claim to be active but have no live worker as interrupted
    (the WebUI restarted mid-run). Returns how many were closed."""
    with _LOCK:
        alive = set(_LIVE_RUNS)
    conn = connect_job_os()
    try:
        rows = conn.execute(
            f"SELECT id, owner_pid FROM discovery_runs WHERE status IN ({','.join('?' * len(ACTIVE_STATES))})",
            ACTIVE_STATES).fetchall()
        stale = [r["id"] for r in rows if not (r["owner_pid"] == os.getpid() and r["id"] in alive)]
        now = int(time.time())
        for run_id in stale:
            conn.execute(
                "UPDATE discovery_runs SET status='interrupted', stage_detail='Hermes restarted during this run',"
                " revision=revision+1, finished_at=? WHERE id=?", (now, run_id))
        conn.commit()
        return len(stale)
    finally:
        conn.close()


def get_run(run_id: str) -> dict | None:
    recover_interrupted_runs()
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT * FROM discovery_runs WHERE id = ?", (run_id,)).fetchone()
        return _run_row(row) if row else None
    finally:
        conn.close()


def list_runs(*, search_id: str | None = None, limit: int = 20) -> list[dict]:
    recover_interrupted_runs()
    conn = connect_job_os()
    try:
        if search_id:
            rows = conn.execute("SELECT * FROM discovery_runs WHERE search_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                                (search_id, limit))
        else:
            rows = conn.execute("SELECT * FROM discovery_runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
        return [_run_row(r) for r in rows]
    finally:
        conn.close()


def _update_run(run_id: str, **fields) -> None:
    sets, values = [], []
    for key, value in fields.items():
        column = {"counts": "counts_json", "errors": "errors_json", "new_job_ids": "new_job_ids_json"}.get(key, key)
        sets.append(f"{column}=?")
        values.append(json.dumps(value) if key in ("counts", "errors", "new_job_ids") else value)
    conn = connect_job_os()
    try:
        conn.execute(f"UPDATE discovery_runs SET {', '.join(sets)}, revision=revision+1 WHERE id=?", (*values, run_id))
        conn.commit()
    finally:
        conn.close()


def _cancel_requested(run_id: str) -> bool:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT cancel_requested FROM discovery_runs WHERE id=?", (run_id,)).fetchone()
        return bool(row and row["cancel_requested"])
    finally:
        conn.close()


def cancel_run(run_id: str) -> dict:
    """Ask a run to stop. A queued run stops at once; a working one stops
    before its next page."""
    run = get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    if run["status"] in TERMINAL_STATES:
        return run
    conn = connect_job_os()
    try:
        conn.execute("UPDATE discovery_runs SET cancel_requested=1, revision=revision+1 WHERE id=?", (run_id,))
        if run["status"] == "queued":
            conn.execute("UPDATE discovery_runs SET status='cancelled', stage_detail='Cancelled', finished_at=?,"
                         " revision=revision+1 WHERE id=?", (int(time.time()), run_id))
        conn.commit()
    finally:
        conn.close()
    return get_run(run_id)


def _default_client():
    from api.job_os.firecrawl import FirecrawlClient, resolve_firecrawl_config
    from api.job_os.settings import load_settings

    from api.job_os.search_provider import make_scout_client

    override = (load_settings().get("firecrawl") or {}).get("api_url") or None
    return make_scout_client(FirecrawlClient(resolve_firecrawl_config(override)))


def start_discovery(search_id: str, *, trigger: str = "manual", idempotency_key: str | None = None,
                    client_factory: Callable | None = None, run_async: bool = True) -> dict:
    """Create (or return the already-active) run for a search and start it."""
    search = get_search(search_id)
    if search is None:
        raise KeyError(search_id)
    recover_interrupted_runs()
    key = str(idempotency_key or "").strip() or None
    conn = connect_job_os()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if key:
            row = conn.execute("SELECT * FROM discovery_runs WHERE idempotency_key=?", (key,)).fetchone()
            if row:
                conn.rollback()
                return _run_row(row)
        active = conn.execute(
            f"SELECT * FROM discovery_runs WHERE search_id=? AND status IN ({','.join('?' * len(ACTIVE_STATES))})"
            " ORDER BY created_at DESC LIMIT 1", (search_id, *ACTIVE_STATES)).fetchone()
        if active:
            conn.rollback()
            return _run_row(active)
        run_id = str(uuid.uuid4())
        now = int(time.time())
        conn.execute(
            "INSERT INTO discovery_runs (id, search_id, status, stage_detail, trigger, counts_json, idempotency_key,"
            " owner_pid, created_at) VALUES (?, ?, 'queued', 'Waiting to start', ?, ?, ?, ?, ?)",
            (run_id, search_id, trigger if trigger in ("manual", "schedule") else "manual",
             json.dumps(_EMPTY_COUNTS), key, os.getpid(), now))
        conn.commit()
    finally:
        conn.close()
    factory = client_factory or _default_client
    with _LOCK:
        _LIVE_RUNS.add(run_id)
    if run_async:
        threading.Thread(target=run_discovery, args=(run_id, factory), name=f"job-scout-{run_id[:8]}", daemon=True).start()
    else:
        run_discovery(run_id, factory)
    return get_run(run_id)


_LINKEDIN_ID = re.compile(r"^https://www\.linkedin\.com/jobs/view/(\d+)$")


# Job ids Scout already has, per site, read back from the stored links (for
# actors that can skip known jobs).
_KNOWN_ID = {"linkedin": _LINKEDIN_ID, "indeed": re.compile(r"^https://[a-z.]*indeed\.com/viewjob\?jk=(\w+)$")}


def _known_ids(site: str, known: set[str]) -> list[str]:
    pattern = _KNOWN_ID.get(site)
    return [m.group(1) for url in sorted(known) if pattern and (m := pattern.match(url))] if pattern else []


def _oldest_posted(days: int) -> str:
    """The earliest posted date (YYYY-MM-DD) a search's window allows; "" for any time."""
    if not days:
        return ""
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))


def _mark_ran(search_id: str) -> None:
    conn = connect_job_os()
    try:
        conn.execute("UPDATE searches SET last_run_at=? WHERE id=?", (int(time.time()), search_id))
        conn.commit()
    finally:
        conn.close()


def _is_remote(posting: dict) -> bool:
    """Indeed often leaves the workplace out of a posting's data; its title or place says it."""
    text = f"{posting.get('title', '')} {posting.get('location', '')}".lower()
    return posting.get("workplace") == "remote" or "remote" in text


def _known_urls() -> set[str]:
    conn = connect_job_os()
    try:
        return {row[0] for row in conn.execute("SELECT canonical_url FROM jobs")}
    finally:
        conn.close()


NOT_SCORED = " · not scored: upload your master resume in Resume Studio"


def _after_run(new_ids: list[str]) -> str:
    """Queue Luna analysis for new finds (Settings -> AI -> analyse automatically).
    Returns a note for the run's summary when the finds could not be scored."""
    if not new_ids:
        return ""
    try:
        from api.job_os import analysis
        from api.job_os.resume import load_resume
        from api.job_os.settings import load_settings

        if not load_settings()["ai"].get("auto_analyze", True):
            return ""
        if not load_resume():
            return NOT_SCORED  # scoring compares each job with the master resume
        analysis.request_analysis(new_ids)
    except Exception:  # analysis unavailable: finds are still saved
        pass
    return ""


def read_posting(url: str, client) -> tuple[str, dict | None]:
    """Read one posting URL: ("posting", fields) | ("closed", None) | ("not_posting", None)."""
    safe = validate_external_job_url(url)
    page = client.scrape(safe)
    if page.get("status") in (404, 410):
        return "closed", None
    posting = extract_job_posting(page["html"], safe)
    return ("posting", posting) if posting else ("not_posting", None)


def fill_job_details(job_id: str, *, client_factory: Callable | None = None) -> dict:
    """Read a manually imported job's page and store its details (discovered -> scraped)."""
    from api.job_os.lifecycle import transition_job
    from api.job_os.repository import get_job

    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    kind, posting = read_posting(job.canonical_url, (client_factory or _default_client)())
    if kind != "posting":
        raise ScoutError("That page is closed or is not a single job posting." if kind == "closed"
                         else "No job posting details were found on that page.")
    conn = connect_job_os()
    try:
        conn.execute(
            "UPDATE jobs SET description=?, salary_text=?, employment_type=?, workplace=?, posted_at=?,"
            " company=CASE WHEN company='' THEN ? ELSE company END, location=CASE WHEN location='' THEN ? ELSE location END,"
            " updated_at=? WHERE id=?",
            (posting["description"], posting["salary_text"], posting["employment_type"], posting["workplace"],
             posting["posted_at"], posting["company"], posting["location"], int(time.time()), job_id))
        conn.commit()
    finally:
        conn.close()
    current = get_job(job_id)
    if current.status == JobStatus.DISCOVERED:
        current = transition_job(job_id, JobStatus.SCRAPED, expected_revision=current.revision)
    _after_run([job_id])
    return {"job_id": job_id, "status": current.status.value}


class _PacedClient:
    """Spaces requests to Indeed INDEED_GAP_S apart (a manual job's own page is not held back)."""

    def __init__(self, client) -> None:
        self._client = client
        self._last_indeed: float | None = None

    def search(self, query: str, *, limit: int = 10) -> list[dict]:
        return self._client.search(query, limit=limit)

    def scrape(self, url: str, *, links: bool = False) -> dict:
        if is_indeed(url):
            if self._last_indeed is not None:
                wait = INDEED_GAP_S - (_monotonic() - self._last_indeed)
                if wait > 0:
                    _sleep(wait)
            try:
                return self._client.scrape(url, links=links)
            finally:
                self._last_indeed = _monotonic()
        return self._client.scrape(url, links=links)


def run_discovery(run_id: str, client_factory: Callable) -> None:
    """Do the work for one run. Never raises; every exit is a terminal state."""
    counts = dict(_EMPTY_COUNTS)
    errors: list[dict] = []
    new_ids: list[str] = []

    def note_error(where: str, message: str) -> None:
        counts["errors"] += 1
        if len(errors) < MAX_ERRORS:
            errors.append({"where": where[:120], "message": str(message)[:200]})

    def save(status: str | None = None, detail: str | None = None, **extra) -> None:
        fields = {"counts": counts, "errors": errors, "new_job_ids": new_ids, **extra}
        if status:
            fields["status"] = status
        if detail is not None:
            fields["stage_detail"] = detail[:200]
        _update_run(run_id, **fields)

    def finish(status: str, detail: str) -> None:
        save(status, detail, finished_at=int(time.time()))

    try:
        run = get_run(run_id)
        if run is None or run["status"] != "queued":
            return
        search = get_search(run["search_id"])
        if search is None:
            finish("failed", "The saved search was deleted")
            return
        from api.job_os.settings import load_settings

        all_settings = load_settings()
        scout_settings = all_settings["scout"]
        max_results = int(scout_settings["max_results_per_search"])
        blocked = {company_key(name) for name in scout_settings.get("blocked_companies") or []}
        client = _PacedClient(client_factory())
        if search["country"] not in indeed.COUNTRIES:
            finish("failed", "Choose the Indeed country for this search")
            return
        country_host = indeed.country_host(search["country"])
        apify_settings = all_settings["apify"]
        via_apify = bool(apify_settings["enabled"])
        if via_apify and not apify.token():
            finish("failed", "Apify is on but not connected; connect it in Settings → Apify or turn it off")
            return
        sites = search["sites"]
        # Sites other than Indeed are only reachable through Apify.
        apify_sites = list(sites) if via_apify else []
        unreachable = [s for s in sites if s != "indeed" and not via_apify]
        if unreachable and sites == unreachable:
            finish("failed", f"{' and '.join(apify.SITE_NAMES[s] for s in unreachable)} need Apify; connect it in Settings → Apify")
            return
        for site in unreachable:
            note_error(apify.SITE_NAMES[site], "skipped: needs Apify (Settings → Apify)")
        names = ", ".join(apify.SITE_NAMES[s] for s in sites if s not in unreachable)
        save("searching", f"Searching {names}{' through Apify' if via_apify else ''}", started_at=int(time.time()))

        candidates: list[str] = []
        stored_url: dict[str, str] = {}  # read URL -> the stable URL saved (Indeed)
        result_pages: list[str] = []  # Indeed results pages, opened for their postings
        seen: set[str] = set()
        known = _known_urls()

        def keep(posting: dict, canonical_url: str, source: str = "indeed") -> None:
            """Filter one read posting and save it (raises DuplicateJobError, JobValidationError)."""
            if not title_matches(posting.get("title"), search["title_filter"]):
                counts["filtered"] += 1  # the title doesn't have the words the search asks for
            elif search["remote_only"] and not _is_remote(posting):
                counts["filtered"] += 1
            elif company_key(posting.get("company")) in blocked:
                counts["blocked"] += 1
            elif similar_job_exists(posting.get("company"), posting.get("title")):
                counts["duplicates"] += 1  # the same role, posted again
            else:
                job = replace(
                    normalize_job_input({**posting, "canonical_url": canonical_url, "source": source,
                                        "country": indeed.country_name(search["country"])}),
                    search_id=search["id"], run_id=run_id)
                record = create_job(job, status=JobStatus.SCRAPED)
                counts["saved"] += 1
                new_ids.append(record.id)

        if apify_sites:
            # One actor run per site and city returns finished postings
            # (description included), so there is nothing left to read page by page.
            locations = search["locations"] or [""]
            country_name = indeed.country_name(search["country"])
            oldest = _oldest_posted(search["posted_within_days"])
            runs = failures = 0
            pairs = [(query, location) for query in search["queries"] for location in locations]
            for site in apify_sites:
                for query, location in pairs:
                    if _cancel_requested(run_id):
                        finish("cancelled", "Cancelled")
                        return
                    runs += 1
                    counts["queries"] += 1
                    keywords = query + (" remote" if search["remote_only"] else "")
                    label = f"{apify.SITE_NAMES[site]} “{query}”{' in ' + location if location else ''}"
                    save(detail=f"Apify is searching {label}")
                    context = {"country": search["country"], "country_name": country_name, "indeed_host": country_host,
                               "keywords": keywords, "location": location, "limit": int(apify_settings["results_per_city"]),
                               "posted_within_days": search["posted_within_days"]}
                    try:
                        reader = apify.adapter(site, apify_settings.get(f"{site}_actor") or apify.default_actor(site))
                        actor_input = reader.build(context)
                        # Where the actor can, it drops off-title and already-known jobs
                        # itself, so they are not charged; Scout filters the rest.
                        if reader.title_filter and search["title_filter"]:
                            actor_input[reader.title_filter] = list(search["title_filter"])
                        if reader.skip_known and (ids := _known_ids(site, known)):
                            actor_input[reader.skip_known] = ids[-apify.MAX_SKIP_IDS:]
                        if reader.incremental:
                            # One memory per search, title and place: later runs return only new postings.
                            actor_input.update({"incrementalMode": True, "emitUnchanged": False, "emitExpired": False,
                                                "stateKey": apify.state_key(search["id"][:8], site, query, location or "all")})
                        items = _apify_run(reader.actor, actor_input)
                    except apify.ApifyError as error:
                        failures += 1
                        note_error(f"Apify {label}", error)
                        continue
                    for item in items:
                        counts["found"] += 1
                        posting = reader.parse(item, context)
                        if posting is None:
                            counts["closed"] += 1  # expired, or not a usable record
                            continue
                        if oldest and posting["posted_at"] and posting["posted_at"] < oldest:
                            counts["filtered"] += 1  # older than the search's window
                            continue
                        canonical = normalize_job_input({"title": "x", "canonical_url": posting["canonical_url"]}).canonical_url
                        if canonical in seen:
                            continue
                        seen.add(canonical)
                        if canonical in known:
                            counts["duplicates"] += 1
                            continue
                        counts["scraped"] += 1
                        try:
                            keep(posting, canonical, site)
                        except DuplicateJobError:
                            counts["duplicates"] += 1
                        except JobValidationError as error:
                            note_error(apify.SITE_NAMES[site], error)
                    save(detail=f"Searched {label} · {counts['saved']} new")
            counts["candidates"] = counts["scraped"]
            if failures and failures == runs:
                finish("failed", f"Apify could not run: {errors[-1]['message'] if errors else 'unknown error'}")
                return
            _mark_ran(search["id"])
            note = _after_run(new_ids)
            finish("completed", f"{counts['saved']} new job{'s' if counts['saved'] != 1 else ''}{note}")
            return

        def offer(url: str) -> None:
            counts["found"] += 1
            try:
                safe = validate_external_job_url(url)
            except UnsafeJobUrl:
                counts["unsafe"] += 1
                return
            if (urlsplit(safe).hostname or "").lower() != country_host:
                counts["filtered"] += 1  # another site, or another country's Indeed
                return
            posting_link = looks_like_single_posting(safe)
            try:
                stable = indeed_posting_url(safe) if posting_link else safe
                canonical = normalize_job_input({"title": "x", "canonical_url": stable}).canonical_url
            except JobValidationError:
                counts["unsafe"] += 1
                return
            if canonical in seen:
                return
            seen.add(canonical)
            if not posting_link:
                result_pages.append(safe)  # a results page the web search found
                return
            if canonical in known:
                counts["duplicates"] += 1
                return
            stored_url[safe] = canonical
            candidates.append(safe)

        from api.job_os.firecrawl import FirecrawlError

        # Every title and city gets a fair share of the quota, so the first one
        # cannot crowd out the rest; leftovers from thin ones go to the next.
        # Each job title is searched in each city.
        pairs = [(query, location) for query in search["queries"] for location in (search["locations"] or [""])]
        for position, (query, location) in enumerate(pairs):
            keywords = query + (" remote" if search["remote_only"] else "")
            room = max_results - len(candidates)
            if room <= 0:
                break
            share = max(1, -(-room // (len(pairs) - position)))
            counts["queries"] += 1
            before = len(candidates)
            for page_number in range(PAGES_PER_LOCATION):
                if _cancel_requested(run_id):
                    finish("cancelled", "Cancelled")
                    return
                url = indeed.search_url(search["country"], keywords, location,
                                        posted_within_days=search["posted_within_days"], page=page_number)
                try:
                    page = client.scrape(url, links=True)
                except FirecrawlError as error:
                    note_error(f"{country_host} {location or 'results'}", error)
                    if page_number == 0:
                        # Indeed refused its results page; ask a web search for this site instead.
                        try:
                            for result in client.search(f"site:{country_host} {keywords} {location}".strip(), limit=10):
                                offer(result["url"])
                        except FirecrawlError as search_error:
                            note_error("web search", search_error)
                    break
                added = len(candidates)
                links = indeed_posting_links(page["links"], url)
                for link in links:
                    if len(candidates) - before >= share:
                        break
                    offer(link)
                # A short page is the last one; a page of only known postings means
                # Indeed is repeating itself.
                if len(links) < indeed.RESULTS_PER_PAGE or len(candidates) == added or len(candidates) - before >= share:
                    break
            save(detail=f"Searched {counts['queries']} of {len(pairs)} title and place combination{'s' if len(pairs) != 1 else ''}")

        for page_url in result_pages[:MAX_INDEED_RESULT_PAGES]:
            if _cancel_requested(run_id):
                finish("cancelled", "Cancelled")
                return
            if len(candidates) >= max_results:
                break
            try:
                validate_external_job_url(page_url)
                page = client.scrape(page_url, links=True)
                for link in indeed_posting_links(page["links"], page_url):
                    offer(link)
            except (UnsafeJobUrl, FirecrawlError) as error:
                note_error(urlsplit(page_url).hostname or page_url, error)
            save(detail="Opened an Indeed results page")

        candidates = candidates[:max_results]
        counts["candidates"] = len(candidates)
        if not candidates and counts["errors"] and counts["queries"] and counts["errors"] >= counts["queries"]:
            finish("failed", f"{country_host} could not be read; check Settings → Connections or try again later")
            return
        save("scraping", f"Reading {len(candidates)} postings")

        refused = 0
        for index, url in enumerate(candidates, start=1):
            if _cancel_requested(run_id):
                finish("cancelled", "Cancelled")
                return
            if refused >= REFUSALS_BEFORE_STOP:
                _mark_ran(search["id"])  # so the schedule waits its interval instead of retrying into the block
                saved = f"{counts['saved']} new job{'s' if counts['saved'] != 1 else ''}"
                note = _after_run(new_ids)
                finish("completed" if counts["saved"] else "failed",
                       f"{saved}{note} · Indeed is refusing requests right now; run again in a few minutes")
                return
            try:
                safe = validate_external_job_url(url)  # resolve again at the moment of use
                kind, posting = read_posting(safe, client)
                refused = 0
                counts["scraped"] += 1
                if kind == "closed":
                    counts["closed"] += 1  # the site no longer lists this posting
                    save(detail=f"Read {index} of {len(candidates)} postings · {counts['saved']} new")
                    continue
                if kind == "not_posting" or posting is None:
                    counts["not_postings"] += 1
                else:
                    keep(posting, stored_url.get(url, posting["canonical_url"]))
            except DuplicateJobError:
                counts["duplicates"] += 1
            except FirecrawlError as error:
                refused += 1
                note_error(urlsplit(url).hostname or url, error)
            except (UnsafeJobUrl, JobValidationError) as error:
                note_error(urlsplit(url).hostname or url, error)
            save(detail=f"Read {index} of {len(candidates)} postings · {counts['saved']} new")

        _mark_ran(search["id"])
        note = _after_run(new_ids)
        finish("completed", f"{counts['saved']} new job{'s' if counts['saved'] != 1 else ''}{note}")
    except Exception as error:  # a crashed worker must still leave a terminal run
        note_error("scout", type(error).__name__)
        try:
            finish("failed", "Scout stopped on an unexpected error")
        except Exception:
            pass
    finally:
        with _LOCK:
            _LIVE_RUNS.discard(run_id)
