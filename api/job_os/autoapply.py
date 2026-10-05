"""Gated auto-apply: fill (and, once approved, submit) standard ATS forms.

Off by default (Jobs -> Settings -> Auto-apply). Every run passes the same
gate -- enabled, an allowed ATS (Greenhouse, Lever, Ashby), the job is
*Application ready* (you approved its tailored resume), fit score at or above
the minimum, your name and email filled in, and for real submissions the
daily limit. The browser work runs in a separate process
(``apply_runner.py``) with a hard timeout.

Flow:

* **Preview** (a dry run): fill the form, screenshot it, never submit. The job
  moves to *Awaiting approval*; you approve in the board or by replying
  ``APPLY <code>`` to the email.
* **Submit**: approval moves the job to *Applying* and the runner fills the
  form again and presses submit; a confirmation page moves it to
  *Submitted*. Anything else returns it to *Application ready*.
* With *Dry run first* on, an ATS gets a preview until you have approved one
  successful submission there; after that, scheduled runs submit directly.

Captchas, salary/legal/consent questions, required questions Hermes can't
answer, or a missing confirmation stop the run and put the job in *Needs
attention* (an ``auto_apply_stopped`` event) -- it is never retried
automatically.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from api.job_os.db import connect_job_os
from api.job_os.models import JobStatus
from api.job_os.paths import job_os_state_dir
from api.job_os.repository import get_job

logger = logging.getLogger(__name__)
RUN_TIMEOUT = 240
REPO_ROOT = Path(__file__).resolve().parents[2]
ATS_HOSTS = {
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io", "job-boards.eu.greenhouse.io", "boards.eu.greenhouse.io"),
    "lever": ("jobs.lever.co", "jobs.eu.lever.co"),
    "ashby": ("jobs.ashbyhq.com",),
}
_queue_lock = threading.Lock()
_worker: threading.Thread | None = None
# Tests replace this: (job_payload) -> result dict.
_runner = None


class AutoApplyError(ValueError):
    """The job can't be auto-applied right now (HTTP 400); the message says why."""


# ---- gate ----------------------------------------------------------------

def ats_of(url: str) -> str | None:
    host = (urlparse(url or "").hostname or "").lower()
    return next((ats for ats, hosts in ATS_HOSTS.items() if host in hosts), None)


def form_url(url: str, ats: str) -> str:
    """The page with the application form on it."""
    path = urlparse(url).path.rstrip("/")
    base = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if ats == "lever" and not path.endswith("/apply"):
        return base + "/apply"
    if ats == "ashby" and not path.endswith("/application"):
        return base + "/application"
    return base


def submitted_today(now: float | None = None) -> int:
    now = time.time() if now is None else now
    start = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    conn = connect_job_os()
    try:
        return conn.execute("SELECT COUNT(*) FROM apply_runs WHERE mode='submit' AND status='submitted' AND finished_at>=?",
                            (int(start),)).fetchone()[0]
    finally:
        conn.close()


def has_trusted_submission(ats: str) -> bool:
    """An approved preview on ``ats`` was followed by a confirmed submission."""
    conn = connect_job_os()
    try:
        return conn.execute("SELECT 1 FROM apply_runs WHERE ats=? AND mode='submit' AND status='submitted' LIMIT 1",
                            (ats,)).fetchone() is not None
    finally:
        conn.close()


def check(job_id: str, *, mode: str, settings: dict | None = None, now: float | None = None) -> tuple[object, str]:
    """Return ``(job, ats)`` or raise AutoApplyError with the reason."""
    from api.job_os.analysis import get_analysis
    from api.job_os.network_policy import validate_external_job_url
    from api.job_os.settings import load_settings

    settings = settings or load_settings()
    policy = settings["auto_apply"]
    if not policy["enabled"]:
        raise AutoApplyError("Auto-apply is off (Jobs → Settings → Auto-apply).")
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    ats = ats_of(job.canonical_url)
    if ats is None:
        raise AutoApplyError("Auto-apply only works on Greenhouse, Lever and Ashby postings.")
    if ats not in policy["allowed_ats"]:
        raise AutoApplyError(f"{ats.title()} isn't in your allowed application systems.")
    expected = JobStatus.APPLICATION_READY if mode == "preview" else JobStatus.AWAITING_APPROVAL
    if job.status != expected:
        raise AutoApplyError("Approve the tailored resume (Application ready) first." if mode == "preview"
                             else "This job isn't waiting for approval.")
    analysis = get_analysis(job_id) or {}
    if analysis.get("status") != "done" or (analysis.get("fit_score") or 0) < policy["min_fit_score"]:
        raise AutoApplyError(f"Fit score is below your auto-apply minimum ({policy['min_fit_score']}).")
    applicant = settings["applicant"]
    if not (applicant.get("full_name") and applicant.get("email")):
        raise AutoApplyError("Add your name and email under Jobs → Settings → Your details.")
    if mode == "submit" and submitted_today(now) >= policy["daily_cap"]:
        raise AutoApplyError(f"Today's auto-apply limit ({policy['daily_cap']}) is used up.")
    try:
        validate_external_job_url(form_url(job.canonical_url, ats))
    except Exception as error:
        raise AutoApplyError(f"The posting address isn't allowed ({error}).") from error
    return job, ats


# ---- runs ----------------------------------------------------------------

def _event(conn, job_id: str, event_type: str, payload: dict) -> None:
    conn.execute("INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                 (str(uuid.uuid4()), job_id, event_type, json.dumps(payload, separators=(",", ":")), int(time.time())))


def _new_run(job_id: str, mode: str, ats: str, trigger: str) -> str:
    run_id = uuid.uuid4().hex
    conn = connect_job_os()
    try:
        conn.execute("INSERT INTO apply_runs (id, job_id, mode, ats, trigger, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                     (run_id, job_id, mode, ats, trigger, int(time.time())))
        conn.commit()
    finally:
        conn.close()
    return run_id


def _finish(run_id: str, status: str, reason: str, result: dict) -> None:
    conn = connect_job_os()
    try:
        conn.execute("UPDATE apply_runs SET status=?, reason=?, result_json=?, finished_at=? WHERE id=?",
                     (status, reason[:300], json.dumps(result)[:20000], int(time.time()), run_id))
        conn.commit()
    finally:
        conn.close()


def _row(r) -> dict:
    return {"id": r["id"], "job_id": r["job_id"], "mode": r["mode"], "ats": r["ats"], "trigger": r["trigger"],
            "status": r["status"], "reason": r["reason"], "result": json.loads(r["result_json"] or "{}"),
            "created_at": r["created_at"], "finished_at": r["finished_at"]}


def runs_for(job_id: str) -> list[dict]:
    conn = connect_job_os()
    try:
        return [_row(r) for r in conn.execute("SELECT * FROM apply_runs WHERE job_id=? ORDER BY created_at DESC, rowid DESC", (job_id,))]
    finally:
        conn.close()


def latest_runs() -> dict[str, dict]:
    """Newest run per job (for the board)."""
    conn = connect_job_os()
    try:
        rows = conn.execute("SELECT * FROM apply_runs r WHERE created_at = (SELECT MAX(created_at) FROM apply_runs WHERE job_id=r.job_id)"
                            " ORDER BY rowid").fetchall()
        return {r["job_id"]: _row(r) for r in rows}
    finally:
        conn.close()


def proof_dir(job_id: str) -> Path:
    safe = "".join(ch for ch in job_id if ch.isalnum() or ch == "-")[:64]
    return job_os_state_dir() / "applications" / safe


def browser_python() -> str | None:
    """An interpreter that has Playwright: override, this one, then the repo .venv."""
    override = os.environ.get("HERMES_JOB_OS_BROWSER_PYTHON", "").strip()
    if override:
        return override
    if importlib.util.find_spec("playwright") is not None:
        return sys.executable
    candidate = REPO_ROOT / ".venv" / "bin" / "python"
    if candidate.exists():
        probe = subprocess.run([str(candidate), "-c", "import playwright"], capture_output=True, timeout=30)
        if probe.returncode == 0:
            return str(candidate)
    return None


def _subprocess_runner(payload: dict) -> dict:
    python = browser_python()
    if python is None:
        return {"status": "stopped", "reason": "Browser automation isn't installed (Playwright).", "screenshots": []}
    try:
        proc = subprocess.run([python, "-m", "api.job_os.apply_runner"], input=json.dumps(payload), capture_output=True,
                              text=True, timeout=RUN_TIMEOUT, cwd=str(REPO_ROOT))
    except subprocess.TimeoutExpired:
        return {"status": "error", "reason": "The browser run timed out.", "screenshots": []}
    line = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    try:
        return json.loads(line[0])
    except ValueError:
        logger.debug("apply runner stderr: %s", (proc.stderr or "")[-2000:])
        return {"status": "error", "reason": "The browser run failed to report a result.", "screenshots": []}


def _payload(job, ats: str, mode: str, settings: dict) -> dict:
    from api.job_os.export import to_html
    from api.job_os.tailor import latest_documents

    docs = latest_documents(job.id)
    resume = (docs.get("resume") or {}).get("content") or ""
    letter = (docs.get("cover_letter") or {}).get("content") or ""
    name = settings["applicant"].get("full_name") or "Resume"
    pdf_html = {"resume": to_html(resume, title=f"{name} — Resume")} if resume else {}
    if letter:
        pdf_html["cover_letter"] = to_html(letter, title=f"{name} — Cover letter")
    return {"url": form_url(job.canonical_url, ats), "mode": mode, "applicant": settings["applicant"],
            "pdf_html": pdf_html, "files": {}, "cover_text": letter, "out_dir": str(proof_dir(job.id))}


def _stop(job_id: str, reason: str, run_id: str) -> None:
    conn = connect_job_os()
    try:
        _event(conn, job_id, "auto_apply_stopped", {"reason": reason[:200], "run_id": run_id})
        conn.commit()
    finally:
        conn.close()


def _execute(job_id: str, mode: str, trigger: str) -> dict:
    """Run one preview or submission now (the worker's unit of work)."""
    from api.job_os.lifecycle import transition_job
    from api.job_os.settings import load_settings

    settings = load_settings()
    try:
        job, ats = check(job_id, mode=mode, settings=settings)
    except AutoApplyError as error:
        if mode == "submit":  # approval was given but the gate closed meanwhile: hand the job back
            _return_to_ready(job_id)
        _stop(job_id, str(error), "")
        return {"status": "stopped", "reason": str(error)}
    run_id = _new_run(job_id, mode, ats, trigger)
    if mode == "submit":
        job = transition_job(job_id, JobStatus.APPLYING, expected_revision=job.revision)
    result = (_runner or _subprocess_runner)(_payload(job, ats, mode, settings))
    status, reason = result.get("status", "error"), result.get("reason", "")
    _finish(run_id, status, reason, result)
    if mode == "preview" and status == "filled":
        current = get_job(job_id)
        transition_job(job_id, JobStatus.AWAITING_APPROVAL, expected_revision=current.revision)
        conn = connect_job_os()
        try:
            _event(conn, job_id, "auto_apply_preview", {"run_id": run_id, "filled": len(result.get("filled") or [])})
            conn.commit()
        finally:
            conn.close()
        _email_preview(job_id, result)
    elif mode == "submit" and status == "submitted":
        from api.job_os.applications import mark_applied

        mark_applied(job_id, method="auto", note=f"Submitted on {ats.title()} (run {run_id[:8]})")
    else:
        if mode == "submit":
            _return_to_ready(job_id)
        _stop(job_id, reason or "The browser run failed.", run_id)
    return {"status": status, "reason": reason, "run_id": run_id}


def _return_to_ready(job_id: str) -> None:
    from api.job_os.lifecycle import transition_job

    job = get_job(job_id)
    if job is None:
        return
    if job.status == JobStatus.AWAITING_APPROVAL:
        job = transition_job(job_id, JobStatus.APPLYING, expected_revision=job.revision)
    if job.status == JobStatus.APPLYING:
        transition_job(job_id, JobStatus.APPLICATION_READY, expected_revision=job.revision)


def _email_preview(job_id: str, result: dict) -> None:
    try:
        from api.job_os import notify

        notify.send_preview(job_id, result)
    except Exception:
        logger.debug("preview email failed", exc_info=True)


# ---- public actions ------------------------------------------------------

_pending: list[tuple[str, str, str]] = []


def _work() -> None:
    global _worker
    try:
        while True:
            with _queue_lock:
                if not _pending:
                    return
                job_id, mode, trigger = _pending.pop(0)
            try:
                _execute(job_id, mode, trigger)
            except Exception:
                logger.exception("auto-apply run failed for %s", job_id)
    finally:
        with _queue_lock:
            _worker = None


def _enqueue(job_id: str, mode: str, trigger: str, start_worker: bool) -> None:
    global _worker
    with _queue_lock:
        if any(item[0] == job_id for item in _pending):
            raise AutoApplyError("This job already has an auto-apply run queued.")
        _pending.append((job_id, mode, trigger))
        if not start_worker or (_worker is not None and _worker.is_alive()):
            return
        _worker = threading.Thread(target=_work, name="job-os-autoapply", daemon=True)
        _worker.start()


def request_preview(job_id: str, *, trigger: str = "manual", start_worker: bool = True) -> dict:
    check(job_id, mode="preview")
    _enqueue(job_id, "preview", trigger, start_worker)
    return {"job_id": job_id, "queued": "preview"}


def approve(job_id: str, *, trigger: str = "manual", start_worker: bool = True) -> dict:
    """You looked at the filled form: send it."""
    check(job_id, mode="submit")
    _enqueue(job_id, "submit", trigger, start_worker)
    return {"job_id": job_id, "queued": "submit"}


def cancel(job_id: str) -> dict:
    """Don't send: the job goes back to Application ready."""
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status != JobStatus.AWAITING_APPROVAL:
        raise AutoApplyError("This job isn't waiting for approval.")
    _return_to_ready(job_id)
    conn = connect_job_os()
    try:
        _event(conn, job_id, "auto_apply_cancelled", {})
        conn.commit()
    finally:
        conn.close()
    return {"job_id": job_id, "status": "application_ready"}


def tick(*, start_worker: bool = True) -> str | None:
    """Scheduled pass: start at most one run for an eligible job that has never had one."""
    from api.job_os.lifecycle import transition_job
    from api.job_os.repository import list_jobs
    from api.job_os.settings import load_settings

    settings = load_settings()
    if not settings["auto_apply"]["enabled"]:
        return None
    with _queue_lock:
        if _pending or (_worker is not None and _worker.is_alive()):
            return None
    tried = set(latest_runs())
    for job in list_jobs():
        if job.status != JobStatus.APPLICATION_READY or job.id in tried:
            continue
        try:
            _job, ats = check(job.id, mode="preview", settings=settings)
        except (AutoApplyError, KeyError):
            continue
        if settings["auto_apply"]["dry_run_first"] and not has_trusted_submission(ats):
            _enqueue(job.id, "preview", "schedule", start_worker)
            return job.id
        if submitted_today() >= settings["auto_apply"]["daily_cap"]:
            return None
        transition_job(job.id, JobStatus.AWAITING_APPROVAL, expected_revision=job.revision)
        conn = connect_job_os()
        try:
            _event(conn, job.id, "auto_apply_approved", {"by": "policy", "ats": ats})
            conn.commit()
        finally:
            conn.close()
        _enqueue(job.id, "submit", "schedule", start_worker)
        return job.id
    return None
