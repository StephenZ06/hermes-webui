"""Skill-gap report: the gaps of every analysed job, added up.

Each analysis lists the posting's must-haves and the gaps the resume doesn't
cover; one job's gaps say little, but the same gap across twenty jobs is a
plan. The report counts them (near-identical wording merged), optionally only
for good matches or a recent window, then one Luna call groups them by theme
and suggests a short learning plan. No study links: they would be invented
without web search.

The last 5 reports are kept (``skill_gaps.json``); each shows what changed
since the one before: new gaps, and gaps that no longer appear.

Adapted from ai-job-search's ``/upskill`` aggregate mode
(github.com/ai-job-search-dev/ai-job-search, MIT).
"""

from __future__ import annotations

import json
import re
import threading
import time

from api.job_os.paths import job_os_state_dir

KEEP = 5
TOP = 25
_STOP = {"and", "or", "the", "with", "of", "in", "to", "a", "an", "for", "experience", "years", "year", "strong",
         "knowledge", "ability", "skills", "skill", "using", "including", "plus", "such", "as", "on", "at", "no",
         "not", "proven", "solid", "good", "excellent", "hands", "on", "required", "preferred", "familiarity",
         "understanding", "working", "proficiency", "proficient", "background", "level", "shown", "listed",
         "resume", "does", "doesn't", "mentioned", "evidence", "lacks", "missing", "direct"}


class SkillGapError(ValueError):
    """A report can't be built now (HTTP 400)."""


def key(text: str) -> frozenset:
    """The words that identify a gap, so near-identical wording merges."""
    words = re.findall(r"[a-z0-9+#.]+", str(text or "").lower())
    out = set()
    for word in words:
        word = word.strip(".")
        if not word or word in _STOP or word.isdigit():
            continue
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        out.add(word)
    return frozenset(out)


def _similar(a: frozenset, b: frozenset) -> bool:
    if not a or not b:
        return False
    # "Kubernetes" and "Kubernetes in production" are one gap; short phrases
    # merge when one contains the other, longer ones when most words match.
    return len(a & b) / len(a | b) >= 0.6 or ((a <= b or b <= a) and max(len(a), len(b)) <= 3)


def aggregate(*, good_only: bool = False, days: int = 0, now: int | None = None) -> dict:
    """Gaps and must-haves across analysed jobs, merged and counted."""
    from api.job_os.db import connect_job_os
    from api.job_os.settings import load_settings

    now = int(time.time()) if now is None else now
    floor = load_settings()["notifications"]["min_fit_score"] if good_only else -1
    since = now - days * 86400 if days else 0
    conn = connect_job_os()
    try:
        rows = conn.execute("SELECT a.job_id, a.fit_score, a.data_json, a.finished_at FROM job_analyses a"
                            " WHERE a.status='done'").fetchall()
    finally:
        conn.close()
    groups: list[dict] = []
    jobs = 0
    for row in rows:
        if (row["fit_score"] if row["fit_score"] is not None else -1) < floor or (row["finished_at"] or 0) < since:
            continue
        try:
            data = json.loads(row["data_json"] or "{}")
        except ValueError:
            continue
        jobs += 1
        for field, counter in (("gaps", "gap"), ("must_haves", "asked")):
            seen_here: set[int] = set()
            for text in data.get(field) or []:
                k = key(text)
                if not k:
                    continue
                group = next((g for g in groups if _similar(g["key"], k)), None)
                if group is None:
                    group = {"key": k, "label": str(text).strip()[:120], "gap": 0, "asked": 0, "jobs": set()}
                    groups.append(group)
                index = groups.index(group)
                if index in seen_here:  # one job counts once per gap
                    continue
                seen_here.add(index)
                group[counter] += 1
                group["jobs"].add(row["job_id"])
    ranked = sorted((g for g in groups if g["gap"]), key=lambda g: (-g["gap"], -g["asked"], g["label"]))
    return {"jobs": jobs, "gaps": [{"label": g["label"], "gap": g["gap"], "asked": g["asked"],
                                    "key": sorted(g["key"])} for g in ranked[:TOP]]}


def _path():
    return job_os_state_dir() / "skill_gaps.json"


def load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"reports": []}
    return data if isinstance(data, dict) and isinstance(data.get("reports"), list) else {"reports": []}


def _save(data: dict) -> None:
    import os
    import tempfile

    path = _path()
    fd, tmp = tempfile.mkstemp(prefix=".skill-gaps-", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.replace(tmp, path)


def diff(new: list[dict], old: list[dict]) -> dict:
    """Gaps that appeared since the previous report, and ones that went away."""
    old_keys = [frozenset(g["key"]) for g in old]
    new_keys = [frozenset(g["key"]) for g in new]
    added = [g["label"] for g, k in zip(new, new_keys) if not any(_similar(k, o) for o in old_keys)]
    closed = [g["label"] for g, k in zip(old, old_keys) if not any(_similar(k, n) for n in new_keys)]
    return {"new": added[:10], "closed": closed[:10]}


SYSTEM = (
    "You turn a job seeker's recurring skill gaps into a short plan. The list shows each gap and in how many analysed "
    "job postings it appeared. Return ONLY JSON: {\"themes\": [{\"name\": \"<theme>\", \"gaps\": [\"<gap label as "
    "given>\"], \"why\": \"<why it matters for these jobs, one sentence>\"}], \"plan\": [{\"step\": \"<what to do>\", "
    "\"detail\": \"<how, in one or two sentences, without links>\"}]}\n"
    "Up to 5 themes and 5 plan steps, most frequent first. Use the gap labels exactly as given. No URLs or course "
    "names you are not sure exist."
)


def build(*, good_only: bool = False, days: int = 0) -> dict:
    """Aggregate, ask Luna to group and plan, and keep the report."""
    from api.job_os import llm

    totals = aggregate(good_only=good_only, days=days)
    if not totals["gaps"]:
        raise SkillGapError("No analysed jobs list any gaps yet. Score some jobs against your resume first.")
    lines = "\n".join(f"- {g['label']} (gap in {g['gap']}, asked in {g['asked']})" for g in totals["gaps"])
    data, model = llm.ask_json(SYSTEM, f"Analysed jobs: {totals['jobs']}\nGaps:\n{lines}", max_tokens=2000)
    labels = {g["label"] for g in totals["gaps"]}
    themes = []
    for theme in data.get("themes") or []:
        if isinstance(theme, dict) and str(theme.get("name") or "").strip():
            themes.append({"name": str(theme["name"]).strip()[:80],
                           "gaps": [str(x) for x in (theme.get("gaps") or []) if str(x) in labels][:8],
                           "why": str(theme.get("why") or "").strip()[:200]})
    plan = [{"step": str(p.get("step") or "").strip()[:120], "detail": re.sub(r"https?://\S+", "", str(p.get("detail") or "")).strip()[:300]}
            for p in (data.get("plan") or []) if isinstance(p, dict) and str(p.get("step") or "").strip()][:5]
    stored = load()
    previous = stored["reports"][0] if stored["reports"] else None
    report = {"created_at": int(time.time()), "jobs": totals["jobs"], "scope": {"good_only": good_only, "days": days},
              "gaps": totals["gaps"], "themes": themes[:5], "plan": plan, "model": model,
              "since_last": diff(totals["gaps"], previous["gaps"]) if previous else None}
    stored["reports"] = [report, *stored["reports"]][:KEEP]
    _save(stored)
    return report


def status() -> dict:
    data = load()
    return {"reports": data["reports"], "running": bool(data.get("running")), "error": data.get("error") or ""}


def request(*, good_only: bool = False, days: int = 0, run_async: bool = True) -> dict:
    data = load()
    if data.get("running"):
        return status()
    data["running"] = True
    data.pop("error", None)
    _save(data)

    def work():
        try:
            build(good_only=good_only, days=days)
        except Exception as error:
            stored = load()
            stored["error"] = str(error)[:300] if isinstance(error, SkillGapError) or "LLMError" in type(error).__name__ \
                else f"The report failed ({type(error).__name__})."
            _save(stored)
        finally:
            stored = load()
            stored.pop("running", None)
            _save(stored)
    if run_async:
        threading.Thread(target=work, name="job-os-skill-gaps", daemon=True).start()
    else:
        work()
    return status()
