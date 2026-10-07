"""Apply kit: everything to apply for one job by hand, quickly.

Automated applying is not offered (LinkedIn's and Indeed's terms forbid it, and
it means handing a session to a third party), so Hermes prepares the rest:
the tailored resume and cover letter (Resume Studio), and ready-to-paste
answers to the usual screening questions, written by Luna from the job, the
master resume and the person's standard answers (Settings -> Application
answers), which it uses word for word. The person opens the posting, pastes,
submits, and records the application.

One kit per job (``apply_kits``); generating runs in the background.
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

QUESTIONS = (
    "Why are you interested in this role?",
    "Why this company?",
    "How many years of relevant experience do you have?",
    "Which of your skills match this role best?",
    "What is your notice period?",
    "What are your salary expectations?",
    "Are you authorised to work in this country, or do you need sponsorship?",
    "Are you willing to relocate?",
    "Which languages do you speak?",
)
PROFILE_LABELS = {"notice_period": "Notice period", "expected_salary": "Expected salary",
                  "work_authorization": "Work authorisation", "years_experience": "Years of experience",
                  "relocation": "Relocation", "languages": "Languages", "other": "Other notes"}
SYSTEM = (
    "You prepare a candidate's answers to job application screening questions. Return ONLY JSON: "
    '{"answers": [{"question": "<question>", "answer": "<answer>"}]}\n'
    "Answer each question given, in order, in the first person, ready to paste: one to three sentences, "
    "plain text, no placeholders like [Company]. Use the candidate's stated answers exactly when one applies "
    "(notice period, salary, work authorisation, relocation, languages); for salary, keep the stated figure "
    "and only add the job's currency if the stated answer lists one for that country. When the candidate gave "
    "no answer for a question, write exactly \"Not provided — fill in before sending\". Take experience and "
    "skills only from the resume; never invent employers, titles, numbers or certifications. " + llm.UNTRUSTED
)


class ApplyKitError(ValueError):
    """The kit can't be prepared (HTTP 400)."""


def get_kit(job_id: str) -> dict | None:
    conn = connect_job_os()
    try:
        row = conn.execute("SELECT * FROM apply_kits WHERE job_id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"status": row["status"], "answers": json.loads(row["answers_json"] or "[]"), "error": row["error"],
            "updated_at": row["updated_at"]}


def _save(job_id: str, status: str, *, answers: list | None = None, error: str = "", model: str = "") -> None:
    conn = connect_job_os()
    try:
        conn.execute(
            "INSERT INTO apply_kits (job_id, status, answers_json, error, model, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, answers_json=CASE WHEN excluded.answers_json='[]'"
            " THEN apply_kits.answers_json ELSE excluded.answers_json END, error=excluded.error, model=excluded.model,"
            " updated_at=excluded.updated_at",
            (job_id, status, json.dumps(answers or []), error[:300], model, int(time.time())))
        conn.commit()
    finally:
        conn.close()


def _clean(data: dict) -> list[dict]:
    answers = data.get("answers") if isinstance(data, dict) else None
    out = []
    for item in answers if isinstance(answers, list) else []:
        if isinstance(item, dict) and str(item.get("question") or "").strip() and str(item.get("answer") or "").strip():
            out.append({"question": str(item["question"]).strip()[:200], "answer": str(item["answer"]).strip()[:1200]})
    if not out:
        raise llm.LLMError("Luna returned no answers.")
    return out[:15]


def generate(job_id: str) -> dict:
    """Write the answers now (the background unit of work). Returns the kit."""
    from api.job_os.analysis import posting_text
    from api.job_os.resume import load_resume
    from api.job_os.settings import load_settings

    try:
        job, resume = get_job(job_id), load_resume()
        if job is None or resume is None:
            raise llm.LLMError("The job or the master resume is no longer available.")
        profile = load_settings()["apply"]
        stated = "\n".join(f"{PROFILE_LABELS[k]}: {v}" for k, v in profile.items() if v) or "(none given)"
        user = ("Questions:\n" + "\n".join(f"- {q}" for q in QUESTIONS)
                + f"\n\nCandidate's stated answers:\n{stated}\n\nJob country: {job.country or 'unknown'}"
                + f"\n\n<<<POSTING\n{posting_text(job)}\nPOSTING>>>\n\n<<<RESUME\n{resume['text'][:14000]}\nRESUME>>>")
        data, model = llm.ask_json(SYSTEM, user, max_tokens=3000)
        _save(job_id, "done", answers=_clean(data), model=model)
    except Exception as error:  # the posting can still be applied for by hand
        message = str(error) if isinstance(error, llm.LLMError) else f"Preparing the answers failed ({type(error).__name__})."
        _save(job_id, "failed", error=message)
    return get_kit(job_id)


def request(job_id: str, *, run_async: bool = True) -> dict:
    from api.job_os.resume import load_resume

    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if not job.description:
        raise ApplyKitError("This job has no description yet.")
    if not load_resume():
        raise ApplyKitError("Upload your master resume in Resume Studio first.")
    current = get_kit(job_id)
    if current and current["status"] == "running":
        return current
    _save(job_id, "running")
    if run_async:
        threading.Thread(target=generate, args=(job_id,), name=f"job-os-applykit-{job_id[:8]}", daemon=True).start()
        return get_kit(job_id)
    return generate(job_id)
