"""Resume Studio tailoring: a job-specific resume and cover letter from the master resume.

Luna may rephrase, reorder, select and emphasise -- never invent -- and keeps
the master resume's layout (its sections, header and entry lines), so the
export in the master's design (resume_style.py) reads like the original. Two guards
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

# The method follows the resume-tailoring skill (github.com/amanattar/resume-tailoring-skill,
# MIT): a success profile from the posting, every resume bullet matched to it
# (direct / transferable / adjacent / gap), truthful reframing, gaps reported
# rather than papered over. Its interactive checkpoints become the report in
# Resume Studio; the questions stand in for its experience-discovery interview.
SYSTEM = (
    "You tailor a candidate's master resume to one job and write a cover letter, using a truth-preserving method.\n"
    "1. Success profile: from the posting, the core requirements (must-haves), the valued capabilities, and a "
    "terminology map from the candidate's wording to the posting's (only where the meaning is the same).\n"
    "2. Match: judge every experience and project bullet against the profile as direct (same skill, same domain), "
    "transferable (same capability, different context), adjacent (related tools or problems) or weak. Lead each "
    "section with the strongest; shorten or drop weak bullets rather than padding.\n"
    "3. Reframe truthfully: align keywords (the posting's term for the same thing), shift emphasis (same facts, the "
    "relevant aspect first), adjust the level of technical detail, highlight the relevant scale. A job title may take "
    "its standard industry form but never a higher seniority; company names and dates stay exact.\n"
    "4. Gaps: a requirement the resume cannot support stays out of the resume; list it with a recommendation.\n"
    "5. Layout: the master resume is given in Markdown. Keep its layout exactly: the same header lines in the same "
    "order ('# Name', the bold headline line if there is one, the contact line with the same separators), the same "
    "'## ' section headings word for word and in the same order, the same '### Title | Company | Place | Dates' entry "
    "lines, '**Label:** text' lines where the master has them, '- ' bullets, and about the same length. Only the "
    "wording and selection inside the sections change.\n"
    "6. Verified skills: when a VERIFIED SKILLS block is given, those are skills the candidate has confirmed they "
    "learned (courses, bootcamps, certifications) after writing the master resume. Add a verified skill to the resume's "
    "existing skills section (in its format) only when the posting asks for it or something equivalent; never claim "
    "experience, projects or results with it, and never add a verified skill the posting does not need.\n"
    "Hard rules: use ONLY facts in the master resume (and the VERIFIED SKILLS, as in step 6). You may rephrase, reorder, select, merge and emphasise; never add "
    "employers, titles, dates, numbers, degrees, certifications, tools or achievements that are not in it. Keep every "
    "date and number exactly as written. Cover letter: plain text, 180-320 words, specific to this company and role, "
    "no placeholders like [Company].\n"
    "Return ONLY JSON:\n"
    '{"profile": {"core": ["<must-have>"], "valued": ["<nice-to-have>"], "terms": [{"from": "<resume wording>", "to": "<posting wording>"}]}, '
    '"mapping": {"direct": <bullets>, "transferable": <bullets>, "adjacent": <bullets>, "gaps": <requirements not covered>}, '
    '"resume_markdown": "<the tailored resume in the master\'s layout>", "cover_letter": "<text>", '
    '"changes": [{"what": "<edit made>", "why": "<which posting need it serves>"}], '
    '"reframings": [{"original": "<master wording>", "reframed": "<new wording>", "why": "<why it is still true>"}], '
    '"gaps": [{"need": "<requirement>", "advice": "<cover letter angle, or what to add if it is true>"}], '
    '"questions": ["<question for the candidate that could surface real, unlisted experience for a gap>"], '
    '"skills_added": ["<verified skill you added, exactly as given>"]}\n'
    "Up to 6 items in each list, 8 changes. " + llm.UNTRUSTED
)

_NUMBER = re.compile(r"(?<![\w.])(\d[\d,.]*\s?%?|[€$£]\s?\d[\d,.]*\s?[kKmM]?)(?![\w])")


def _verified_skills() -> list[str]:
    """Skills the user listed under Dashboard > Career > Skills gained."""
    try:
        from api.dashboard_game import skill_names

        return [name for name in skill_names() if name.strip()][:60]
    except Exception:
        logger.debug("verified skills unavailable", exc_info=True)
        return []


def skills_added(tailored: str, master: str, verified: list[str]) -> list[str]:
    """Which verified skills the tailored resume names that the master did not:
    decided from the text itself, not from what the model says it did."""
    def norm(text: str) -> str:
        return re.sub(r"\s+", " ", text.lower())

    tailored_n, master_n = norm(tailored), norm(master)
    out = []
    for name in verified:
        n = norm(name).strip()
        if not n:
            continue
        pattern = r"(?<![\w])" + re.escape(n) + r"(?![\w])"
        if re.search(pattern, tailored_n) and not re.search(pattern, master_n):
            out.append(name)
    return out


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


# A rescore runs on a thread of this process: one still marked 'running' from
# before this module loaded died with the old process and will never finish.
_LOADED_AT = int(time.time())


def _settle_orphaned_fit(notes: dict) -> dict:
    fit = notes.get("tailored_fit")
    if isinstance(fit, dict) and fit.get("status") == "running" and int(fit.get("at") or 0) < _LOADED_AT:
        notes = {**notes, "tailored_fit": {"status": "failed", "error": "Scoring was interrupted by a restart. Score it again."}}
    return notes


def _doc_row(row) -> dict:
    return {"id": row["id"], "job_id": row["job_id"], "kind": row["kind"], "status": row["status"],
            "content": row["content"], "notes": _settle_orphaned_fit(json.loads(row["notes_json"] or "{}")), "error": row["error"],
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
    """Start tailoring for a job with a description (shortlisting it first if needed)."""
    from api.job_os.lifecycle import transition_job
    from api.job_os.resume import load_resume

    if not load_resume():
        raise TailorError("Upload your master resume in Resume Studio first.")
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if not job.description:
        raise TailorError("This job has no description yet; fetch its details first.")
    if job.status in (JobStatus.SCRAPED, JobStatus.ANALYZED):
        job = transition_job(job_id, JobStatus.SHORTLISTED, expected_revision=job.revision)
    if job.status in (JobStatus.RESUME_READY, JobStatus.APPLICATION_READY):
        job = transition_job(job_id, JobStatus.SHORTLISTED, expected_revision=job.revision)  # re-tailor
    if job.status != JobStatus.SHORTLISTED:
        if job.status == JobStatus.TAILORING:
            return {"job_id": job_id, "status": "tailoring"}
        raise TailorError("Add the job to Favorite before tailoring.")
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
        from api.job_os.export import text_markdown

        layout = text_markdown(master["text"])[:18000]
        verified = _verified_skills()
        skills_block = ("\n\n<<<VERIFIED SKILLS\n" + "\n".join(f"- {name}" for name in verified) + "\nVERIFIED SKILLS>>>") if verified else ""
        data, model = llm.ask_json(SYSTEM, f"{contact}\n\n<<<POSTING\n{posting}\nPOSTING>>>\n\n<<<MASTER RESUME\n{layout}\nMASTER RESUME>>>{skills_block}",
                                   max_tokens=9000)
        tailored = str(data.get("resume_markdown") or "").strip()
        letter = str(data.get("cover_letter") or "").strip()
        if len(tailored) < 200:
            raise llm.LLMError("The tailored resume came back empty.")
        allowed_numbers = master["text"] + " " + json.dumps(applicant) + " " + " ".join(verified)
        flags_resume = unverified_numbers(tailored, allowed_numbers)
        flags_letter = unverified_numbers(letter, allowed_numbers)
        changes = [{"what": str(c.get("what") or "")[:200], "why": str(c.get("why") or "")[:200]}
                   for c in (data.get("changes") or []) if isinstance(c, dict)][:8]
        coverage = keyword_coverage(tailored, analysis.get("must_haves") or [])
        set_doc(resume_doc, status="needs_review" if flags_resume else "ready", content=tailored[:30000], model=model, error="",
                notes_json=json.dumps({"changes": changes, "unverified": flags_resume, "coverage": coverage,
                                       "skills_added": skills_added(tailored, master["text"], verified),
                                       "report": _report(data),
                                       "master_revision": master.get("revision"),
                                       "master_fit": analysis.get("fit_score"),
                                       "tailored_fit": _fit_of(job, tailored)}))
        set_doc(letter_doc, status="needs_review" if flags_letter else "ready", content=letter[:8000], model=model, error="",
                notes_json=json.dumps({"unverified": flags_letter}))
        finish_job(JobStatus.RESUME_READY)
    except Exception as error:
        message = str(error) if isinstance(error, llm.LLMError) else f"Tailoring failed ({type(error).__name__})."
        for doc in (resume_doc, letter_doc):
            set_doc(doc, status="failed", error=message[:300])
        finish_job(JobStatus.SHORTLISTED)
    return latest_documents(job_id)


def _report(data: dict) -> dict:
    """The tailoring method's working, cleaned for the Resume Studio report."""
    def text(value, limit=200):
        return str(value or "").strip()[:limit]

    def strings(value, limit=6):
        return [text(v, 160) for v in (value if isinstance(value, list) else []) if text(v)][:limit]

    def pairs(value, keys, limit=6):
        rows = value if isinstance(value, list) else []
        return [{k: text(row.get(k)) for k in keys} for row in rows if isinstance(row, dict) and text(row.get(keys[0]))][:limit]
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    raw = data.get("mapping") if isinstance(data.get("mapping"), dict) else {}
    mapping = {}
    for key in ("direct", "transferable", "adjacent", "gaps"):
        try:
            mapping[key] = max(0, min(99, int(raw.get(key) or 0)))
        except (TypeError, ValueError):
            mapping[key] = 0
    return {"core": strings(profile.get("core")), "valued": strings(profile.get("valued")),
            "terms": pairs(profile.get("terms"), ("from", "to")), "mapping": mapping,
            "reframings": pairs(data.get("reframings"), ("original", "reframed", "why")),
            "gaps": pairs(data.get("gaps"), ("need", "advice")), "questions": strings(data.get("questions"), 5)}


def _fit_of(job, text: str) -> dict:
    """The tailored resume's fit, scored like the master's; a failed scoring is
    recorded rather than failing the tailoring."""
    from api.job_os.analysis import score_text

    try:
        result = score_text(job, text)
        return {"status": "done", "fit_score": result["fit_score"], "summary": result["summary"], "at": int(time.time())}
    except Exception as error:  # the tailored resume is still usable without its score
        return {"status": "failed", "error": (str(error) if isinstance(error, llm.LLMError) else type(error).__name__)[:200]}


def rescore_document(doc_id: str, *, run_async: bool = True) -> dict:
    """Score the tailored resume again (after edits), in the background."""
    doc = get_document(doc_id)
    if doc is None:
        raise KeyError(doc_id)
    if doc["kind"] != "resume" or doc["status"] not in ("ready", "needs_review"):
        raise TailorError("Only a finished tailored resume can be scored.")
    job = get_job(doc["job_id"])
    if job is None or not job.description:
        raise TailorError("The job has no description to score against.")

    def write(fit: dict) -> None:
        conn = connect_job_os()
        try:
            row = conn.execute("SELECT notes_json FROM job_documents WHERE id=?", (doc_id,)).fetchone()
            notes = json.loads((row["notes_json"] if row else None) or "{}")
            notes["tailored_fit"] = fit
            conn.execute("UPDATE job_documents SET notes_json=?, updated_at=? WHERE id=?", (json.dumps(notes), int(time.time()), doc_id))
            conn.commit()
        finally:
            conn.close()

    write({"status": "running", "at": int(time.time())})
    work = lambda: write(_fit_of(job, doc["content"]))  # noqa: E731
    if run_async:
        threading.Thread(target=work, name=f"job-os-rescore-{doc_id[:8]}", daemon=True).start()
    else:
        work()
    return get_document(doc_id)


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
    if isinstance(notes.get("tailored_fit"), dict) and text != doc["content"]:
        notes["tailored_fit"] = {**notes["tailored_fit"], "stale": True}  # scored before these edits
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


def resume_if_stalled() -> None:
    """Restart tailoring if documents are waiting and no worker is running (a
    restart leaves them 'running' with no thread behind them)."""
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
    conn = connect_job_os()
    try:
        waiting = conn.execute("SELECT 1 FROM job_documents WHERE status IN ('pending', 'running') LIMIT 1").fetchone()
    finally:
        conn.close()
    if waiting:
        ensure_worker()


def ensure_worker() -> None:
    global _worker
    with _lock:
        _requeue_orphans()
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_work, name="job-os-tailor", daemon=True)
        _worker.start()
