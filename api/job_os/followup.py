"""Follow-ups: a drafted nudge for an application gone quiet, and the stale sweep.

Once an application has had no news for ``applications.FOLLOW_UP_DAYS`` the
job's side panel offers **Draft follow-up**: one Luna call with the posting
and the resume and cover letter you sent. The draft is 60-120 words, uses
only claims from what you sent, reminds them of one strength, asks one
question about timing, and comes as an email (with a subject), a LinkedIn
message or a portal note. Numbers that are not in what you sent are flagged,
like tailoring's check.

Hermes never sends it: you copy it or open it in your mail app, then press
**I sent it**, which logs it and restarts the quiet clock. Two follow-ups at
most; after that the panel offers **Mark no response**. A status change after
a draft (an employer reply moving the job, a drag) retires the draft.

The **stale sweep** lists applications quiet for 60+ days so they can be
moved to No response in one go; each move is logged and can be dragged back.

Adapted from ai-job-search (github.com/ai-job-search-dev/ai-job-search, MIT).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid

from api.job_os import llm
from api.job_os.db import connect_job_os
from api.job_os.repository import get_job

logger = logging.getLogger(__name__)
MAX_FOLLOW_UPS = 2
STALE_DAYS = 60
WAITING = ("submitted", "screening", "interviewing")
CHANNELS = ("email", "linkedin", "portal")
SYSTEM = (
    "You write one short follow-up message from a job candidate about an application that has gone quiet. "
    "Return ONLY JSON: {\"channel\": \"email|linkedin|portal\", \"subject\": \"<email subject, or empty>\", "
    "\"body\": \"<message>\"}\n"
    "Rules: 60-120 words; polite and specific to this role and company; one reminder of the single strongest fit "
    "taken from the SENT documents; one question about the timeline or next steps; written in the same language and "
    "tone as the sent cover letter; plain text, no placeholders like [Name] (use 'Hello' when no contact name is "
    "given). Use ONLY facts in the SENT documents: never add skills, numbers, employers or achievements that are "
    "not there. Choose email when a contact address is given, otherwise the channel named in the request. "
    + llm.UNTRUSTED
)


class FollowUpError(ValueError):
    """A follow-up can't be drafted now (HTTP 400)."""


def _events(job_id: str) -> list:
    conn = connect_job_os()
    try:
        return conn.execute("SELECT event_type, payload_json, created_at FROM job_events WHERE job_id=?"
                            " ORDER BY created_at, rowid", (job_id,)).fetchall()
    finally:
        conn.close()


def _row(job_id: str):
    conn = connect_job_os()
    try:
        return conn.execute("SELECT * FROM follow_ups WHERE job_id=?", (job_id,)).fetchone()
    finally:
        conn.close()


def state(job, *, now: int | None = None) -> dict | None:
    """What the job's Follow up section shows, or None for a job not waiting on a reply."""
    if job.status.value not in WAITING:
        return None
    now = int(time.time()) if now is None else now
    events = _events(job.id)
    moved = [e["created_at"] for e in events if e["event_type"] in ("status_changed", "application_submitted")]
    sent = [e["created_at"] for e in events if e["event_type"] == "follow_up_sent"]
    last = max(moved + sent) if moved or sent else job.updated_at
    from api.job_os.applications import FOLLOW_UP_DAYS

    quiet = max(0, (now - last) // 86400)
    row = _row(job.id)
    draft = None
    if row is not None and row["status"] in ("running", "done", "failed"):
        # A status change after the draft (a reply moved the job) retires it.
        if row["status"] == "running" or row["updated_at"] >= max(moved or [0]):
            draft = {"status": row["status"], "error": row["error"], **json.loads(row["draft_json"] or "{}")}
    return {"quiet_days": int(quiet), "due": quiet >= FOLLOW_UP_DAYS, "sent": len(sent),
            "max_reached": len(sent) >= MAX_FOLLOW_UPS, "draft": draft}


def _save(job_id: str, status: str, *, draft: dict | None = None, error: str = "", model: str = "") -> None:
    conn = connect_job_os()
    try:
        conn.execute(
            "INSERT INTO follow_ups (job_id, status, draft_json, error, model, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, draft_json=CASE WHEN excluded.draft_json='{}'"
            " THEN follow_ups.draft_json ELSE excluded.draft_json END, error=excluded.error, model=excluded.model,"
            " updated_at=excluded.updated_at",
            (job_id, status, json.dumps(draft or {}), error[:300], model, int(time.time())))
        conn.commit()
    finally:
        conn.close()


def _sent_documents(job_id: str) -> str:
    from api.job_os.tailor import latest_documents

    docs = latest_documents(job_id)
    parts = []
    for kind, label in (("resume", "RESUME"), ("cover_letter", "COVER LETTER")):
        doc = docs.get(kind)
        if doc and doc.get("status") in ("ready", "needs_review") and doc.get("content"):
            parts.append(f"<<<SENT {label}\n{doc['content'][:9000]}\nSENT {label}>>>")
    if not parts:
        from api.job_os.resume import load_resume

        master = load_resume()
        if master:
            parts.append(f"<<<SENT RESUME\n{master['text'][:9000]}\nSENT RESUME>>>")
    return "\n\n".join(parts)


def clean(data: dict, sent_text: str) -> dict:
    from api.job_os.tailor import unverified_numbers

    body = str(data.get("body") or "").strip()
    if len(body.split()) < 20:
        raise llm.LLMError("The follow-up came back empty.")
    channel = str(data.get("channel") or "").lower()
    channel = channel if channel in CHANNELS else "email"
    subject = str(data.get("subject") or "").strip()[:160] if channel == "email" else ""
    return {"channel": channel, "subject": subject, "body": body[:2000], "words": len(body.split()),
            "unverified": unverified_numbers(body, sent_text)}


def generate(job_id: str) -> dict | None:
    from api.job_os.analysis import posting_text
    from api.job_os.settings import load_settings

    try:
        job = get_job(job_id)
        if job is None:
            raise llm.LLMError("The job is no longer available.")
        sent = _sent_documents(job_id)
        name = load_settings()["applicant"].get("full_name") or "the candidate"
        channel = "linkedin" if "linkedin.com" in job.canonical_url else "email"
        user = (f"Candidate: {name}\nApplied for: {job.title} at {job.company or 'the company'}\n"
                f"Preferred channel: {channel}\nContact: not known\n\n<<<POSTING\n{posting_text(job)[:8000]}\nPOSTING>>>\n\n{sent}")
        data, model = llm.ask_json(SYSTEM, user, max_tokens=1500)
        _save(job_id, "done", draft=clean(data, sent + "\n" + job.description), model=model)
    except Exception as error:  # you can still write it yourself
        message = str(error) if isinstance(error, llm.LLMError) else f"Drafting failed ({type(error).__name__})."
        _save(job_id, "failed", error=message)
    job = get_job(job_id)
    return state(job) if job else None


def request(job_id: str, *, run_async: bool = True) -> dict | None:
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    current = state(job)
    if current is None:
        raise FollowUpError("Follow-ups are for applications waiting on a reply.")
    if current["max_reached"]:
        raise FollowUpError("You have followed up twice already; consider marking it no response.")
    if current["draft"] and current["draft"]["status"] == "running":
        return current
    _save(job_id, "running")
    if run_async:
        threading.Thread(target=generate, args=(job_id,), name=f"job-os-followup-{job_id[:8]}", daemon=True).start()
        return state(get_job(job_id))
    return generate(job_id)


def mark_sent(job_id: str) -> dict | None:
    """Record that you sent a follow-up: logged, and the quiet clock restarts."""
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    current = state(job)
    if current is None:
        raise FollowUpError("Follow-ups are for applications waiting on a reply.")
    if current["max_reached"]:
        raise FollowUpError("Two follow-ups are already logged for this application.")
    now = int(time.time())
    conn = connect_job_os()
    try:
        conn.execute("INSERT INTO job_events (id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                     (str(uuid.uuid4()), job_id, "follow_up_sent",
                      json.dumps({"n": current["sent"] + 1, "channel": (current["draft"] or {}).get("channel", "")}), now))
        conn.execute("UPDATE follow_ups SET status='sent', updated_at=? WHERE job_id=?", (now, job_id))
        conn.commit()
    finally:
        conn.close()
    return state(get_job(job_id))


def stale(days: int = STALE_DAYS, *, now: int | None = None) -> list[dict]:
    """Applications with no news for ``days`` or more, quietest first."""
    from api.job_os.repository import list_jobs

    now = int(time.time()) if now is None else now
    out = []
    for job in list_jobs():
        info = state(job, now=now)
        if info and info["quiet_days"] >= days:
            out.append({"id": job.id, "title": job.title, "company": job.company, "status": job.status.value,
                        "revision": job.revision, "quiet_days": info["quiet_days"], "follow_ups": info["sent"]})
    return sorted(out, key=lambda j: -j["quiet_days"])


def sweep(job_ids: list[str]) -> dict:
    """Move the chosen quiet applications to No response, one logged move each."""
    from api.job_os.applications import move_to_column

    moved, skipped = 0, 0
    for job_id in dict.fromkeys(str(i) for i in job_ids):
        job = get_job(job_id)
        if job is None or job.status.value not in WAITING:
            skipped += 1
            continue
        try:
            move_to_column(job_id, "closed", expected_revision=job.revision, status="no_response",
                           payload={"by": "sweep"})
            moved += 1
        except Exception:
            logger.debug("stale sweep skipped %s", job_id, exc_info=True)
            skipped += 1
    return {"moved": moved, "skipped": skipped}
