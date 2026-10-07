"""Automate all: score and tailor a batch of jobs without reviewing each one.

Resume Studio's match check walks the jobs on the Pipeline board one by one;
"Automate all" does the same work in the background for the jobs not yet
done. A job that already has its fit score is tailored now if it reaches the
bar; one without a score is queued for analysis first and remembered in
``auto_tailor``, and the analysis worker tailors it when its score comes back
at or above the bar (``after_analysis``). Jobs below the bar are left for you.
Nothing is ever sent: applying stays a person's step.
"""

from __future__ import annotations

import logging
import time

from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.repository import get_job

logger = logging.getLogger(__name__)
# "Needs improvement" and up: the band tailoring helps most. Below it a job
# usually misses a must-have no rewording can supply.
MIN_FIT = 50
_TAILORABLE = (JobStatus.SCRAPED, JobStatus.ANALYZED, JobStatus.SHORTLISTED)


class AutopilotError(ValueError):
    """Automate all cannot start (HTTP 400)."""


def automate(job_ids: list[str], *, start_workers: bool = True) -> dict:
    """Tailor every job in ``job_ids`` that qualifies; score the unscored first."""
    from api.job_os import analysis, tailor
    from api.job_os.resume import load_resume

    if not load_resume():
        raise AutopilotError("Upload your master resume in Resume Studio first.")
    out = {"tailoring": 0, "scoring": 0, "below": 0, "skipped": 0}
    scores = analysis.analyses_by_job()
    to_score: list[str] = []
    now = int(time.time())
    for job_id in dict.fromkeys(str(i) for i in job_ids if i):
        job = get_job(job_id)
        if job is None or not (job.description or "").strip() or job.status not in _TAILORABLE:
            out["skipped"] += 1
            continue
        state = scores.get(job_id) or {}
        if state.get("status") == "done" and state.get("fit_score") is not None:
            if state["fit_score"] < MIN_FIT:
                out["below"] += 1
                continue
            try:
                tailor.request_tailoring(job_id, start_worker=False)
                out["tailoring"] += 1
            except (tailor.TailorError, ValueError):
                out["skipped"] += 1
            continue
        if state.get("status") not in ("pending", "running"):
            to_score.append(job_id)
        _remember(job_id, now)
        out["scoring"] += 1
    if to_score:
        analysis.request_analysis(to_score, force=True, start_worker=start_workers)
    if out["tailoring"] and start_workers:
        tailor.ensure_worker()
    return out


def _remember(job_id: str, now: int) -> None:
    conn = connect_job_os()
    try:
        conn.execute("INSERT INTO auto_tailor (job_id, requested_at) VALUES (?, ?) ON CONFLICT(job_id) DO NOTHING", (job_id, now))
        conn.commit()
    finally:
        conn.close()


def waiting() -> set[str]:
    conn = connect_job_os()
    try:
        return {r["job_id"] for r in conn.execute("SELECT job_id FROM auto_tailor")}
    finally:
        conn.close()


def after_analysis(job_id: str, fit_score: int | None, *, start_worker: bool = True) -> bool:
    """Called when an analysis finishes (or fails): tailor the job if Automate
    all was waiting on it and it reached the bar. Returns whether it started."""
    from api.job_os import tailor

    conn = connect_job_os()
    try:
        cur = conn.execute("DELETE FROM auto_tailor WHERE job_id=?", (job_id,))
        conn.commit()
        if cur.rowcount != 1:
            return False
    finally:
        conn.close()
    if fit_score is None or fit_score < MIN_FIT:
        return False
    try:
        tailor.request_tailoring(job_id, start_worker=start_worker)
        return True
    except Exception:  # the job moved on (skipped, applied) since it was queued
        logger.debug("auto-tailor skipped for %s", job_id, exc_info=True)
        return False
