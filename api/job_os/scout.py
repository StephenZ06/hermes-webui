"""Scout: saved searches and durable Firecrawl discovery runs.

A run is persisted before any external work and after every page, so the
browser can show live progress by polling, a cancel takes effect between
pages, and a WebUI restart mid-run leaves a terminal ``interrupted`` run
instead of one that claims to be running forever. Firecrawl never owns state:
it is asked for search results and pages; Job OS decides what is a posting
and what is saved.

Flow: queued -> searching (keyword queries, optionally limited to sites) ->
scraping (each candidate page; postings read from their JSON-LD) ->
completed | cancelled | failed | interrupted.
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

from api.job_os.db import connect_job_os
from api.job_os.extract import ATS_HOSTS, extract_job_posting, job_links_from_page
from api.job_os.models import DuplicateJobError, JobStatus, JobValidationError
from api.job_os.network_policy import UnsafeJobUrl, validate_external_job_url
from api.job_os.repository import create_job, normalize_job_input

ACTIVE_STATES = ("queued", "searching", "scraping")
TERMINAL_STATES = ("completed", "cancelled", "failed", "interrupted")
DEFAULT_SITES = ("boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com",
                 "apply.workable.com", "jobs.smartrecruiters.com")
MAX_ERRORS = 20
_EMPTY_COUNTS = {"queries": 0, "found": 0, "candidates": 0, "scraped": 0, "saved": 0,
                 "duplicates": 0, "not_postings": 0, "filtered": 0, "unsafe": 0, "errors": 0}
# Runs with a live worker in this process (threaded or inline).
_LIVE_RUNS: set[str] = set()
_LOCK = threading.Lock()
_DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")


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


def _site(value: str) -> str:
    """A bare domain (searched with ``site:``) or a full careers-page URL (scraped for job links)."""
    text = value.strip()
    if "://" in text:
        parts = urlsplit(text)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ScoutError(f"Not a usable site: {value[:80]}")
        return text.rstrip("/")
    domain = text.lower().strip("/").removeprefix("www.")
    if not _DOMAIN.match(domain):
        raise ScoutError(f"Not a usable site: {value[:80]}")
    return domain


def normalize_search(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ScoutError("search must be an object")
    name = str(payload.get("name") or "").strip()
    keywords = str(payload.get("keywords") or "").strip()
    if not keywords or len(keywords) > 200:
        raise ScoutError("Keywords are required (up to 200 characters)")
    if len(name) > 80:
        raise ScoutError("Name is too long")
    sites = [_site(s) for s in _split(payload.get("sites"), limit=20, field="sites")]
    return {
        "name": name or keywords[:80],
        "keywords": keywords,
        "locations": _split(payload.get("locations"), limit=10, field="locations"),
        "sites": sites,
        "remote_only": bool(payload.get("remote_only")),
        "enabled": bool(payload.get("enabled", True)),
    }


def _search_row(row) -> dict:
    return {
        "id": row["id"], "name": row["name"], "keywords": row["keywords"],
        "locations": json.loads(row["locations"] or "[]"), "sites": json.loads(row["sites"] or "[]"),
        "remote_only": bool(row["remote_only"]), "enabled": bool(row["enabled"]),
        "revision": row["revision"], "last_run_at": row["last_run_at"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def list_searches() -> list[dict]:
    conn = connect_job_os()
    try:
        return [_search_row(r) for r in conn.execute("SELECT * FROM searches ORDER BY created_at ASC, id ASC")]
    finally:
        conn.close()


def get_search(search_id: str) -> dict | None:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
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
            "INSERT INTO searches (id, name, keywords, locations, sites, remote_only, enabled, revision, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (search_id, data["name"], data["keywords"], json.dumps(data["locations"]), json.dumps(data["sites"]),
             int(data["remote_only"]), int(data["enabled"]), now, now))
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
            "UPDATE searches SET name=?, keywords=?, locations=?, sites=?, remote_only=?, enabled=?,"
            " revision=revision+1, updated_at=? WHERE id=? AND revision=?",
            (data["name"], data["keywords"], json.dumps(data["locations"]), json.dumps(data["sites"]),
             int(data["remote_only"]), int(data["enabled"]), int(time.time()), search_id, expected_revision))
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

    override = (load_settings().get("firecrawl") or {}).get("api_url") or None
    return FirecrawlClient(resolve_firecrawl_config(override))


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


def _queries(search: dict) -> list[str]:
    base = search["keywords"] + (" remote" if search["remote_only"] else "")
    locations = search["locations"] or [""]
    domains = [s for s in search["sites"] if "://" not in s] or list(DEFAULT_SITES)
    out = []
    for location in locations:
        query = f"{base} {location}".strip()
        out.extend(f"site:{domain} {query}" for domain in domains)
    return out


def _source_for(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    for name, ats in (("greenhouse", "greenhouse.io"), ("lever", "lever.co"), ("ashby", "ashbyhq.com"),
                      ("workable", "workable.com"), ("smartrecruiters", "smartrecruiters.com")):
        if host == ats or host.endswith("." + ats):
            return name
    return host.removeprefix("www.")[:60] or "web"


def _known_urls() -> set[str]:
    conn = connect_job_os()
    try:
        return {row[0] for row in conn.execute("SELECT canonical_url FROM jobs")}
    finally:
        conn.close()


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

        max_results = int(load_settings()["scout"]["max_results_per_search"])
        client = client_factory()
        save("searching", "Searching job sites", started_at=int(time.time()))

        candidates: list[str] = []
        seen: set[str] = set()
        known = _known_urls()

        def offer(url: str) -> None:
            counts["found"] += 1
            try:
                safe = validate_external_job_url(url)
            except UnsafeJobUrl:
                counts["unsafe"] += 1
                return
            try:
                canonical = normalize_job_input({"title": "x", "canonical_url": safe}).canonical_url
            except JobValidationError:
                counts["unsafe"] += 1
                return
            if canonical in seen:
                return
            seen.add(canonical)
            if canonical in known:
                counts["duplicates"] += 1
                return
            candidates.append(safe)

        from api.job_os.firecrawl import FirecrawlError

        for page_url in [s for s in search["sites"] if "://" in s]:
            if _cancel_requested(run_id):
                finish("cancelled", "Cancelled")
                return
            try:
                validate_external_job_url(page_url)
                page = client.scrape(page_url, links=True)
                for link in job_links_from_page(page["links"], page_url):
                    offer(link)
            except (UnsafeJobUrl, FirecrawlError) as error:
                note_error(page_url, error)
            save(detail=f"Checked careers page {urlsplit(page_url).hostname}")

        for query in _queries(search):
            if _cancel_requested(run_id):
                finish("cancelled", "Cancelled")
                return
            if len(candidates) >= max_results:
                break
            counts["queries"] += 1
            try:
                for result in client.search(query, limit=min(10, max_results)):
                    offer(result["url"])
            except FirecrawlError as error:
                note_error(query, error)
            save(detail=f"Searched {counts['queries']} of {len(_queries(search))} queries")

        candidates = candidates[:max_results]
        counts["candidates"] = len(candidates)
        if not candidates and counts["errors"] and counts["queries"] and counts["errors"] >= counts["queries"]:
            finish("failed", "Firecrawl could not search; check Settings → Connections")
            return
        save("scraping", f"Reading {len(candidates)} pages")

        for index, url in enumerate(candidates, start=1):
            if _cancel_requested(run_id):
                finish("cancelled", "Cancelled")
                return
            try:
                safe = validate_external_job_url(url)  # resolve again at the moment of use
                page = client.scrape(safe)
                counts["scraped"] += 1
                posting = extract_job_posting(page["html"], safe)
                if posting is None:
                    counts["not_postings"] += 1
                elif search["remote_only"] and posting["workplace"] != "remote":
                    counts["filtered"] += 1
                else:
                    job = replace(
                        normalize_job_input({**posting, "source": _source_for(safe)}),
                        description=posting["description"], salary_text=posting["salary_text"],
                        employment_type=posting["employment_type"], workplace=posting["workplace"],
                        posted_at=posting["posted_at"], search_id=search["id"], run_id=run_id)
                    record = create_job(job, status=JobStatus.SCRAPED)
                    counts["saved"] += 1
                    new_ids.append(record.id)
            except DuplicateJobError:
                counts["duplicates"] += 1
            except (UnsafeJobUrl, FirecrawlError, JobValidationError) as error:
                note_error(urlsplit(url).hostname or url, error)
            save(detail=f"Read {index} of {len(candidates)} pages · {counts['saved']} new")

        conn = connect_job_os()
        try:
            conn.execute("UPDATE searches SET last_run_at=? WHERE id=?", (int(time.time()), search["id"]))
            conn.commit()
        finally:
            conn.close()
        finish("completed", f"{counts['saved']} new job{'s' if counts['saved'] != 1 else ''}")
    except Exception as error:  # a crashed worker must still leave a terminal run
        note_error("scout", type(error).__name__)
        try:
            finish("failed", "Scout stopped on an unexpected error")
        except Exception:
            pass
    finally:
        with _LOCK:
            _LIVE_RUNS.discard(run_id)
