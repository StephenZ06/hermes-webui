"""Docs-Git assistance for the project starter wizard.

Two jobs run under the ``docs-gits`` profile:

* ``start_analysis`` reviews a project brief and returns the questions still
  needed to fill the template's instruction files.
* ``start_docs_setup`` works inside the project folder with Docs-Git's own
  tools, writing (new project) or adapting (existing project) the
  instruction files, and returns its summary.

Both are hidden, non-persistent (ephemeral) turns tracked as in-memory jobs
the wizard polls. A visible chat would live in the docs-gits profile, and
opening it would switch the user's whole UI to that profile.

The profile is never substituted: when it is missing the job fails with a
clear reason and the wizard carries on without Docs-Git.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

DOCS_PROFILE = "docs-gits"
_ANALYSIS_TIMEOUT_SECONDS = 240
_SETUP_TIMEOUT_SECONDS = 1200
_JOB_TTL_SECONDS = 1800
_MAX_QUESTIONS = 6

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def docs_profile_available() -> bool:
    try:
        from api.profiles import get_hermes_home_for_profile

        home = Path(get_hermes_home_for_profile(DOCS_PROFILE))
        return home.name == DOCS_PROFILE and (home / "config.yaml").is_file()
    except Exception:
        return False


def docs_agent_readiness() -> dict:
    """Can Docs-Git start? Checked before a run so the wizard can offer setup.

    Blocks only on a definite gap (no sign-in / no key / no model) with no
    usable fallback; routes Hermes can't verify from here are let through and
    the agent reports any problem itself.
    """
    if not docs_profile_available():
        return {"ready": False, "state": "missing", "provider": "",
                "message": "The Docs-Git profile is not set up."}
    from api.profile_providers import overview

    try:
        view = overview(DOCS_PROFILE)
    except Exception:
        return {"ready": True, "state": "unknown", "provider": "", "message": ""}
    main = view["main"]
    state = main["status"]["state"]
    if state not in {"signin", "key", "unset"}:
        return {"ready": True, "state": state, "provider": main["provider"], "message": main["status"]["message"]}
    if any(f["status"]["state"] == "ready" for f in view["fallbacks"]):
        return {"ready": True, "state": "fallback", "provider": main["provider"], "message": "Using a fallback model."}
    return {"ready": False, "state": state, "provider": main["provider"],
            "message": f"Docs-Git can't run yet: {main['status']['message']}"}


# ── Brief analysis ─────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """You are helping set up a new software project's instruction files.
Do not use any tools and do not create files. Reply with ONLY one JSON object:
{{"complete": true|false, "summary": "one sentence", "questions": [
  {{"id": "short_snake_id", "question": "...", "options": ["...", "..."],
    "recommended": "one of the options, copied exactly", "why": "one short reason tied to the brief"}}]}}

The project will be created from the "{template}" template, which writes these
files: {files}. To fill them well we need: what is being built and for whom, the
programming stack (languages, frameworks, data storage), how it is tested, and
how it is deployed or delivered (skip what does not apply to this template).

Set "complete" to true only when the brief already answers everything that
applies. Otherwise ask at most {max_questions} short questions, one per missing
fact, most important first. Give each question 3-6 concrete, mutually exclusive
options that suit the brief (the user can also type their own answer). For every
question, pick the option you would recommend for THIS project (its users,
scale, platform and constraints in the brief) as "recommended", and say why in
under 15 words as "why". Prefer mainstream, well-supported choices unless the
brief points elsewhere.

Project name: {name}
Brief:
<<<
{brief}
>>>"""


def _prune_jobs(now: float) -> None:
    for job_id in [k for k, v in _jobs.items() if now - v["created"] > _JOB_TTL_SECONDS]:
        _jobs.pop(job_id, None)


def start_analysis(*, name: str, brief: str, template: dict) -> str:
    """Start a background brief review; poll with ``get_job``."""
    prompt = _ANALYSIS_PROMPT.format(
        template=template.get("label") or template.get("key") or "blank",
        files=", ".join(template.get("files") or []),
        max_questions=_MAX_QUESTIONS,
        name=name or "Untitled project",
        brief=brief[:20000],
    )
    return _start_job("analysis", lambda: parse_analysis(_run_ephemeral_turn(prompt, timeout=_ANALYSIS_TIMEOUT_SECONDS)))


def _start_job(kind: str, work) -> str:
    job_id = uuid.uuid4().hex[:16]
    now = time.time()
    with _jobs_lock:
        _prune_jobs(now)
        _jobs[job_id] = {"status": "running", "kind": kind, "created": now}
    threading.Thread(target=_job_worker, args=(job_id, work), daemon=True).start()
    return job_id


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(str(job_id or ""))
        return {k: v for k, v in job.items() if k != "created"} if job else None


def _finish(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def _job_worker(job_id: str, work) -> None:
    try:
        _finish(job_id, status="done", result=work())
    except Exception as exc:  # reported to the wizard, which offers retry/skip
        logger.warning("Project starter Docs-Git job failed: %s", exc)
        _finish(job_id, status="error", error=str(exc) or "Docs-Git could not finish.")


def parse_analysis(text: str) -> dict:
    """Validate Docs-Git's JSON reply into the wizard's question format."""
    raw = str(text or "").strip()
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("Docs-Git did not return a readable review.")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Docs-Git did not return a readable review.")
    questions = []
    seen = set()
    for item in data.get("questions") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()[:300]
        options = [str(o).strip()[:120] for o in item.get("options") or [] if str(o).strip()][:6]
        qid = re.sub(r"[^a-z0-9_]+", "_", str(item.get("id") or question).lower()).strip("_")[:40] or f"q{len(questions) + 1}"
        if not question or qid in seen:
            continue
        seen.add(qid)
        recommended = str(item.get("recommended") or "").strip()
        match = next((o for o in options if o.casefold() == recommended.casefold()), "")
        entry = {"id": qid, "question": question, "options": options}
        if match:
            entry["recommended"] = match
            entry["why"] = str(item.get("why") or "").strip()[:160]
        questions.append(entry)
        if len(questions) >= _MAX_QUESTIONS:
            break
    return {
        "complete": bool(data.get("complete")) and not questions,
        "summary": str(data.get("summary") or "").strip()[:400],
        "questions": questions,
    }


def _profile_model(session) -> tuple[str | None, str | None]:
    from api.routes import _read_profile_model_config, _resolve_compatible_session_model_state

    provider, default_model, config = _read_profile_model_config(session, None)
    model, model_provider, _normalized = _resolve_compatible_session_model_state(
        None,
        None,
        profile_provider=provider,
        profile_default_model=default_model,
        profile_config=config,
        prefer_cached_catalog=True,
    )
    return model, model_provider


def _run_ephemeral_turn(prompt: str, *, timeout: float, workspace: str | None = None, title: str = "Docs-Git") -> str:
    """Run one hidden Docs-Git turn and return its final answer."""
    if not docs_profile_available():
        raise RuntimeError("The Docs-Git profile is not set up.")
    from api.models import new_session
    from api.routes import (
        STREAMS,
        STREAMS_LOCK,
        _run_agent_streaming,
        create_stream_channel,
        register_session_writeback_owner,
        register_stream_owner,
    )

    session = new_session(workspace=workspace, profile=DOCS_PROFILE)
    model, model_provider = _profile_model(session)
    session.model = model
    session.model_provider = model_provider
    session.title = title[:80]
    session.save()
    stream_id = uuid.uuid4().hex
    session.active_stream_id = stream_id
    register_session_writeback_owner(session.session_id, stream_id)
    session.save()
    channel = create_stream_channel()
    register_stream_owner(stream_id, session.session_id)
    with STREAMS_LOCK:
        STREAMS[stream_id] = channel
    events = channel.subscribe()
    worker = threading.Thread(
        target=_run_agent_streaming,
        args=(session.session_id, prompt, model, session.workspace, stream_id, None),
        kwargs={"ephemeral": True, "model_provider": model_provider},
        daemon=True,
    )
    worker.start()
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            try:
                event = events.get(timeout=1.0)
            except queue.Empty:
                if not worker.is_alive():
                    break
                continue
            name, data = event[0], event[1] if len(event) > 1 else None
            if name == "done":
                return str((data or {}).get("answer") or "")
            if name in ("error", "apperror", "cancel"):
                message = (data or {}).get("message") if isinstance(data, dict) else None
                raise RuntimeError(message or "Docs-Git stopped before answering.")
        raise RuntimeError("Docs-Git took too long to answer.")
    finally:
        with STREAMS_LOCK:
            STREAMS.pop(stream_id, None)


# ── Docs-Git project setup ──────────────────────────────────────────────────

def _new_project_prompt(name: str, template_label: str, files: list[str]) -> str:
    return (
        f"Set up the instruction files for the new project \"{name}\" ({template_label}). "
        "This folder is the project root. Hermes created these starter files from the brief "
        f"and my answers: {', '.join(files)}.\n\n"
        "Read them, then rewrite each one so it is complete and specific to this project: "
        "replace placeholder text with concrete guidance derived from the brief and the "
        "decisions recorded in them (stack, structure, conventions, testing, delivery). "
        "Keep AGENTS.md's continuity rules about .agent/ECC_HANDOFF.md, and update that "
        "handoff to record what you set up. Do not write application code yet. "
        "Finish with a short summary of what each file now covers and any open questions."
    )


def _adopt_prompt(name: str) -> str:
    return (
        f"Adopt the existing project \"{name}\". This folder is its root.\n\n"
        "1. Read the project to understand it: README and docs, build/package files, the "
        "source layout, tests, and any existing agent or contributor instructions "
        "(AGENTS.md, CLAUDE.md, .cursor, .github, CONTRIBUTING.md, .agent/).\n"
        "2. Make AGENTS.md and .agent/ECC_HANDOFF.md fit this project: follow the structure, "
        "tone and conventions of the instruction files it already has, merge rather than "
        "duplicate, and never delete or overwrite user-written guidance. AGENTS.md must "
        "require reading and updating .agent/ECC_HANDOFF.md for every persisted change.\n"
        "3. Record the verified current state (stack, commands, test status) in the handoff.\n\n"
        "Do not change application code. Finish with a short summary of what you learned "
        "and which files you created or edited."
    )


def start_docs_setup(project: dict, *, adopt: bool, template_label: str = "", files=None) -> str | None:
    """Start Docs-Git on the project folder; returns a job id, or None without the profile."""
    if not docs_profile_available():
        return None
    prompt = _adopt_prompt(project["name"]) if adopt else _new_project_prompt(
        project["name"], template_label or "Blank project", list(files or []))
    title = f"Docs-Git: {'adopt' if adopt else 'set up'} {project['name']}"
    return _start_job("setup", lambda: {"summary": _run_ephemeral_turn(
        prompt, timeout=_SETUP_TIMEOUT_SECONDS, workspace=project["workspace_path"], title=title).strip()})
