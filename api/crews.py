"""
Crews (multi-agent dispatch templates) storage.

A user-owned CRUD collection of named "crew" templates: each is a small,
ordered list of Kanban task specs that can be bulk-dispatched together in one
action, tagged with a shared ``workflow_template_id``/``current_step_key`` so
the resulting tasks can later be filtered/grouped as one dispatch run. This is
NOT a step-graph workflow engine -- there is nothing upstream (no dispatcher
support) to execute a graph against, so all of a template's task specs
dispatch as parent-less siblings, matching what
``hermes_cli.kanban_db.dispatch_once`` can actually run in parallel today.

Modeled directly on api/agent_definitions.py's storage pattern (profile-scoped
JSON file under the active profile's Hermes home, atomic tmp-file + fsync +
os.replace write, uuid4-hex12 ids). Unlike Personas there is no built-in vs.
custom split here -- every crew is a plain user-owned row.

See docs/HERMES_STUDIO_PARITY_PLAN.md, "Multi-agent orchestration (Crews +
Conductor)" -> "Phase 1 (v1) -- Crew templates + bulk dispatch", for the full
design and the (resolved) open questions this module implements.
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

NAME_MAX = 128
DESCRIPTION_MAX = 512
ICON_MAX = 8
TASK_TITLE_MAX = 200
TASK_BODY_MAX = 4000
SKILLS_MAX = 10
SKILL_MAX = 32
MAX_CREWS = 50
MAX_TASKS_PER_CREW = 20

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")

# Read-modify-write is not otherwise atomic across two concurrent requests for
# the same profile (the JSON file has no row-level locking); this lock closes
# that window for the common case of two webui tabs open at once. Mirrors
# api/agent_definitions.py's _WRITE_LOCK.
_WRITE_LOCK = threading.Lock()


def _crews_path() -> Path:
    try:
        from api.profiles import get_active_hermes_home
        return Path(get_active_hermes_home()).expanduser() / "webui" / "crew_templates.json"
    except Exception:
        return Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser() / "webui" / "crew_templates.json"


def _atomic_write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _load_crews() -> list:
    p = _crews_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_crews(crews: list) -> None:
    _atomic_write(_crews_path(), crews)


def _validate_color(color) -> None:
    if color and not _COLOR_RE.match(color):
        raise ValueError("Invalid color format")


def _clean_skills(skills) -> list:
    if skills is None:
        return []
    if not isinstance(skills, list):
        raise ValueError("skills must be a list")
    cleaned = []
    for skill in skills[:SKILLS_MAX]:
        skill = str(skill).strip()[:SKILL_MAX]
        if skill:
            cleaned.append(skill)
    return cleaned


def _clean_task_spec(spec) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("each task spec must be an object")
    title = str(spec.get("title") or "").strip()[:TASK_TITLE_MAX]
    if not title:
        raise ValueError("each task spec requires a title")
    body = str(spec.get("body") or "")[:TASK_BODY_MAX]
    assignee = str(spec.get("assignee") or "").strip() or None
    skills = _clean_skills(spec.get("skills"))
    try:
        priority = int(spec.get("priority") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("task priority must be an integer") from exc
    return {
        "title": title,
        "body": body,
        "assignee": assignee,
        "skills": skills,
        "priority": priority,
    }


def _clean_tasks(tasks) -> list:
    # A crew with zero task specs is a template with nothing to bulk-create,
    # so at least one is required. Individual specs MAY leave assignee empty
    # (see the plan's Phase 1 open question #1: resolved as "allow it" --
    # assignee validation already happens at kb.create_task time, so gating
    # it here again would be a parallel validation copy).
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("tasks must be a non-empty list")
    if len(tasks) > MAX_TASKS_PER_CREW:
        raise ValueError(f"too many task specs (max {MAX_TASKS_PER_CREW})")
    return [_clean_task_spec(t) for t in tasks]


def list_crews() -> dict:
    return {"crews": _load_crews()}


def get_crew(crew_id: str) -> dict | None:
    """Look up a single crew template by id, or None."""
    crew_id = str(crew_id or "").strip()
    if not crew_id:
        return None
    for c in _load_crews():
        if c.get("id") == crew_id:
            return c
    return None


def create_crew(body: dict) -> dict:
    name = str(body.get("name") or "").strip()[:NAME_MAX]
    if not name:
        raise ValueError("name is required")
    description = str(body.get("description") or "").strip()[:DESCRIPTION_MAX]
    icon = str(body.get("icon") or "").strip()[:ICON_MAX]
    color = body.get("color")
    _validate_color(color)
    tasks = _clean_tasks(body.get("tasks"))

    with _WRITE_LOCK:
        crews = _load_crews()
        if len(crews) >= MAX_CREWS:
            raise ValueError(f"crew limit reached (max {MAX_CREWS})")
        now = time.time()
        crew = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "icon": icon,
            "color": color,
            "description": description,
            "tasks": tasks,
            "created_at": now,
            "updated_at": now,
            # Phase 1.2 (docs/HERMES_STUDIO_PARITY_PLAN.md): recency signal
            # for the templates-gallery sort, stamped by _touch_crew_dispatched
            # on every dispatch attempt. None until first dispatch.
            "last_dispatched_at": None,
        }
        crews.append(crew)
        _save_crews(crews)
    return crew


def update_crew(body: dict) -> dict:
    crew_id = str(body.get("id") or "").strip()
    if not crew_id:
        raise ValueError("id is required")

    # Validate/normalize before taking the lock so a bad request never
    # partially mutates the in-memory row.
    updates = {}
    if "name" in body:
        name = str(body.get("name") or "").strip()[:NAME_MAX]
        if not name:
            raise ValueError("name is required")
        updates["name"] = name
    if "description" in body:
        updates["description"] = str(body.get("description") or "").strip()[:DESCRIPTION_MAX]
    if "icon" in body:
        updates["icon"] = str(body.get("icon") or "").strip()[:ICON_MAX]
    if "color" in body:
        _validate_color(body.get("color"))
        updates["color"] = body.get("color")
    if "tasks" in body:
        updates["tasks"] = _clean_tasks(body.get("tasks"))

    with _WRITE_LOCK:
        crews = _load_crews()
        crew = next((c for c in crews if c.get("id") == crew_id), None)
        if crew is None:
            raise KeyError("Crew not found")
        crew.update(updates)
        crew["updated_at"] = time.time()
        _save_crews(crews)
        return crew


def delete_crew(crew_id: str) -> None:
    crew_id = str(crew_id or "").strip()
    if not crew_id:
        raise ValueError("id is required")
    with _WRITE_LOCK:
        crews = _load_crews()
        remaining = [c for c in crews if c.get("id") != crew_id]
        if len(remaining) == len(crews):
            raise KeyError("Crew not found")
        _save_crews(remaining)


def duplicate_crew(crew_id: str) -> dict:
    crew_id = str(crew_id or "").strip()
    if not crew_id:
        raise ValueError("id is required")
    with _WRITE_LOCK:
        crews = _load_crews()
        source = next((c for c in crews if c.get("id") == crew_id), None)
        if source is None:
            raise KeyError("Crew not found")
        if len(crews) >= MAX_CREWS:
            raise ValueError(f"crew limit reached (max {MAX_CREWS})")

        now = time.time()
        new_crew = {
            "id": uuid.uuid4().hex[:12],
            "name": (source.get("name") or "Crew") + " (copy)",
            "icon": source.get("icon") or "",
            "color": source.get("color"),
            "description": source.get("description") or "",
            # Deep-copy every task spec (including nested lists like `skills`)
            # so editing the copy's tasks can never mutate the source crew's
            # rows in place -- mirrors the independent-copy guarantee tested
            # for Personas' `tags` list, one level deeper here.
            "tasks": copy.deepcopy(source.get("tasks") or []),
            "created_at": now,
            "updated_at": now,
            # A duplicate is a new template with no dispatch history of its
            # own -- deliberately NOT copied from the source (Phase 1.2).
            "last_dispatched_at": None,
        }
        crews.append(new_crew)
        _save_crews(crews)
        return new_crew


def _touch_crew_dispatched(crew_id: str, ts: float) -> None:
    """Best-effort: stamp ``last_dispatched_at`` on a crew that was just
    dispatched (Phase 1.2 -- see docs/HERMES_STUDIO_PARITY_PLAN.md).

    Called once per dispatch_crew() call, regardless of whether the run's
    individual task specs succeeded or failed -- "last dispatched" means
    "a dispatch of this template was last attempted at this time," not
    "last fully succeeded." A silent no-op if the crew isn't actually in
    on-disk storage (e.g. a test double, or a race with a concurrent
    delete) -- this is pure metadata, never load-bearing for dispatch_crew's
    own success/failure.
    """
    with _WRITE_LOCK:
        crews = _load_crews()
        crew = next((c for c in crews if c.get("id") == crew_id), None)
        if crew is None:
            return
        crew["last_dispatched_at"] = ts
        _save_crews(crews)


def _substitute_variables(text: str, variables: dict) -> str:
    """Single flat str.format-style pass -- no templating engine, no
    conditionals (see plan). A variable referenced in the template but absent
    from ``variables`` raises KeyError, which the per-task-spec dispatch loop
    below turns into that one spec's {ok: false, error} entry rather than
    aborting the whole dispatch."""
    return str(text or "").format(**(variables or {}))


def dispatch_crew(crew_id: str, body: dict) -> dict:
    """Bulk-create one Kanban task per task spec in the crew template.

    Reuses api.kanban_bridge._create_task_payload for validation (title
    required, priority-int handling, status handling) rather than
    duplicating it -- see that function's ``workflow_template_id``/
    ``current_step_key`` extension. Every task created by this dispatch run
    shares the crew's id as ``workflow_template_id`` and a single freshly
    generated ISO-timestamp ``current_step_key`` as an opaque per-run tag.

    Deliberately does NOT call ``dispatch_once`` -- matches the existing
    runKanbanDispatcher's explicit-confirm, cost-consuming-action pattern
    (static/panels.js). Dispatching a crew only stages `ready` tasks; a human
    still clicks Run Dispatcher to actually spawn worker subprocesses.

    Partial-success contract like api.kanban_bridge._bulk_tasks_payload: one
    bad assignee/spec does not abort the rest of the run.
    """
    crew_id = str(crew_id or "").strip()
    if not crew_id:
        raise ValueError("id is required")
    crew = get_crew(crew_id)
    if crew is None:
        raise KeyError("Crew not found")

    variables = body.get("variables") if isinstance(body.get("variables"), dict) else {}
    board = body.get("board") or None
    # Opaque per-dispatch run tag. Microsecond precision keeps concurrent
    # dispatches of the same crew from colliding on current_step_key.
    run_id = datetime.now(timezone.utc).isoformat(timespec="microseconds")

    # Lazy import: api.kanban_bridge itself lazily imports hermes_cli.kanban_db
    # (which may not always be mounted). Keeping this import inside the
    # function body means every other /api/crews/* endpoint (list/create/
    # update/delete/duplicate) stays usable even when the kanban bridge is
    # unavailable -- only dispatch needs it.
    from api.kanban_bridge import _create_task_payload

    results = []
    for spec in crew.get("tasks") or []:
        try:
            create_body = {
                "title": _substitute_variables(spec.get("title") or "", variables),
                "body": _substitute_variables(spec.get("body") or "", variables),
                "assignee": spec.get("assignee"),
                "skills": spec.get("skills"),
                "priority": spec.get("priority", 0),
                "workflow_template_id": crew_id,
                "current_step_key": run_id,
            }
            payload = _create_task_payload(create_body, board=board)
            task = payload.get("task") or {}
            results.append({"ok": True, "task_id": task.get("id")})
        except Exception as exc:
            results.append({"ok": False, "error": str(exc)})

    # Phase 1.2: stamp the recency signal for every dispatch attempt that
    # reached a real crew, regardless of per-task success/failure above.
    _touch_crew_dispatched(crew_id, time.time())

    return {"ok": True, "run_id": run_id, "results": results}
