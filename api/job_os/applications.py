"""Pipeline board, 'I applied' recording, notes, attention and the funnel.

The board shows every job in one column per stage, from new finds to closed,
and can be narrowed to one source (``indeed`` from Scout, ``manual`` from the
tracker). Scout's finds carry their job site (``apify.SITES``); the board can also
narrow to one of those. Marking a job applied walks the canonical lifecycle path to
``submitted`` (every step lands in the event log) and records an
``application_submitted`` event; a job applied for without a tailored resume
goes straight to ``submitted``. Outcomes after that (screening, interview,
offer, rejected, ...) use the normal status transitions.
"""

from __future__ import annotations

import json
import time
import uuid

from api.job_os.db import connect_job_os
from api.job_os.lifecycle import transition_job
from api.job_os.models import JobStatus
from api.job_os.repository import get_job, list_jobs

FOLLOW_UP_DAYS = 7
COLUMNS = (
    ("new", "New", ("discovered", "scraped", "analyzed")),
    ("shortlisted", "Shortlisted", ("shortlisted",)),
    ("resume", "Resume", ("tailoring", "resume_ready")),
    ("ready", "Ready to apply", ("application_ready", "awaiting_approval", "applying")),
    ("applied", "Applied", ("submitted",)),
    ("interviewing", "Interviewing", ("screening", "interviewing")),
    ("offers", "Offer", ("offer", "offer_accepted", "offer_declined")),
    ("closed", "Closed", ("rejected", "withdrawn", "no_response", "closed", "skipped", "expired")),
)
def _sources() -> tuple[str, ...]:
    from api.job_os.apify import SITES

    return (*SITES, "manual")


SOURCES = _sources()
# What a person can move a card to by hand (tailoring and the internal apply
# steps have their own actions). "submitted" goes through mark_applied.
MOVES = (("shortlisted", "Shortlisted"), ("submitted", "Applied"), ("screening", "Screening"),
         ("interviewing", "Interviewing"), ("offer", "Offer"), ("offer_accepted", "Offer accepted"),
         ("offer_declined", "Offer declined"), ("rejected", "Rejected"), ("no_response", "No response"),
         ("withdrawn", "Withdrawn"), ("skipped", "Skipped"))
# Applying without a tailored resume: these go straight to submitted.
_DIRECT_APPLY = (JobStatus.DISCOVERED, JobStatus.SCRAPED, JobStatus.ANALYZED, JobStatus.SHORTLISTED)
_PATH = [JobStatus.SHORTLISTED, JobStatus.TAILORING, JobStatus.RESUME_READY, JobStatus.APPLICATION_READY,
         JobStatus.AWAITING_APPROVAL, JobStatus.APPLYING, JobStatus.SUBMITTED]


class ApplicationError(ValueError):
    """The requested application step is not possible (HTTP 400)."""


def _event(conn, job_id: str, event_type: str, payload: dict) -> None:
    conn.execute("INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                 (str(uuid.uuid4()), job_id, event_type, json.dumps(payload, separators=(",", ":")), int(time.time())))


def mark_applied(job_id: str, *, method: str = "manual", note: str = "") -> dict:
    """Record that the application was sent: from any stage before it, with or
    without a tailored resume (a tailoring job must finish first)."""
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status == JobStatus.SUBMITTED:
        return {"job_id": job_id, "status": job.status.value}
    if job.status in _DIRECT_APPLY:
        job = transition_job(job_id, JobStatus.SUBMITTED, expected_revision=job.revision)
    elif job.status in _PATH and _PATH.index(job.status) >= _PATH.index(JobStatus.RESUME_READY):
        for target in _PATH[_PATH.index(job.status) + 1:]:
            job = transition_job(job_id, target, expected_revision=job.revision)
    else:
        raise ApplicationError("This job can't be marked applied from its current stage.")
    conn = connect_job_os()
    try:
        _event(conn, job_id, "application_submitted", {"method": "manual",
                                                       "note": str(note or "")[:500]})
        conn.commit()
    finally:
        conn.close()
    return {"job_id": job_id, "status": job.status.value}


def add_note(job_id: str, text: str) -> dict:
    if get_job(job_id) is None:
        raise KeyError(job_id)
    text = str(text or "").strip()
    if not text:
        raise ApplicationError("A note needs some text.")
    conn = connect_job_os()
    try:
        _event(conn, job_id, "note", {"text": text[:2000]})
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def timeline(job_id: str) -> list[dict]:
    conn = connect_job_os()
    try:
        rows = conn.execute("SELECT event_type, payload_json, created_at FROM job_events WHERE job_id=? ORDER BY created_at, rowid",
                            (job_id,)).fetchall()
        return [{"type": r["event_type"], "data": json.loads(r["payload_json"] or "{}"), "at": r["created_at"]} for r in rows]
    finally:
        conn.close()


def _signals() -> tuple[dict, dict, dict, dict]:
    """Per job: applied event, last status change, document states, analysis state."""
    conn = connect_job_os()
    try:
        applied = {r["job_id"]: {"at": r["created_at"], **json.loads(r["payload_json"] or "{}")}
                   for r in conn.execute("SELECT job_id, payload_json, created_at FROM job_events WHERE event_type='application_submitted'")}
        changed = {r["job_id"]: r["at"] for r in conn.execute(
            "SELECT job_id, MAX(created_at) AS at FROM job_events WHERE event_type='status_changed' GROUP BY job_id")}
        docs: dict[str, list[str]] = {}
        for r in conn.execute("SELECT d.job_id, d.status FROM job_documents d WHERE d.created_at = (SELECT MAX(created_at)"
                              " FROM job_documents WHERE job_id=d.job_id AND kind=d.kind)"):
            docs.setdefault(r["job_id"], []).append(r["status"])
        analyses = {r["job_id"]: {"status": r["status"], "fit_score": r["fit_score"], "verdict": r["verdict"]}
                    for r in conn.execute("SELECT job_id, status, fit_score, verdict FROM job_analyses")}
        return applied, changed, docs, {"analyses": analyses}
    finally:
        conn.close()


def attention_reasons(job, docs: list[str], extra: dict, changed_at: int | None, now: int) -> list[str]:
    reasons = []
    status = job.status.value
    if status in ("resume_ready", "application_ready") and "needs_review" in docs:
        reasons.append("A tailored document has numbers to check")
    if "failed" in docs and status == "shortlisted":
        reasons.append("Tailoring failed")
    if status in ("submitted", "screening", "interviewing") and changed_at and now - changed_at > FOLLOW_UP_DAYS * 86400:
        reasons.append(f"No update in {int((now - changed_at) // 86400)} days — follow up?")
    return reasons


def moves_for(status: JobStatus) -> list[list[str]]:
    """The stages a card can be moved to from ``status``, as [value, label]."""
    from api.job_os.lifecycle import _ALLOWED_TRANSITIONS

    allowed = {s.value for s in _ALLOWED_TRANSITIONS.get(status, ())}
    if status in _DIRECT_APPLY or status in (JobStatus.RESUME_READY, JobStatus.APPLICATION_READY):
        allowed.add("submitted")
    return [[value, label] for value, label in MOVES if value in allowed]


def board(source: str | None = None) -> dict:
    """Every job in a column per stage, newest first; ``source`` narrows it to
    Scout's Indeed finds or the manual tracker. ``sources`` counts both."""
    if source is not None and source not in SOURCES:
        raise ApplicationError("Unknown source")
    applied, changed, docs, extra = _signals()
    now = int(time.time())
    by_status = {status: key for key, _label, statuses in COLUMNS for status in statuses}
    columns = {key: [] for key, _label, _statuses in COLUMNS}
    sources = {name: 0 for name in SOURCES}
    for job in list_jobs():
        key = by_status.get(job.status.value)
        if key is None:
            continue
        kind = job.source if job.source in SOURCES else "indeed"  # Scout's older finds were all Indeed
        sources[kind] += 1
        if source is not None and kind != source:
            continue
        card = {"id": job.id, "title": job.title, "company": job.company, "location": job.location,
                "country": job.country, "workplace": job.workplace, "salary_text": job.salary_text,
                "employment_type": job.employment_type, "source": kind, "status": job.status.value,
                "revision": job.revision, "canonical_url": job.canonical_url, "posted_at": job.posted_at,
                "has_description": bool(job.description), "analysis": extra["analyses"].get(job.id),
                "attention": attention_reasons(job, docs.get(job.id, []), extra, changed.get(job.id), now),
                "applied": applied.get(job.id), "updated_at": job.updated_at, "created_at": job.created_at,
                "moves": moves_for(job.status)}
        columns[key].append(card)
    for cards in columns.values():
        cards.sort(key=lambda c: -(c["updated_at"] or 0))
    return {"columns": [{"key": k, "label": label, "jobs": columns[k]} for k, label, _ in COLUMNS],
            "sources": {"all": sum(sources.values()), **sources}}


def funnel() -> list[dict]:
    """How far jobs got: found -> analysed -> shortlisted -> applied -> interview -> offer."""
    jobs = list_jobs()
    _applied, _changed, _docs, extra = _signals()
    later = {s.value for s in _PATH[_PATH.index(JobStatus.SHORTLISTED):]} | {
        "screening", "interviewing", "offer", "offer_accepted", "offer_declined", "rejected", "withdrawn", "no_response"}
    applied = {"submitted", "screening", "interviewing", "offer", "offer_accepted", "offer_declined", "rejected", "no_response"}
    interviewed = {"interviewing", "offer", "offer_accepted", "offer_declined"}
    offers = {"offer", "offer_accepted", "offer_declined"}
    analysed = sum(1 for j in jobs if (extra["analyses"].get(j.id) or {}).get("status") == "done")
    return [
        {"key": "found", "label": "Found", "count": len(jobs)},
        {"key": "analysed", "label": "Analysed", "count": analysed},
        {"key": "shortlisted", "label": "Shortlisted", "count": sum(j.status.value in later for j in jobs)},
        {"key": "applied", "label": "Applied", "count": sum(j.status.value in applied for j in jobs)},
        {"key": "interviewing", "label": "Interviewing", "count": sum(j.status.value in interviewed for j in jobs)},
        {"key": "offers", "label": "Offers", "count": sum(j.status.value in offers for j in jobs)},
    ]
