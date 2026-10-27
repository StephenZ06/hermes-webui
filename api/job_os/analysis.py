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
# Stored with each analysis, so Score again can find the ones made by an older prompt.
# 2: eligibility and language gates, closing date, dimension scores.
ANALYSIS_PROMPT_VERSION = 2
ELIGIBILITY = ("pass", "fail", "unverified")
LANGUAGE = ("pass", "fail", "flag", "unverified")
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
    "each under 120 characters.\n"
    "Also return \"gates\": {\"eligibility\": \"pass|fail|unverified\", \"eligibility_quote\": \"<posting wording>\", "
    "\"language\": \"pass|fail|flag|unverified\", \"language_quote\": \"<posting wording>\"}, judged against the "
    "candidate PROFILE. Eligibility: a citizenship, permanent-residency or security-clearance requirement the profile "
    "does not meet is fail; a posting that accepts visa holders or offers sponsorship is pass; a posting that says "
    "nothing about the right to work is unverified, never pass. Language: a required language the profile does not "
    "list is fail; a required level above the profile's stated level is flag; otherwise pass. If the profile does not "
    "say, answer unverified. Quotes are the posting's own words, under 160 characters, or empty.\n"
    "Also return \"deadline\": the closing date for applications as \"YYYY-MM-DD\" only when the posting states one, "
    "else null. " + llm.UNTRUSTED
)


def profile_block(settings: dict | None = None) -> str:
    """The candidate facts the gates are judged against (Settings → Application answers)."""
    if settings is None:
        from api.job_os.settings import load_settings

        settings = load_settings()
    apply, applicant = settings.get("apply") or {}, settings.get("applicant") or {}
    rows = [("Right to work", apply.get("work_authorization")), ("Languages", apply.get("languages")),
            ("Relocation", apply.get("relocation")), ("Based in", applicant.get("location"))]
    return "\n".join(f"{label}: {str(value or '').strip() or 'not stated'}" for label, value in rows)


def _gates(data: dict, profile: str) -> dict:
    """The gates, failing closed: a missing or unknown answer is never a pass."""
    raw = data.get("gates") if isinstance(data.get("gates"), dict) else {}
    eligibility = str(raw.get("eligibility") or "").lower()
    language = str(raw.get("language") or "").lower()
    eligibility = eligibility if eligibility in ELIGIBILITY else "unverified"
    language = language if language in LANGUAGE else "flag"
    facts = dict(line.split(": ", 1) for line in profile.splitlines() if ": " in line)
    # Without the person's own answer a requirement can't be judged either way.
    if facts.get("Right to work", "not stated") == "not stated" and eligibility != "unverified":
        eligibility = "unverified"
    if facts.get("Languages", "not stated") == "not stated" and language != "pass":
        language = "unverified"
    quote = lambda key: str(raw.get(key) or "").strip()[:160]  # noqa: E731
    return {"eligibility": eligibility, "eligibility_quote": quote("eligibility_quote"),
            "language": language, "language_quote": quote("language_quote"),
            "profile_missing": [k for k in ("Right to work", "Languages") if facts.get(k, "not stated") == "not stated"]}


class AnalysisError(ValueError):
    """Analysis cannot be requested (HTTP 400)."""


def _clean(data: dict, profile: str = "") -> dict:
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
    gates = _gates(data, profile)
    if "fail" in (gates["eligibility"], gates["language"]):
        verdict = "poor"  # a job you can't take is never a good match, whatever the skills say
    from api.job_os.repository import parse_deadline

    return {"fit_score": score, "verdict": verdict, "gates": gates, "prompt_version": ANALYSIS_PROMPT_VERSION,
            "deadline": parse_deadline(data.get("deadline")) or None, "summary": str(data.get("summary") or "").strip()[:400],
            "strengths": items("strengths"), "gaps": items("gaps"), "must_haves": items("must_haves"),
            "seniority": str(data.get("seniority") or "").strip()[:60],
            "salary_note": str(data.get("salary_note") or "").strip()[:160]}


def _row(row) -> dict:
    data = json.loads(row["data_json"] or "{}")
    return {"job_id": row["job_id"], "status": row["status"], "fit_score": row["fit_score"], "verdict": row["verdict"],
            "error": row["error"], "model": row["model"], "requested_at": row["requested_at"],
            "finished_at": row["finished_at"], **{k: data.get(k) for k in DETAIL_KEYS}}


DETAIL_KEYS = ("summary", "strengths", "gaps", "must_haves", "seniority", "salary_note", "gates", "prompt_version",
               "deadline")
# What list payloads carry besides the score: enough for the checks on a card.
COMPACT_KEYS = ("gates",)


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
        out = {}
        for r in conn.execute("SELECT job_id, status, fit_score, verdict, data_json FROM job_analyses"):
            try:
                data = json.loads(r["data_json"] or "{}")
            except ValueError:
                data = {}
            out[r["job_id"]] = {"status": r["status"], "fit_score": r["fit_score"], "verdict": r["verdict"],
                                **{k: data[k] for k in COMPACT_KEYS if k in data}}
        return out
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
    """The posting as Luna reads it, cleaned again by the posting guard (jobs
    saved before the guard still carry their original text)."""
    from api.job_os.posting_guard import guard_text

    description = guard_text(job.description)[0]
    return (f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\nWorkplace: {job.workplace}\n"
            f"Employment: {job.employment_type}\nPay: {job.salary_text}\n\n{description[:14000]}")


def score_text(job, resume_text: str) -> dict:
    """Luna's fit of any resume text against a job, with the same prompt and
    scale as the master resume's analysis (so the two are comparable)."""
    profile = profile_block()
    data, _model = llm.ask_json(SYSTEM, _prompt(job, resume_text, profile))
    return _clean(data, profile)


def _prompt(job, resume_text: str, profile: str) -> str:
    return (f"<<<POSTING\n{posting_text(job)}\nPOSTING>>>\n\n<<<RESUME\n{resume_text[:14000]}\nRESUME>>>\n\n"
            f"<<<PROFILE\n{profile}\nPROFILE>>>")


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
        profile = profile_block()
        data, model = llm.ask_json(SYSTEM, _prompt(job, resume["text"], profile))
        result = _clean(data, profile)
        conn = connect_job_os()
        try:
            conn.execute("UPDATE job_analyses SET status='done', fit_score=?, verdict=?, data_json=?, model=?, error='', finished_at=? WHERE job_id=?",
                         (result["fit_score"], result["verdict"], json.dumps(result), model, int(time.time()), job_id))
            if result["deadline"]:  # a date the site sent wins over Luna's reading of the text
                conn.execute("UPDATE jobs SET deadline=? WHERE id=? AND deadline=''", (result["deadline"], job_id))
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


def resume_if_stalled() -> None:
    """Restart the queue if work is waiting and no worker is running.

    A server restart kills the worker thread mid-analysis: its row stays
    'running' (or 'pending') and nothing restarts the queue until the next
    request, so the score ring in the page spins forever. Read paths call this,
    so a page that is showing "scoring" also drives the queue on."""
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
    conn = connect_job_os()
    try:
        waiting = conn.execute("SELECT 1 FROM job_analyses WHERE status IN ('pending', 'running') LIMIT 1").fetchone()
    finally:
        conn.close()
    if waiting:
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
