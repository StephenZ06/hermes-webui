"""Resume Studio tailoring: a job-specific resume and cover letter from the master resume.

Luna may rephrase, reorder, select and emphasise -- never invent. Two guards
back that up after generation:
- every number, year and percentage in the tailored text must appear in the
  master resume; anything else is flagged and the document is marked
  ``needs_review`` instead of ``ready``;
- an ATS-style keyword check reports which of the posting's must-haves the
  tailored resume mentions.

Flow: shortlisted -> tailoring -> resume_ready (failure returns the job to
shortlisted). One background worker, like analysis.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid

from api.job_os import llm
from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.repository import get_job

logger = logging.getLogger(__name__)
KINDS = ("resume", "cover_letter")
_lock = threading.Lock()
_worker: threading.Thread | None = None
_recovered = False

SYSTEM = (
    "You tailor a candidate's resume and write a cover letter for one job. Return ONLY JSON:\n"
    '{"resume_markdown": "<full tailored resume in Markdown>", "cover_letter": "<cover letter, plain text, 180-320 words>", '
    '"changes": [{"what": "<edit made>", "why": "<which posting need it serves>"}]}\n'
    "Hard rules: use ONLY facts in the master resume. You may rephrase, reorder, select, merge and emphasise; never add "
    "employers, titles, dates, numbers, degrees, certifications, tools or achievements that are not in it. Keep every "
    "date and number exactly as written. Mirror the posting's wording only where the resume genuinely supports it. "
    "Resume: Markdown with '# Name', a short contact line, '## ' sections, '- ' bullets; no tables, columns or images "
    "(application tracking systems parse plain structure best). Cover letter: specific to this company and role, "
    "no placeholders like [Company]. Up to 8 changes. " + llm.UNTRUSTED
)

_NUMBER = re.compile(r"(?<![\w.])(\d[\d,.]*\s?%?|[€$£]\s?\d[\d,.]*\s?[kKmM]?)(?![\w])")


class TailorError(ValueError):
    """Tailoring cannot be requested (HTTP 400)."""


def _numbers(text: str) -> set[str]:
    return {re.sub(r"[\s,]", "", m) for m in _NUMBER.findall(text or "")}


def unverified_numbers(tailored: str, master: str) -> list[str]:
    """Numbers in ``tailored`` that do not appear anywhere in ``master``."""
    known = _numbers(master)
    known_digits = {re.sub(r"\D", "", n) for n in known}
    out = []
    for raw in _NUMBER.findall(tailored or ""):
        token = re.sub(r"[\s,]", "", raw)
        if token in known or re.sub(r"\D", "", token) in known_digits:
            continue
        if token not in out:
            out.append(token)
    return out[:20]


def keyword_coverage(text: str, must_haves: list[str]) -> dict:
    """Which must-haves the tailored resume mentions (by their main words)."""
    lowered = (text or "").lower()
    stop = {"and", "or", "the", "with", "of", "in", "to", "a", "an", "for", "experience", "years", "strong", "knowledge",
            "ability", "skills", "using", "including", "plus", "such", "as", "on", "at", "+"}
    found, missing = [], []
    for need in must_haves or []:
        words = [w for w in re.findall(r"[a-z0-9+#.]{2,}", need.lower()) if w not in stop]
        hit = bool(words) and sum(w in lowered for w in words) >= max(1, (len(words) + 1) // 2)
        (found if hit else missing).append(need)
    total = len(found) + len(missing)
    return {"found": found, "missing": missing, "score": round(100 * len(found) / total) if total else None}


def _doc_row(row) -> dict:
    return {"id": row["id"], "job_id": row["job_id"], "kind": row["kind"], "status": row["status"],
            "content": row["content"], "notes": json.loads(row["notes_json"] or "{}"), "error": row["error"],
            "model": row["model"], "revision": row["revision"], "created_at": row["created_at"], "updated_at": row["updated_at"]}


def latest_documents(job_id: str) -> dict[str, dict]:
    conn = connect_job_os()
    try:
        out = {}
        for kind in KINDS:
            row = conn.execute("SELECT * FROM job_documents WHERE job_id=? AND kind=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                               (job_id, kind)).fetchone()
            if row:
                out[kind] = _doc_row(row)
        return out
    finally:
        conn.close()


def get_document(doc_id: str) -> dict | None:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT * FROM job_documents WHERE id=?", (doc_id,)).fetchone()
        return _doc_row(row) if row else None
    finally:
        conn.close()


def list_tailored() -> list[dict]:
    """Latest tailored resume per job, newest first, with its job's title/company."""
    conn = connect_job_os()
    try:
        rows = conn.execute(
            "SELECT d.*, j.title AS job_title, j.company AS job_company, j.status AS job_status FROM job_documents d"
            " JOIN jobs j ON j.id = d.job_id WHERE d.kind='resume' AND d.created_at = (SELECT MAX(created_at) FROM job_documents"
            " WHERE job_id=d.job_id AND kind='resume') ORDER BY d.updated_at DESC").fetchall()
        out = []
        for row in rows:
            doc = _doc_row(row)
            doc["content"] = ""  # list view: no bodies
            doc.update(job_title=row["job_title"], job_company=row["job_company"], job_status=row["job_status"])
            out.append(doc)
        return out
    finally:
        conn.close()


def request_tailoring(job_id: str, *, start_worker: bool = True) -> dict:
    """Start tailoring for a shortlisted (or analysed) job."""
    from api.job_os.lifecycle import transition_job
    from api.job_os.resume import load_resume

    if not load_resume():
        raise TailorError("Upload your master resume in Resume Studio first.")
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if not job.description:
        raise TailorError("This job has no description yet; fetch its details first.")
    if job.status == JobStatus.ANALYZED:
        job = transition_job(job_id, JobStatus.SHORTLISTED, expected_revision=job.revision)
    if job.status in (JobStatus.RESUME_READY, JobStatus.APPLICATION_READY):
        job = transition_job(job_id, JobStatus.SHORTLISTED, expected_revision=job.revision)  # re-tailor
    if job.status != JobStatus.SHORTLISTED:
        if job.status == JobStatus.TAILORING:
            return {"job_id": job_id, "status": "tailoring"}
        raise TailorError("Shortlist the job before tailoring.")
    transition_job(job_id, JobStatus.TAILORING, expected_revision=job.revision)
    now = int(time.time())
    conn = connect_job_os()
    try:
        for kind in KINDS:
            conn.execute("INSERT INTO job_documents (id, job_id, kind, status, created_at, updated_at) VALUES (?, ?, ?, 'pending', ?, ?)",
                         (str(uuid.uuid4()), job_id, kind, now, now))
        conn.commit()
    finally:
        conn.close()
    if start_worker:
        ensure_worker()
    return {"job_id": job_id, "status": "tailoring"}


def _contact_line(applicant: dict) -> str:
    parts = [applicant.get(k, "") for k in ("email", "phone", "location", "linkedin_url", "portfolio_url")]
    return " · ".join(p for p in parts if p)


def tailor_one(job_id: str) -> dict:
    from api.job_os.analysis import get_analysis
    from api.job_os.lifecycle import transition_job
    from api.job_os.resume import load_resume
    from api.job_os.settings import load_settings

    docs = latest_documents(job_id)
    resume_doc, letter_doc = docs.get("resume"), docs.get("cover_letter")

    def finish_job(target: JobStatus) -> None:
        current = get_job(job_id)
        if current is not None and current.status == JobStatus.TAILORING:
            try:
                transition_job(job_id, target, expected_revision=current.revision)
            except Exception:
                logger.debug("tailoring transition skipped", exc_info=True)

    def set_doc(doc, **fields):
        if not doc:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        conn = connect_job_os()
        try:
            conn.execute(f"UPDATE job_documents SET {sets}, revision=revision+1, updated_at=? WHERE id=?",
                         (*fields.values(), int(time.time()), doc["id"]))
            conn.commit()
        finally:
            conn.close()

    try:
        job, master = get_job(job_id), load_resume()
        if job is None or master is None:
            raise llm.LLMError("The job or the master resume is no longer available.")
        for doc in (resume_doc, letter_doc):
            set_doc(doc, status="running")
        analysis = get_analysis(job_id) or {}
        applicant = load_settings()["applicant"]
        posting = (f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n\n{job.description[:12000]}\n\n"
                   f"Must-haves identified: {json.dumps(analysis.get('must_haves') or [])}\n"
                   f"Gaps identified: {json.dumps(analysis.get('gaps') or [])}")
        contact = (f"Candidate name: {applicant.get('full_name')}\nContact line: {_contact_line(applicant)}"
                   if applicant.get("full_name") else "Use the name and contact details from the master resume.")
        data, model = llm.ask_json(SYSTEM, f"{contact}\n\n<<<POSTING\n{posting}\nPOSTING>>>\n\n<<<MASTER RESUME\n{master['text'][:16000]}\nMASTER RESUME>>>",
                                   max_tokens=6000)
        tailored = str(data.get("resume_markdown") or "").strip()
        letter = str(data.get("cover_letter") or "").strip()
        if len(tailored) < 200:
            raise llm.LLMError("The tailored resume came back empty.")
        allowed_numbers = master["text"] + " " + json.dumps(applicant)
        flags_resume = unverified_numbers(tailored, allowed_numbers)
        flags_letter = unverified_numbers(letter, allowed_numbers)
        changes = [{"what": str(c.get("what") or "")[:200], "why": str(c.get("why") or "")[:200]}
                   for c in (data.get("changes") or []) if isinstance(c, dict)][:8]
        coverage = keyword_coverage(tailored, analysis.get("must_haves") or [])
        set_doc(resume_doc, status="needs_review" if flags_resume else "ready", content=tailored[:30000], model=model, error="",
                notes_json=json.dumps({"changes": changes, "unverified": flags_resume, "coverage": coverage,
                                       "master_revision": master.get("revision")}))
        set_doc(letter_doc, status="needs_review" if flags_letter else "ready", content=letter[:8000], model=model, error="",
                notes_json=json.dumps({"unverified": flags_letter}))
        finish_job(JobStatus.RESUME_READY)
    except Exception as error:
        message = str(error) if isinstance(error, llm.LLMError) else f"Tailoring failed ({type(error).__name__})."
        for doc in (resume_doc, letter_doc):
            set_doc(doc, status="failed", error=message[:300])
        finish_job(JobStatus.SHORTLISTED)
    return latest_documents(job_id)


def update_document(doc_id: str, content: str, *, expected_revision: int) -> dict:
    """Save the user's edits. Edited text is re-checked for unverified numbers."""
    from api.job_os.resume import load_resume

    doc = get_document(doc_id)
    if doc is None:
        raise KeyError(doc_id)
    if doc["revision"] != expected_revision:
        raise TailorError("This document changed in another tab; reload it.")
    text = str(content or "")[:30000]
    master = (load_resume() or {}).get("text", "")
    notes = dict(doc["notes"])
    notes["unverified"] = unverified_numbers(text, master)
    notes["edited"] = True
    conn = connect_job_os()
    try:
        conn.execute("UPDATE job_documents SET content=?, notes_json=?, status=?, revision=revision+1, updated_at=? WHERE id=?",
                     (text, json.dumps(notes), "needs_review" if notes["unverified"] else "ready", int(time.time()), doc_id))
        conn.commit()
    finally:
        conn.close()
    return get_document(doc_id)


def _next_pending() -> str | None:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT job_id FROM job_documents WHERE status='pending' ORDER BY created_at LIMIT 1").fetchone()
        return row["job_id"] if row else None
    finally:
        conn.close()


def _requeue_orphans() -> None:
    global _recovered
    if _recovered:
        return
    _recovered = True
    conn = connect_job_os()
    try:
        conn.execute("UPDATE job_documents SET status='pending' WHERE status='running'")
        conn.commit()
    finally:
        conn.close()


def _work() -> None:
    global _worker
    try:
        while True:
            job_id = _next_pending()
            if job_id is None:
                return
            tailor_one(job_id)
    except Exception:
        logger.debug("tailor worker stopped", exc_info=True)
    finally:
        with _lock:
            _worker = None
        if _next_pending():
            ensure_worker()


def ensure_worker() -> None:
    global _worker
    with _lock:
        _requeue_orphans()
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_work, name="job-os-tailor", daemon=True)
        _worker.start()
