"""Agent assistance for the project starter wizard.

Two kinds of hidden job run here, both under the ``architecture`` profile
pinned to GPT-6.1 Sol on Codex, for new and adopted projects alike:

* ``start_analysis`` reviews a project brief and returns the questions still
  needed to fill the template's instruction files.
* ``start_docs_setup`` works inside the project folder with the agent's own
  tools: it installs the project's dependencies, writes (new project) or
  adapts (existing project) the linked instruction files, and returns its
  summary.

Both are hidden, non-persistent (ephemeral) turns tracked as in-memory jobs
the wizard polls. A visible chat would live in the architecture profile, and
opening it would switch the user's whole UI to that profile.

The profile is never substituted: when it is missing the job fails with a
clear reason and the wizard carries on without the agent.
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
# The wizard's agent work (brief review, follow-up questions, and writing or
# adapting the instruction files) runs under the Architecture profile, pinned
# to GPT-6.1 Sol on Codex so it does not drift with the profile's default.
PLANNER_PROFILE = "architecture"
PLANNER_MODEL = "gpt-6.1-sol"
PLANNER_MODEL_LABEL = "GPT-6.1 Sol"
PLANNER_PROVIDER = "openai-codex"
AGENT_LABELS = {DOCS_PROFILE: "Docs-Git", PLANNER_PROFILE: "Architecture"}
_ANALYSIS_TIMEOUT_SECONDS = 240
# Setup now installs dependencies too, which can take a while on a cold cache.
_SETUP_TIMEOUT_SECONDS = 1800
_JOB_TTL_SECONDS = 3600
_MAX_QUESTIONS = 6

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def profile_available(profile: str) -> bool:
    try:
        from api.profiles import get_hermes_home_for_profile

        home = Path(get_hermes_home_for_profile(profile))
        return home.name == profile and (home / "config.yaml").is_file()
    except Exception:
        return False


def docs_profile_available() -> bool:
    return profile_available(DOCS_PROFILE)


def planner_profile_available() -> bool:
    return profile_available(PLANNER_PROFILE)


def agent_readiness(profile: str) -> dict:
    """Can this profile's agent start? Checked before a run so the wizard can offer setup.

    Blocks only on a definite gap (no sign-in / no key / no model) with no
    usable fallback; routes Hermes can't verify from here are let through and
    the agent reports any problem itself.
    """
    label = AGENT_LABELS.get(profile, profile)
    base = {"profile": profile, "agent": label}
    named = {DOCS_PROFILE: docs_profile_available, PLANNER_PROFILE: planner_profile_available}
    available = named[profile]() if profile in named else profile_available(profile)
    if not available:
        return {**base, "ready": False, "state": "missing", "provider": "",
                "message": f"The {label} profile is not set up."}
    from api.profile_providers import overview

    try:
        view = overview(profile)
    except Exception:
        return {**base, "ready": True, "state": "unknown", "provider": "", "message": ""}
    main = view["main"]
    state = main["status"]["state"]
    if state not in {"signin", "key", "unset"}:
        return {**base, "ready": True, "state": state, "provider": main["provider"], "message": main["status"]["message"]}
    if any(f["status"]["state"] == "ready" for f in view["fallbacks"]):
        return {**base, "ready": True, "state": "fallback", "provider": main["provider"], "message": "Using a fallback model."}
    return {**base, "ready": False, "state": state, "provider": main["provider"],
            "message": f"{label} can't run yet: {main['status']['message']}"}


def docs_agent_readiness() -> dict:
    return agent_readiness(DOCS_PROFILE)


def planner_readiness() -> dict:
    return agent_readiness(PLANNER_PROFILE)


# ── Brief analysis ─────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """You are helping set up a new software project's instruction files.
Do not use any tools and do not create files. Reply with ONLY one JSON object:
{{"complete": true|false, "summary": "one sentence", "questions": [
  {{"id": "short_snake_id", "question": "...",
    "options": [{{"label": "...", "detail": "what it is, in under 12 words"}}, ...exactly 3],
    "other": "placeholder for a typed answer, e.g. Other stack (type it)",
    "recommended": "one of the option labels, copied exactly",
    "why": "2-4 sentences tied to the brief",
    "examples": ["concrete example", "..."]}}]}}

The project will be created from the "{template}" template, which writes these
files: {files}. To fill them well we need: what is being built and for whom, the
programming stack (languages, frameworks, data storage), how it is tested, and
how it is deployed or delivered (skip what does not apply to this template).

Set "complete" to true only when the brief already answers everything that
applies. Otherwise ask at most {max_questions} short questions, one per missing
fact, most important first. Give each question exactly 3 concrete, mutually
exclusive options that suit the brief, each with a short "detail". Do not add
an "Other" option: the user types their own answer in a fourth field, whose
placeholder you write as "other". For every question, pick the option you would
recommend for THIS project (its users, scale, platform and constraints in the
brief) as "recommended". In "why", explain in 2-4 sentences why it fits this
brief better than the other two, naming the trade-off you accept. In
"examples", give 2-3 short concrete illustrations (a well-known product built
that way, a library or service it pairs with, or what it means for this
project's first milestone). Prefer mainstream, well-supported choices unless
the brief points elsewhere.

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
    return _start_job("analysis", lambda: parse_analysis(_run_ephemeral_turn(
        prompt, timeout=_ANALYSIS_TIMEOUT_SECONDS, **_planner_run())))


def _planner_run() -> dict:
    return {"profile": PLANNER_PROFILE, "title": "Architecture",
            "model": PLANNER_MODEL, "model_provider": PLANNER_PROVIDER}


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
        logger.warning("Project starter agent job failed: %s", exc)
        _finish(job_id, status="error", error=str(exc) or "Architecture could not finish.")


def parse_analysis(text: str) -> dict:
    """Validate the planner's JSON reply into the wizard's question format.

    Each question keeps at most three choices (the wizard's keys 1-3) plus a
    typed answer (key 4) whose placeholder is ``other``. An "Other ..." choice
    the model adds anyway becomes that placeholder instead of a fourth choice.
    """
    raw = str(text or "").strip()
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        logger.warning("Planner review was not JSON (%d chars): %r", len(raw), raw[:300])
        raise ValueError("Architecture did not return a readable review.")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Architecture did not return a readable review.")
    questions = []
    seen = set()
    for item in data.get("questions") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()[:300]
        other = str(item.get("other") or "").strip()[:80]
        choices = []
        for raw_option in item.get("options") or []:
            label, detail = (raw_option.get("label"), raw_option.get("detail")) if isinstance(raw_option, dict) else (raw_option, "")
            label, detail = str(label or "").strip()[:120], str(detail or "").strip()[:160]
            if not label:
                continue
            if re.match(r"(other|something else)\b", label, re.I):
                other = other or label[:80]
                continue
            choices.append((label, detail))
        choices = choices[:3]
        options = [label for label, _ in choices]
        qid = re.sub(r"[^a-z0-9_]+", "_", str(item.get("id") or question).lower()).strip("_")[:40] or f"q{len(questions) + 1}"
        if not question or qid in seen:
            continue
        seen.add(qid)
        recommended = str(item.get("recommended") or "").strip()
        match = next((o for o in options if o.casefold() == recommended.casefold()), "")
        entry = {"id": qid, "question": question, "options": options,
                 "details": [detail for _, detail in choices], "other": other or "Something else"}
        if match:
            entry["recommended"] = match
            entry["why"] = str(item.get("why") or "").strip()[:600]
            examples = [str(e).strip()[:160] for e in item.get("examples") or [] if isinstance(e, str) and str(e).strip()]
            if examples:
                entry["examples"] = examples[:3]
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


def _run_ephemeral_turn(prompt: str, *, timeout: float, workspace: str | None = None, title: str = "Docs-Git",
                        profile: str = DOCS_PROFILE, model: str | None = None,
                        model_provider: str | None = None) -> str:
    """Run one hidden agent turn under ``profile`` and return its final answer.

    ``model``/``model_provider`` pin the model; otherwise the profile's own
    default is used.
    """
    label = AGENT_LABELS.get(profile, profile)
    if not profile_available(profile):
        raise RuntimeError(f"The {label} profile is not set up.")
    from api.models import new_session
    from api.routes import (
        STREAMS,
        STREAMS_LOCK,
        _run_agent_streaming,
        create_stream_channel,
        register_session_writeback_owner,
        register_stream_owner,
    )

    session = new_session(workspace=workspace, profile=profile)
    if not model:
        model, model_provider = _profile_model(session)
    session.model = model
    session.model_provider = model_provider
    session.title = title[:80]
    session.source_tag = "project_starter"  # hidden from every session list
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
                payload = data or {}
                if payload.get("failure_reason"):
                    # The model never answered: report why, not "unreadable".
                    detail = str(payload.get("failure_message") or "").strip()
                    raise RuntimeError(detail or f"{label}'s model failed ({payload['failure_reason']}).")
                return str(payload.get("answer") or "")
            if name in ("error", "apperror", "cancel"):
                message = (data or {}).get("message") if isinstance(data, dict) else None
                raise RuntimeError(message or f"{label} stopped before answering.")
        raise RuntimeError(f"{label} took too long to answer.")
    finally:
        with STREAMS_LOCK:
            STREAMS.pop(stream_id, None)
        # The ephemeral path removes the file only on success; a failed or
        # timed-out run would otherwise leave an empty session behind.
        if not worker.is_alive():
            try:
                Path(session.path).unlink(missing_ok=True)
            except Exception:
                pass


# ── Project setup (Architecture) ────────────────────────────────────────────

_SETUP_RULES = (
    "Dependencies: install everything the chosen stack needs so the project runs "
    "from a clean checkout. Use the stack's own package manager and lockfile "
    "(npm/pnpm/yarn, uv/pip with a virtual environment inside the project, cargo, "
    "go mod, Swift Package Manager, Gradle...), never global installs or sudo. "
    "Create the manifest if there is none, install, then run the install and "
    "test commands once to prove they work, and record the exact commands in "
    ".agent/CONTEXT.md and the README's Getting started. If something cannot be "
    "installed here, say what and why in .agent/ECC_HANDOFF.md instead of "
    "pretending it worked.\n"
    "Linking: every instruction file ends with a \"Related documents\" list "
    "linking to the others with relative Markdown links. Keep those lists, link "
    "any document you add from AGENTS.md, README.md and the other lists, refer to "
    "related documents inline where a reader needs them (for example "
    "ARCHITECTURE.md pointing at TESTING.md for the test commands), and leave no "
    "dead links."
)

def _new_project_prompt(name: str, template_label: str, files: list[str]) -> str:
    return (
        f"Set up the instruction files for the new project \"{name}\" ({template_label}). "
        "This folder is the project root. Hermes created these starter files from the brief "
        f"and my answers: {', '.join(files)}.\n\n"
        "Read them, then rewrite each one so it is complete and specific to this project: "
        "replace placeholder text with concrete guidance derived from the brief and the "
        "decisions recorded in them (stack, structure, conventions, testing, delivery). "
        "Keep AGENTS.md's continuity rules about .agent/ECC_HANDOFF.md, and update that "
        "handoff to record what you set up. Do not write application features yet; a "
        "manifest, config and the smallest entry point the toolchain needs to install "
        "and run its tests are fine.\n\n"
        f"{_SETUP_RULES}\n\n"
        "Finish with a short summary of what each file now covers, what was installed "
        "and verified, and any open questions."
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
        f"{_SETUP_RULES}\n\n"
        "Do not change application code. Finish with a short summary of what you learned, "
        "what was installed and verified, and which files you created or edited."
    )


def setup_profile(adopt: bool) -> str:
    """Which profile writes the instruction files: Architecture, for new and adopted projects."""
    return PLANNER_PROFILE


def start_docs_setup(project: dict, *, adopt: bool, template_label: str = "", files=None) -> str | None:
    """Start the setup agent on the project folder; returns a job id, or None without the profile."""
    profile = setup_profile(adopt)
    if not profile_available(profile):
        return None
    prompt = _adopt_prompt(project["name"]) if adopt else _new_project_prompt(
        project["name"], template_label or "Blank project", list(files or []))
    run = _planner_run()
    run["title"] = f"{AGENT_LABELS[profile]}: {'adopt' if adopt else 'set up'} {project['name']}"
    return _start_job("setup", lambda: {"summary": _run_ephemeral_turn(
        prompt, timeout=_SETUP_TIMEOUT_SECONDS, workspace=project["workspace_path"], **run).strip()})
