"""Scoring weights: how much each dimension counts towards a job's fit score.

The defaults follow ai-job-search's evaluation rubric (skills 30, experience
25, culture 15, career 30). Calibration from outcomes can tune them; the
current set lives in ``calibration.json`` in the profile's Job OS state.

Adapted from ai-job-search (github.com/ai-job-search-dev/ai-job-search, MIT).
"""

from __future__ import annotations

import json

from api.job_os.paths import job_os_state_dir

DIMENSIONS = ("skills", "experience", "culture", "career")
DEFAULT_WEIGHTS = {"skills": 30, "experience": 25, "culture": 15, "career": 30}


def _path():
    return job_os_state_dir() / "calibration.json"


def load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def weights() -> dict:
    """The weights in use: the accepted calibration's, else the defaults."""
    current = (load().get("current") or {}).get("weights")
    if isinstance(current, dict) and all(isinstance(current.get(k), int) and 0 <= current[k] <= 100 for k in DIMENSIONS) \
            and sum(current.values()) > 0:
        return {k: current[k] for k in DIMENSIONS}
    return dict(DEFAULT_WEIGHTS)


def guidance() -> str:
    """A short note from calibration added to the scoring prompt (or "")."""
    return str((load().get("current") or {}).get("guidance") or "")[:600]


def weighted_score(dimensions: dict, weights_: dict | None = None) -> int | None:
    """The fit score from the dimension scores: a weighted average, with a
    missing culture score's weight shared out over the others."""
    weights_ = weights_ or weights()
    parts = [(dimensions.get(k), weights_[k]) for k in DIMENSIONS]
    present = [(v, w) for v, w in parts if isinstance(v, int)]
    total = sum(w for _v, w in present)
    if not present or total <= 0 or any(not isinstance(dimensions.get(k), int) for k in ("skills", "experience", "career")):
        return None
    return round(sum(v * w for v, w in present) / total)


# ---- Calibration from outcomes ------------------------------------------------
# Once 3 or more applications have a final outcome, one Luna call reads what
# was predicted for each (the dimension scores, the gates, the fit) next to what
# happened, and proposes bounded weight changes, a short note for the scoring
# prompt and the patterns it saw. Nothing changes until you accept; Undo puts
# the previous set back. Past scores are never edited.

MIN_OUTCOMES = 3
MAX_STEP = 10
OUTCOMES = {"rejected": "rejected", "screening": "interview", "interviewing": "interview", "offer": "offer",
            "offer_accepted": "offer", "offer_declined": "offer", "no_response": "no response"}
SYSTEM = (
    "You calibrate a job-fit scoring rubric from a candidate's real outcomes. Each line is one application: the "
    "dimension scores predicted (skills, experience, culture, career, 0-100), the fit score, and what happened. "
    "Return ONLY JSON: {\"weights\": {\"skills\": <int>, \"experience\": <int>, \"culture\": <int>, \"career\": <int>}, "
    "\"guidance\": \"<one or two sentences the scorer should keep in mind, under 300 characters>\", "
    "\"patterns\": [\"<pattern seen in these outcomes, under 140 characters>\"]}\n"
    "Change each current weight by at most 10 points, only where the outcomes support it; keep a weight when unsure. "
    "Up to 4 patterns. Base everything on the lines given; with few outcomes, say so and change little."
)


def _save(data: dict) -> None:
    import os
    import tempfile

    path = _path()
    fd, tmp = tempfile.mkstemp(prefix=".calibration-", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.replace(tmp, path)


def outcomes() -> list[dict]:
    """Applications with a final outcome, with what was predicted for each."""
    from api.job_os.analysis import analyses_by_job, get_analysis
    from api.job_os.repository import list_jobs

    scored = analyses_by_job()
    out = []
    for job in list_jobs():
        result = OUTCOMES.get(job.status.value)
        if not result:
            continue
        a = scored.get(job.id) or {}
        if a.get("status") != "done":
            continue
        full = get_analysis(job.id) or {}
        out.append({"job_id": job.id, "title": job.title, "company": job.company, "outcome": result,
                    "fit_score": a.get("fit_score"), "dimensions": full.get("dimensions"), "gates": full.get("gates")})
    return out


def bounded(proposed: dict, current: dict) -> dict:
    """Each weight moves at most MAX_STEP from the current one, within 0-100."""
    out = {}
    for key in DIMENSIONS:
        try:
            value = int(round(float(proposed.get(key))))
        except (TypeError, ValueError, AttributeError):
            value = current[key]
        out[key] = max(0, min(100, max(current[key] - MAX_STEP, min(current[key] + MAX_STEP, value))))
    if sum(out.values()) <= 0:
        return dict(current)
    return out


def status() -> dict:
    data = load()
    resolved = outcomes()
    current = data.get("current") or None
    since = (current or {}).get("outcomes", 0)
    return {"outcomes": len(resolved), "min_outcomes": MIN_OUTCOMES,
            # Offered again once three more outcomes are in since the last calibration.
            "offer": len(resolved) >= MIN_OUTCOMES and len(resolved) - since >= MIN_OUTCOMES and not data.get("proposal"),
            "weights": weights(), "default_weights": dict(DEFAULT_WEIGHTS), "current": current,
            "proposal": data.get("proposal"), "can_undo": bool(data.get("history")), "running": bool(data.get("running")),
            "error": data.get("error") or ""}


class CalibrationError(ValueError):
    """Calibration can't run now (HTTP 400)."""


def propose() -> dict:
    """One Luna call over the resolved applications; stores the proposal."""
    import time

    from api.job_os import llm

    resolved = outcomes()
    if len(resolved) < MIN_OUTCOMES:
        raise CalibrationError(f"Calibration needs at least {MIN_OUTCOMES} applications with an outcome.")
    current = weights()
    lines = []
    for item in resolved[:60]:
        dims = item["dimensions"] or {}
        lines.append(f"- {item['title'][:80]} at {item['company'][:60] or '?'}: skills {dims.get('skills', '?')}, "
                     f"experience {dims.get('experience', '?')}, culture {dims.get('culture', '?')}, career "
                     f"{dims.get('career', '?')}, fit {item['fit_score']} -> {item['outcome']}")
    data, model = llm.ask_json(SYSTEM, f"Current weights: {json.dumps(current)}\n\nApplications:\n" + "\n".join(lines),
                               max_tokens=1500)
    patterns = [str(p).strip()[:140] for p in (data.get("patterns") or []) if str(p).strip()][:4] \
        if isinstance(data.get("patterns"), list) else []
    proposal = {"weights": bounded(data.get("weights") if isinstance(data.get("weights"), dict) else {}, current),
                "guidance": str(data.get("guidance") or "").strip()[:300], "patterns": patterns,
                "outcomes": len(resolved), "model": model, "created_at": int(time.time())}
    stored = load()
    stored["proposal"] = proposal
    _save(stored)
    return status()


def accept() -> dict:
    import time

    data = load()
    proposal = data.get("proposal")
    if not proposal:
        raise CalibrationError("There is no proposal to accept.")
    history = list(data.get("history") or [])
    history.append(data.get("current"))  # None stands for the defaults
    version = int((data.get("current") or {}).get("version") or 0) + 1
    data["current"] = {"weights": proposal["weights"], "guidance": proposal["guidance"], "patterns": proposal["patterns"],
                       "outcomes": proposal["outcomes"], "version": version,
                       "date": time.strftime("%Y-%m-%d"), "accepted_at": int(time.time())}
    data["history"] = history[-10:]
    data.pop("proposal", None)
    _save(data)
    return status()


def discard() -> dict:
    data = load()
    data.pop("proposal", None)
    _save(data)
    return status()


def undo() -> dict:
    data = load()
    history = list(data.get("history") or [])
    if not history:
        raise CalibrationError("Nothing to undo.")
    data["current"] = history.pop()
    data["history"] = history
    if data["current"] is None:
        data.pop("current")
    _save(data)
    return status()


def request_proposal(*, run_async: bool = True) -> dict:
    """Start a proposal in the background (the page polls ``status``)."""
    import threading

    if len(outcomes()) < MIN_OUTCOMES:
        raise CalibrationError(f"Calibration needs at least {MIN_OUTCOMES} applications with an outcome.")
    data = load()
    if data.get("running"):
        return status()
    data["running"] = True
    data.pop("error", None)
    _save(data)

    def work():
        try:
            propose()
        except Exception as error:
            stored = load()
            stored["error"] = str(error)[:300] if isinstance(error, (CalibrationError,)) or "LLMError" in type(error).__name__ \
                else f"Calibration failed ({type(error).__name__})."
            _save(stored)
        finally:
            stored = load()
            stored.pop("running", None)
            _save(stored)
    if run_async:
        threading.Thread(target=work, name="job-os-calibration", daemon=True).start()
    else:
        work()
    return status()
