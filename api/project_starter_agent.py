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
    "options": [{{"label": "...", "detail": "what it is, in under 12 words",
                 "how": "1-2 sentences: how this project would be built with it"}}, ...exactly 3],
    "other": "placeholder for a typed answer, e.g. Other stack (type it)",
    "recommended": "one of the option labels, copied exactly",
    "why": "2-4 sentences tied to the brief",
    "examples": ["concrete example", "..."]}}],
 "look": {{"style": "minimal|elegant|playful|bold|technical|editorial",
   "motion": "none|subtle|expressive",
   "framework": "react|vue|svelte|vanilla|swiftui|compose|react-native|flutter",
   "tailwind": true|false, "why": "one sentence tied to the brief",
   "palette": {{"name": "two-word name", "why": "one sentence tied to the business",
     "light": {{"bg": "#rrggbb", "surface": "#rrggbb", "text": "#rrggbb", "primary": "#rrggbb", "accent": "#rrggbb"}},
     "dark": {{"bg": "#rrggbb", "surface": "#rrggbb", "text": "#rrggbb", "primary": "#rrggbb", "accent": "#rrggbb"}}}}}}}}

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
brief better than the other two, naming the trade-off you accept. In each
option's "how", say in 1-2 sentences how THIS project would be built if the
user picks that option (what changes in the stack, the work or the delivery),
so the user can compare any choice, not only the recommended one. In
"examples", give 2-3 short concrete illustrations (a well-known product built
that way, a library or service it pairs with, or what it means for this
project's first milestone). Prefer mainstream, well-supported choices unless
the brief points elsewhere.

"look" recommends the visual direction from the business the brief describes:
the one style that suits its audience and brand, how much motion it should use,
and the UI framework and whether Tailwind CSS fit the brief and template (for
iOS pick swiftui or react-native, for Android compose, react-native or flutter).
In "why", name the audience or brand trait that decides it, in one sentence.
"palette" recommends the colours from what the business is about and its vibe
(a brand colour the brief names comes first): a light set and a dark set, each
with the page background, a surface for cards, body text, a primary for buttons
and links, and an accent. Body text must reach 7:1 contrast on the background
and the primary 4.5:1, in both sets; the dark set keeps the light set's hues.

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
    return _start_job("analysis", lambda report, on_run: parse_analysis(_run_ephemeral_turn(
        prompt, timeout=_ANALYSIS_TIMEOUT_SECONDS, progress=report, on_run=on_run,
        answer_label="Writing up its questions", **_planner_run())), with_progress=True)


def _planner_run() -> dict:
    return {"profile": PLANNER_PROFILE, "title": "Architecture",
            "model": PLANNER_MODEL, "model_provider": PLANNER_PROVIDER}


# Fields kept on a job for stopping it; never returned by ``get_job``.
_PRIVATE_JOB_FIELDS = ("created", "workspace", "project_id", "session_id", "stream_id")


def _start_job(kind: str, work, *, with_progress: bool = False, workspace: str | None = None,
               project_id: str | None = None) -> str:
    """Run ``work`` in the background as a pollable job.

    With ``with_progress`` the work is called with ``report(line)``, whose
    latest line ``get_job`` returns as ``progress`` while the job runs (so the
    wizard can show what the agent is doing), and ``on_run(session_id,
    stream_id)``, which records the hidden turn so ``stop_jobs`` can stop
    it. ``workspace``/``project_id`` name the folder and project the job works on.
    """
    job_id = uuid.uuid4().hex[:16]
    now = time.time()
    with _jobs_lock:
        _prune_jobs(now)
        _jobs[job_id] = {"status": "running", "kind": kind, "created": now}
        if workspace:
            _jobs[job_id]["workspace"] = str(workspace)
        if project_id:
            _jobs[job_id]["project_id"] = str(project_id)
    if with_progress:
        inner = work

        def work():
            return inner(lambda line: _report_progress(job_id, line), lambda sid, stream: _note_run(job_id, sid, stream))
    threading.Thread(target=_job_worker, args=(job_id, work), daemon=True).start()
    return job_id


def _note_run(job_id: str, session_id: str, stream_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["session_id"], job["stream_id"] = session_id, stream_id


def _report_progress(job_id: str, line: str) -> None:
    line = str(line or "").strip()
    if not line:
        return
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None and job.get("status") == "running":
            job["progress"] = line[:_PROGRESS_MAX]


# ── Progress lines ──────────────────────────────────────────────────────────
# One short, plain sentence for what a hidden agent turn is doing right now,
# built from its stream events: the tool it called, the heading or latest
# sentence of its reasoning, or that it is writing the answer.

_PROGRESS_MAX = 120
_TOOL_VERBS = {
    "read_file": "Reading", "write_file": "Writing", "patch": "Editing", "search_files": "Searching files for",
    "web_search": "Searching the web for", "web_extract": "Reading", "terminal": "Running",
    "browser_navigate": "Opening", "skill_view": "Reading the skill", "skills_list": "Listing skills",
    "todo": "Updating its plan", "memory": "Checking its memory", "session_search": "Searching past sessions for",
}
_TOOL_ARG_KEYS = ("path", "query", "pattern", "url", "urls", "command", "name", "file_path")


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def tool_progress_line(data) -> str:
    """``Reading src/app.py`` style line for one tool call event."""
    data = data if isinstance(data, dict) else {}
    name = str(data.get("name") or "").strip()
    if not name:
        return ""
    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    arg, arg_key = "", ""
    for key in _TOOL_ARG_KEYS:
        value = args.get(key)
        if isinstance(value, list):
            value = value[0] if value else ""
        if isinstance(value, str) and value.strip():
            arg, arg_key = value.strip(), key
            break
    if arg_key in ("path", "file_path"):
        arg = arg.rstrip("/").rsplit("/", 1)[-1] or arg
    verb = _TOOL_VERBS.get(name)
    if verb is None:
        verb = "Using " + name.replace("_", " ")
    if arg and name not in ("todo", "memory", "skills_list"):
        return _clip(f"{verb} {_clip(arg, 60)}", _PROGRESS_MAX)
    return _clip(verb, _PROGRESS_MAX)


def reasoning_progress_line(text: str) -> str:
    """The latest heading (``**Weighing the stack**``) or sentence of reasoning."""
    text = str(text or "")
    headings = re.findall(r"\*\*([^*\n]{3,80})\*\*", text)
    if headings:
        return _clip(headings[-1], _PROGRESS_MAX)
    plain = re.sub(r"[`*_#>]+", "", text).strip()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", plain) if len(s.strip()) > 12]
    if not sentences:
        return ""
    # The last sentence may still be streaming; prefer the last finished one.
    last = sentences[-1] if re.search(r"[.!?]$", sentences[-1]) or len(sentences) == 1 else sentences[-2]
    return _clip(last, _PROGRESS_MAX)


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(str(job_id or ""))
        return {k: v for k, v in job.items() if k not in _PRIVATE_JOB_FIELDS} if job else None


def _finish(job_id: str, **fields) -> None:
    with _jobs_lock:
        # A stopped job keeps its "cancelled" status: the turn it interrupted
        # ends in an error that is not the reason it ended.
        if job_id in _jobs and _jobs[job_id].get("status") != "cancelled":
            _jobs[job_id].update(fields)


def _inside(path: str, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def stop_jobs(*, under: str | Path | None = None, project_id: str | None = None,
              reason: str = "Stopped: the project was deleted.") -> list[dict]:
    """Stop the running jobs that work inside ``under`` or on ``project_id``.

    Each is marked cancelled first (so its poller stops and its result is
    ignored), then its hidden turn is cancelled and every process that turn
    started is killed. Returns what was stopped: ``{"job_id", "session_id",
    "workspace"}`` per job.
    """
    root = Path(under).resolve() if under is not None else None
    stopped = []
    with _jobs_lock:
        for job_id, job in _jobs.items():
            if job.get("status") != "running":
                continue
            hit = (project_id and job.get("project_id") == str(project_id)) or (
                root is not None and job.get("workspace") and _inside(job["workspace"], root))
            if not hit:
                continue
            job.update(status="cancelled", error=reason)
            job.pop("progress", None)
            stopped.append({"job_id": job_id, "session_id": job.get("session_id"),
                            "stream_id": job.get("stream_id"), "workspace": job.get("workspace")})
    for item in stopped:
        _stop_turn(item.pop("stream_id"), item["session_id"])
    return stopped


def _stop_turn(stream_id: str | None, session_id: str | None) -> None:
    """Cancel one hidden turn and kill the processes it started."""
    if stream_id:
        try:
            from api.streaming import cancel_stream

            cancel_stream(stream_id)
        except Exception:
            logger.warning("Could not cancel project setup stream %s", stream_id, exc_info=True)
    if session_id:
        try:
            from tools.process_registry import process_registry

            process_registry.kill_all(session_id, source="project_deleted", consume_output=True)
        except Exception:
            # The agent's registry is optional here: processes left in the
            # folder are still found by their working directory.
            logger.warning("Could not stop the setup agent's processes for %s", session_id, exc_info=True)


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
            label, detail, how = (raw_option.get("label"), raw_option.get("detail"), raw_option.get("how")) \
                if isinstance(raw_option, dict) else (raw_option, "", "")
            label, detail, how = str(label or "").strip()[:120], str(detail or "").strip()[:160], str(how or "").strip()[:400]
            if not label:
                continue
            if re.match(r"(other|something else)\b", label, re.I):
                other = other or label[:80]
                continue
            choices.append((label, detail, how))
        choices = choices[:3]
        options = [label for label, _, _ in choices]
        qid = re.sub(r"[^a-z0-9_]+", "_", str(item.get("id") or question).lower()).strip("_")[:40] or f"q{len(questions) + 1}"
        if not question or qid in seen:
            continue
        seen.add(qid)
        recommended = str(item.get("recommended") or "").strip()
        match = next((o for o in options if o.casefold() == recommended.casefold()), "")
        entry = {"id": qid, "question": question, "options": options,
                 "details": [detail for _, detail, _ in choices], "other": other or "Something else"}
        if any(how for _, _, how in choices):
            entry["hows"] = [how for _, _, how in choices]
        if match:
            entry["recommended"] = match
            entry["why"] = str(item.get("why") or "").strip()[:600]
            examples = [str(e).strip()[:160] for e in item.get("examples") or [] if isinstance(e, str) and str(e).strip()]
            if examples:
                entry["examples"] = examples[:3]
        questions.append(entry)
        if len(questions) >= _MAX_QUESTIONS:
            break
    out = {
        "complete": bool(data.get("complete")) and not questions,
        "summary": str(data.get("summary") or "").strip()[:400],
        "questions": questions,
    }
    look = parse_look(data.get("look"))
    if look:
        out["look"] = look
    return out


def parse_look(raw, *, palette_source: str = "recommended") -> dict | None:
    """The brief's recommended style and motion (both required), framework, Tailwind and colour palette."""
    from api.library_catalog import FRAMEWORKS, MOTIONS, STYLES
    from api.project_palette import normalize_palette

    if not isinstance(raw, dict):
        return None
    style = str(raw.get("style") or "").strip().lower()
    motion = str(raw.get("motion") or "").strip().lower()
    if style not in STYLES or motion not in MOTIONS:
        return None
    framework = str(raw.get("framework") or "").strip().lower()
    look = {"style": style, "motion": motion, "framework": framework if framework in FRAMEWORKS else "",
            "tailwind": raw.get("tailwind") is True, "why": str(raw.get("why") or "").strip()[:300]}
    palette = normalize_palette(raw.get("palette"), default_source=palette_source)
    if palette:
        look["palette"] = palette
    return look


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
                        model_provider: str | None = None, progress=None,
                        answer_label: str = "Writing its answer", on_run=None) -> str:
    """Run one hidden agent turn under ``profile`` and return its final answer.

    ``model``/``model_provider`` pin the model; otherwise the profile's own
    default is used. ``progress`` receives a one-line description of what the
    turn is doing each time that changes; ``on_run(session_id, stream_id)`` is
    called once the turn exists, so it can be stopped.
    """
    last_line = [""]
    reasoning = [""]

    def report(line: str) -> None:
        if progress is None or not line or line == last_line[0]:
            return
        last_line[0] = line
        try:
            progress(line)
        except Exception:
            pass
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
    if on_run is not None:
        on_run(session.session_id, stream_id)
    worker = threading.Thread(
        target=_run_agent_streaming,
        args=(session.session_id, prompt, model, session.workspace, stream_id, None),
        kwargs={"ephemeral": True, "model_provider": model_provider},
        daemon=True,
    )
    worker.start()
    report(f"Starting {label}")
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
            if name == "tool":
                reasoning[0] = ""  # what it thought before the call is done
                report(tool_progress_line(data))
            elif name == "reasoning" and isinstance(data, dict):
                reasoning[0] = (reasoning[0] + str(data.get("text") or ""))[-4000:]
                report(reasoning_progress_line(reasoning[0]))
            elif name == "token":
                report(answer_label)
            elif name == "done":
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
        # The ephemeral path removes the file only on success; a failed,
        # cancelled or timed-out run would otherwise leave an empty session
        # behind. A cancelled turn needs a moment to unwind first.
        worker.join(timeout=5)
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
        "handoff to record what you set up. Text between <!-- hermes:toolkit:begin --> and "
        "<!-- hermes:toolkit:end --> records the owner's choices in the wizard (skills, look and "
        "feel, approved components, stack): keep those blocks word for word and build on them; "
        "the stack they name is decided. Do not write application features yet; a "
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
    workspace = project["workspace_path"]
    job_id = _start_job("setup", lambda report, on_run: {"summary": _run_ephemeral_turn(
        prompt, timeout=_SETUP_TIMEOUT_SECONDS, workspace=workspace, progress=report, on_run=on_run,
        answer_label="Writing up what it set up", **run).strip()}, with_progress=True, workspace=workspace,
        project_id=project.get("project_id"))
    return job_id
