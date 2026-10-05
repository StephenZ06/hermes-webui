"""Applications: the board, manual 'I applied' recording, notes, attention, funnel.

Marking a job applied walks the canonical lifecycle path (application_ready ->
awaiting_approval -> applying -> submitted) so every step is in the event
log, and records how it was sent (manual, auto) in an
``application_submitted`` event. Outcomes after that (screening, interview,
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
    ("preparing", "Preparing", ("shortlisted", "tailoring", "resume_ready")),
    ("ready", "Ready to apply", ("application_ready",)),
    ("attention", "Needs attention", ("awaiting_approval", "applying")),
    ("applied", "Applied", ("submitted",)),
    ("interviewing", "Interviewing", ("screening", "interviewing")),
    ("offers", "Offers", ("offer", "offer_accepted", "offer_declined")),
    ("closed", "Closed", ("rejected", "withdrawn", "no_response", "closed")),
)
_PATH = [JobStatus.SHORTLISTED, JobStatus.TAILORING, JobStatus.RESUME_READY, JobStatus.APPLICATION_READY,
         JobStatus.AWAITING_APPROVAL, JobStatus.APPLYING, JobStatus.SUBMITTED]


class ApplicationError(ValueError):
    """The requested application step is not possible (HTTP 400)."""


def _event(conn, job_id: str, event_type: str, payload: dict) -> None:
    conn.execute("INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                 (str(uuid.uuid4()), job_id, event_type, json.dumps(payload, separators=(",", ":")), int(time.time())))


def mark_applied(job_id: str, *, method: str = "manual", note: str = "") -> dict:
    """Record that the application was sent. Allowed from resume_ready onward."""
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status not in _PATH or _PATH.index(job.status) < _PATH.index(JobStatus.RESUME_READY):
        raise ApplicationError("Tailor a resume for this job before recording an application.")
    if job.status == JobStatus.SUBMITTED:
        return {"job_id": job_id, "status": job.status.value}
    for target in _PATH[_PATH.index(job.status) + 1:]:
        job = transition_job(job_id, target, expected_revision=job.revision)
    conn = connect_job_os()
    try:
        _event(conn, job_id, "application_submitted", {"method": method if method in ("manual", "auto") else "manual",
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
        stopped = {r["job_id"]: json.loads(r["payload_json"] or "{}").get("reason", "")
                   for r in conn.execute("SELECT job_id, payload_json FROM job_events e WHERE event_type='auto_apply_stopped'"
                                         " AND created_at = (SELECT MAX(created_at) FROM job_events WHERE job_id=e.job_id AND event_type='auto_apply_stopped')")}
        return applied, changed, docs, {"analyses": analyses, "stopped": stopped}
    finally:
        conn.close()


def attention_reasons(job, docs: list[str], extra: dict, changed_at: int | None, now: int) -> list[str]:
    reasons = []
    status = job.status.value
    if status == "awaiting_approval":
        reasons.append("Waiting for your approval to apply")
    if extra["stopped"].get(job.id) and status in ("application_ready", "awaiting_approval", "applying"):
        reasons.append(f"Auto-apply stopped: {extra['stopped'][job.id]}")
    if status in ("resume_ready", "application_ready") and "needs_review" in docs:
        reasons.append("A tailored document has numbers to check")
    if "failed" in docs and status == "shortlisted":
        reasons.append("Tailoring failed")
    if status in ("submitted", "screening") and changed_at and now - changed_at > FOLLOW_UP_DAYS * 86400:
        reasons.append(f"No update in {int((now - changed_at) // 86400)} days — follow up?")
    return reasons


def _auto_summary(run: dict | None) -> dict | None:
    if not run:
        return None
    result = run.get("result") or {}
    return {"mode": run["mode"], "status": run["status"], "reason": run["reason"], "finished_at": run["finished_at"],
            "screenshots": result.get("screenshots") or [], "filled": [f.get("label") for f in result.get("filled") or []]}


def board() -> dict:
    from api.job_os.autoapply import ats_of, latest_runs

    runs = latest_runs()
    applied, changed, docs, extra = _signals()
    now = int(time.time())
    by_status = {status: key for key, _label, statuses in COLUMNS for status in statuses}
    columns = {key: [] for key, _label, _statuses in COLUMNS}
    for job in list_jobs():
        key = by_status.get(job.status.value)
        if key is None:
            continue
        reasons = attention_reasons(job, docs.get(job.id, []), extra, changed.get(job.id), now)
        card = {"id": job.id, "title": job.title, "company": job.company, "location": job.location,
                "workplace": job.workplace, "salary_text": job.salary_text, "status": job.status.value,
                "revision": job.revision, "canonical_url": job.canonical_url,
                "analysis": extra["analyses"].get(job.id), "attention": reasons,
                "applied": applied.get(job.id), "updated_at": job.updated_at,
                "ats": ats_of(job.canonical_url), "auto": _auto_summary(runs.get(job.id))}
        target = "attention" if reasons and key in ("preparing", "ready") else key
        columns[target].append(card)
    for cards in columns.values():
        cards.sort(key=lambda c: -(c["updated_at"] or 0))
    return {"columns": [{"key": k, "label": label, "jobs": columns[k]} for k, label, _ in COLUMNS]}


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
