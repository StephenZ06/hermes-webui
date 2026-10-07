"""Luna job analysis: a fit score and reasons for each posting against the master resume.

Requests queue in ``job_analyses`` and one background worker processes them in
order, so a Scout run that finds 20 jobs never fires 20 model calls at once.
A finished analysis moves the job from ``scraped`` to ``analyzed``; the user
decides shortlist vs skip.
"""

from __future__ import annotations

import json
import logging
import threading
import time

from api.job_os import llm
from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.repository import get_job

logger = logging.getLogger(__name__)
VERDICTS = ("strong", "good", "stretch", "poor")
_worker_lock = threading.Lock()
_worker: threading.Thread | None = None
_recovered = False

SYSTEM = (
    "You are a careful career analyst. Compare one job posting with the candidate's resume and return ONLY JSON:\n"
    '{"fit_score": <integer 0-100>, "verdict": "strong|good|stretch|poor", "summary": "<2 sentences>", '
    '"strengths": ["<matching evidence from the resume>"], "gaps": ["<requirement the resume does not show>"], '
    '"must_haves": ["<key requirement from the posting>"], "seniority": "<level the posting wants>", '
    '"salary_note": "<pay info or empty>"}\n'
    "Scoring: 85+ strong match on most must-haves; 70-84 good; 50-69 stretch; under 50 poor. "
    "Strengths must cite things actually in the resume; never invent experience. Up to 5 items per list, "
    "each under 120 characters. " + llm.UNTRUSTED
)


class AnalysisError(ValueError):
    """Analysis cannot be requested (HTTP 400)."""


def _clean(data: dict) -> dict:
    def items(key):
        values = data.get(key) if isinstance(data.get(key), list) else []
        return [str(v).strip()[:160] for v in values if str(v).strip()][:5]
    try:
        score = max(0, min(100, int(round(float(data.get("fit_score"))))))
    except (TypeError, ValueError) as error:
        raise llm.LLMError("The analysis had no fit score.") from error
    verdict = str(data.get("verdict") or "").lower()
    if verdict not in VERDICTS:
        verdict = "strong" if score >= 85 else "good" if score >= 70 else "stretch" if score >= 50 else "poor"
    return {"fit_score": score, "verdict": verdict, "summary": str(data.get("summary") or "").strip()[:400],
            "strengths": items("strengths"), "gaps": items("gaps"), "must_haves": items("must_haves"),
            "seniority": str(data.get("seniority") or "").strip()[:60],
            "salary_note": str(data.get("salary_note") or "").strip()[:160]}


def _row(row) -> dict:
    data = json.loads(row["data_json"] or "{}")
    return {"job_id": row["job_id"], "status": row["status"], "fit_score": row["fit_score"], "verdict": row["verdict"],
            "error": row["error"], "model": row["model"], "requested_at": row["requested_at"],
            "finished_at": row["finished_at"], **{k: data.get(k) for k in ("summary", "strengths", "gaps", "must_haves", "seniority", "salary_note")}}


def get_analysis(job_id: str) -> dict | None:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT * FROM job_analyses WHERE job_id=?", (job_id,)).fetchone()
        return _row(row) if row else None
    finally:
        conn.close()


def analyses_by_job() -> dict[str, dict]:
    """Compact per-job analysis state for list payloads."""
    conn = connect_job_os()
    try:
        return {r["job_id"]: {"status": r["status"], "fit_score": r["fit_score"], "verdict": r["verdict"]}
                for r in conn.execute("SELECT job_id, status, fit_score, verdict FROM job_analyses")}
    finally:
        conn.close()


def request_analysis(job_ids: list[str], *, force: bool = False, start_worker: bool = True) -> int:
    """Queue analyses. Skips jobs without a description, already queued, or (unless
    ``force``) already analyzed. Returns how many were queued."""
    from api.job_os.resume import load_resume

    if not load_resume():
        raise AnalysisError("Upload your resume in Resume Studio first; analysis compares each job with it.")
    queued = 0
    now = int(time.time())
    conn = connect_job_os()
    try:
        for job_id in dict.fromkeys(job_ids):
            job = conn.execute("SELECT description FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None or not (job["description"] or "").strip():
                continue
            existing = conn.execute("SELECT status FROM job_analyses WHERE job_id=?", (job_id,)).fetchone()
            if existing and (existing["status"] in ("pending", "running") or (existing["status"] == "done" and not force)):
                continue
            conn.execute(
                "INSERT INTO job_analyses (job_id, status, requested_at) VALUES (?, 'pending', ?)"
                " ON CONFLICT(job_id) DO UPDATE SET status='pending', error='', requested_at=excluded.requested_at, finished_at=NULL",
                (job_id, now))
            queued += 1
        conn.commit()
    finally:
        conn.close()
    if queued and start_worker:
        ensure_worker()
    return queued


def posting_text(job) -> str:
    return (f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\nWorkplace: {job.workplace}\n"
            f"Employment: {job.employment_type}\nPay: {job.salary_text}\n\n{job.description[:14000]}")


def score_text(job, resume_text: str) -> dict:
    """Luna's fit of any resume text against a job, with the same prompt and
    scale as the master resume's analysis (so the two are comparable)."""
    data, _model = llm.ask_json(SYSTEM, f"<<<POSTING\n{posting_text(job)}\nPOSTING>>>\n\n<<<RESUME\n{resume_text[:14000]}\nRESUME>>>")
    return _clean(data)


def analyze_one(job_id: str) -> dict:
    """Run one analysis now (the worker's unit of work). Returns the stored row."""
    from api.job_os.lifecycle import transition_job
    from api.job_os.resume import load_resume

    job = get_job(job_id)
    resume = load_resume()
    conn = connect_job_os()
    try:
        conn.execute("UPDATE job_analyses SET status='running' WHERE job_id=?", (job_id,))
        conn.commit()
    finally:
        conn.close()
    try:
        if job is None or resume is None:
            raise llm.LLMError("The job or the resume is no longer available.")
        data, model = llm.ask_json(SYSTEM, f"<<<POSTING\n{posting_text(job)}\nPOSTING>>>\n\n<<<RESUME\n{resume['text'][:14000]}\nRESUME>>>")
        result = _clean(data)
        conn = connect_job_os()
        try:
            conn.execute("UPDATE job_analyses SET status='done', fit_score=?, verdict=?, data_json=?, model=?, error='', finished_at=? WHERE job_id=?",
                         (result["fit_score"], result["verdict"], json.dumps(result), model, int(time.time()), job_id))
            conn.commit()
        finally:
            conn.close()
        current = get_job(job_id)
        if current is not None and current.status == JobStatus.SCRAPED:
            try:
                transition_job(job_id, JobStatus.ANALYZED, expected_revision=current.revision)
            except Exception:  # a concurrent user action wins; the analysis is still stored
                logger.debug("analyzed transition skipped for %s", job_id, exc_info=True)
        _after(job_id, result["fit_score"])
    except Exception as error:
        message = str(error) if isinstance(error, llm.LLMError) else f"Analysis failed ({type(error).__name__})."
        conn = connect_job_os()
        try:
            conn.execute("UPDATE job_analyses SET status='failed', error=?, finished_at=? WHERE job_id=?",
                         (message[:300], int(time.time()), job_id))
            conn.commit()
        finally:
            conn.close()
        _after(job_id, None)
    return get_analysis(job_id)


def _after(job_id: str, fit_score: int | None) -> None:
    """Automate all may be waiting on this score to tailor the job."""
    try:
        from api.job_os.autopilot import after_analysis

        after_analysis(job_id, fit_score)
    except Exception:
        logger.debug("auto-tailor check failed for %s", job_id, exc_info=True)


def _next_pending() -> str | None:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT job_id FROM job_analyses WHERE status='pending' ORDER BY requested_at, job_id LIMIT 1").fetchone()
        return row["job_id"] if row else None
    finally:
        conn.close()


def _requeue_orphans() -> None:
    """Analyses left 'running' by a restart go back in the queue (once per process)."""
    global _recovered
    if _recovered:
        return
    _recovered = True
    conn = connect_job_os()
    try:
        conn.execute("UPDATE job_analyses SET status='pending' WHERE status='running'")
        conn.commit()
    finally:
        conn.close()


def _notify_matches() -> None:
    """The queue drained: email any new strong matches (if notifications are on)."""
    try:
        from api.job_os.notify import send_matches

        send_matches()
    except Exception:
        logger.debug("match alert failed", exc_info=True)


def _work() -> None:
    global _worker
    try:
        while True:
            job_id = _next_pending()
            if job_id is None:
                _notify_matches()
                return
            analyze_one(job_id)
    except Exception:
        logger.debug("analysis worker stopped", exc_info=True)
    finally:
        with _worker_lock:
            _worker = None
        if _next_pending():  # something was queued as we were exiting
            ensure_worker()


def ensure_worker() -> None:
    global _worker
    with _worker_lock:
        _requeue_orphans()
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_work, name="job-os-analysis", daemon=True)
        _worker.start()


def queue_counts() -> dict:
    conn = connect_job_os()
    try:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM job_analyses GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
    finally:
        conn.close()
