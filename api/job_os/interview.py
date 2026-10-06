"""Luna interview preparation for a job you are interviewing for.

On request (job detail -> Prepare for interview), Luna reads the posting, your
master resume and the tailored resume you sent, and returns: likely questions
with an answer outline drawn only from your own experience, STAR stories
to rehearse, questions to ask them, and what to research. Answers that the
resume can't support are flagged instead of invented.

One request at a time, queued in ``interview_preps`` and run by one worker,
like analysis.
"""

from __future__ import annotations

import json
import logging
import threading
import time

from api.job_os import llm
from api.job_os.db import connect_job_os
from api.job_os.repository import get_job

logger = logging.getLogger(__name__)
STAGES = ("screening", "interviewing", "offer")
_lock = threading.Lock()
_worker: threading.Thread | None = None
_recovered = False

SYSTEM = (
    "You are an interview coach. Prepare the candidate for interviews for one job. Return ONLY JSON:\n"
    '{"questions": [{"question": "...", "why": "<what they are probing>", "outline": "<answer outline from the resume>", '
    '"supported": true|false}], "stories": [{"title": "...", "situation": "...", "action": "...", "result": "...", '
    '"use_for": "<which questions>"}], "ask_them": ["..."], "research": ["..."], "watch_outs": ["..."]}\n'
    "6-8 questions mixing role-specific, technical and behavioural; 3-4 STAR stories; 4-5 questions to ask; "
    "3-5 research points; up to 3 watch-outs (gaps the interviewer may probe). Outlines and stories must use ONLY "
    "experience present in the resume; if the resume has no evidence for a question, set supported=false and say "
    "what to prepare instead. Never invent employers, numbers or projects. " + llm.UNTRUSTED
)


class InterviewError(ValueError):
    """Prep can't be requested (HTTP 400)."""


def _clean(data: dict) -> dict:
    def text(value, limit=400):
        return str(value or "").strip()[:limit]

    def items(key, limit=8):
        values = data.get(key) if isinstance(data.get(key), list) else []
        return [v for v in values if v][:limit]

    questions = [{"question": text(q.get("question"), 240), "why": text(q.get("why"), 240), "outline": text(q.get("outline"), 700),
                  "supported": q.get("supported") is not False}
                 for q in items("questions") if isinstance(q, dict) and text(q.get("question"))]
    stories = [{k: text(s.get(k), 500) for k in ("title", "situation", "action", "result", "use_for")}
               for s in items("stories", 5) if isinstance(s, dict) and text(s.get("title"))]
    if not questions:
        raise llm.LLMError("The interview prep had no questions.")
    return {"questions": questions, "stories": stories,
            **{k: [text(v, 240) for v in items(k, 6) if isinstance(v, str)] for k in ("ask_them", "research", "watch_outs")}}


def to_markdown(job, data: dict) -> str:
    lines = [f"# Interview prep — {job.title}" + (f" at {job.company}" if job.company else ""), "", "## Likely questions"]
    for q in data.get("questions", []):
        lines += [f"### {q['question']}", f"*{q['why']}*" if q["why"] else "", ("" if q["supported"] else "**Prepare:** ") + q["outline"], ""]
    if data.get("stories"):
        lines.append("## Stories to rehearse")
        for s in data["stories"]:
            lines += [f"### {s['title']}", f"- **Situation:** {s['situation']}", f"- **Action:** {s['action']}",
                      f"- **Result:** {s['result']}", f"- **Use for:** {s['use_for']}", ""]
    for key, title in (("ask_them", "Questions to ask them"), ("research", "Research before the call"), ("watch_outs", "Watch-outs")):
        if data.get(key):
            lines += [f"## {title}"] + [f"- {item}" for item in data[key]] + [""]
    return "\n".join(line for line in lines if line is not None)


def get_prep(job_id: str) -> dict | None:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT * FROM interview_preps WHERE job_id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"job_id": row["job_id"], "status": row["status"], "error": row["error"], "model": row["model"],
            "requested_at": row["requested_at"], "finished_at": row["finished_at"], **json.loads(row["data_json"] or "{}")}


def request_prep(job_id: str, *, start_worker: bool = True) -> dict:
    from api.job_os.resume import load_resume

    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status.value not in STAGES:
        raise InterviewError("Interview prep is for jobs at screening, interviewing or offer.")
    if not load_resume():
        raise InterviewError("Upload your resume in Resume Studio first.")
    current = get_prep(job_id)
    if current and current["status"] in ("pending", "running"):
        return current
    conn = connect_job_os()
    try:
        conn.execute("INSERT INTO interview_preps (job_id, status, requested_at) VALUES (?, 'pending', ?)"
                     " ON CONFLICT(job_id) DO UPDATE SET status='pending', error='', requested_at=excluded.requested_at, finished_at=NULL",
                     (job_id, int(time.time())))
        conn.commit()
    finally:
        conn.close()
    if start_worker:
        ensure_worker()
    return get_prep(job_id)


def prepare_one(job_id: str) -> dict | None:
    from api.job_os.resume import load_resume
    from api.job_os.tailor import latest_documents

    conn = connect_job_os()
    try:
        conn.execute("UPDATE interview_preps SET status='running' WHERE job_id=?", (job_id,))
        conn.commit()
    finally:
        conn.close()
    job, resume = get_job(job_id), load_resume()
    try:
        if job is None or resume is None:
            raise llm.LLMError("The job or the resume is no longer available.")
        sent = (latest_documents(job_id).get("resume") or {}).get("content") or ""
        posting = f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n\n{job.description[:12000]}"
        user = (f"<<<POSTING\n{posting}\nPOSTING>>>\n\n<<<RESUME\n{resume['text'][:12000]}\nRESUME>>>"
                + (f"\n\n<<<SENT_RESUME\n{sent[:8000]}\nSENT_RESUME>>>" if sent else ""))
        data, model = llm.ask_json(SYSTEM, user, max_tokens=4000)
        result = _clean(data)
        result["markdown"] = to_markdown(job, result)
        conn = connect_job_os()
        try:
            conn.execute("UPDATE interview_preps SET status='done', data_json=?, model=?, error='', finished_at=? WHERE job_id=?",
                         (json.dumps(result), model, int(time.time()), job_id))
            conn.commit()
        finally:
            conn.close()
    except Exception as error:
        message = str(error) if isinstance(error, llm.LLMError) else f"Interview prep failed ({type(error).__name__})."
        conn = connect_job_os()
        try:
            conn.execute("UPDATE interview_preps SET status='failed', error=?, finished_at=? WHERE job_id=?",
                         (message[:300], int(time.time()), job_id))
            conn.commit()
        finally:
            conn.close()
    return get_prep(job_id)


def _next_pending() -> str | None:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT job_id FROM interview_preps WHERE status='pending' ORDER BY requested_at LIMIT 1").fetchone()
        return row["job_id"] if row else None
    finally:
        conn.close()


def _work() -> None:
    global _worker
    try:
        while True:
            job_id = _next_pending()
            if job_id is None:
                return
            prepare_one(job_id)
    except Exception:
        logger.debug("interview prep worker stopped", exc_info=True)
    finally:
        with _lock:
            _worker = None
        if _next_pending():
            ensure_worker()


def ensure_worker() -> None:
    global _worker, _recovered
    with _lock:
        if not _recovered:  # preps left 'running' by a restart go back in the queue
            _recovered = True
            conn = connect_job_os()
            try:
                conn.execute("UPDATE interview_preps SET status='pending' WHERE status='running'")
                conn.commit()
            finally:
                conn.close()
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_work, name="job-os-interview", daemon=True)
        _worker.start()
