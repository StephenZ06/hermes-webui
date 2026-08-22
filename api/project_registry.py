"""Read-only access to the Hermes ``WORKSPACES.yaml`` project registry.

WORKSPACES.yaml is authored/maintained on the agent side (the ``hermes``
container, where ``project-lifecycle`` reads it from
``/opt/data/hermes-workspaces/WORKSPACES.yaml``). WebUI and the agent share
the same underlying volume, mounted here under ``HERMES_HOME``, so this
module only ever reads that file — it never writes it.

Note: ``HERMES_HOME`` is NOT reliably ``api.config.STATE_DIR.parent`` —
``STATE_DIR`` defaults to ``HERMES_HOME / "webui"`` but can be (and in
production is) overridden independently via ``HERMES_WEBUI_STATE_DIR`` to
any path, including one that is NOT nested under HERMES_HOME (the test
harness sets both env vars to the *same* directory). Use
``api.config._DEFAULT_STATE_HOME``, which already resolves HERMES_HOME
correctly (env var if set, else the platform default) independent of
STATE_DIR's own override.

This is the trusted source for project-bound chats: a chat can bind to a
project *key* from this registry, never to an arbitrary path.
"""
import logging
import os
from pathlib import Path

import yaml

from api.config import _DEFAULT_STATE_HOME as _HERMES_HOME

logger = logging.getLogger(__name__)

WORKSPACES_REGISTRY_FILE = _HERMES_HOME / "hermes-workspaces" / "WORKSPACES.yaml"
PROJECT_LIFECYCLE_SKILL_FILE = (
    _HERMES_HOME / "skills" / "project-lifecycle" / "project-lifecycle" / "SKILL.md"
)

_UNCONFIRMED_STATUS_MARKERS = ("needs_confirmation", "not confirmed", "not_confirmed")

# Only projects located under one of these roots are offered as bindable in
# the WebUI picker. This does NOT filter Discord routing, project-lifecycle,
# or any other consumer of WORKSPACES.yaml — it's a WebUI-only presentation
# scope, by explicit user request (e.g. excluding hermes-core-custom, the
# agent's own source checkout, from the chat-binding picker). Override with
# a comma-separated HERMES_WEBUI_PROJECT_SCOPE_ROOTS if the scope changes;
# set it to an explicit empty string to disable filtering entirely (distinct
# from leaving it UNSET, which uses the default below) — used by the test
# harness, which has no reason to know about /workspace.
_DEFAULT_PROJECT_SCOPE_ROOTS = ("/workspace/MiniPC-Main", "/workspace/rp5", "/workspace/remote")


def _project_scope_roots() -> tuple[str, ...]:
    raw = os.getenv("HERMES_WEBUI_PROJECT_SCOPE_ROOTS")
    if raw is None:
        return _DEFAULT_PROJECT_SCOPE_ROOTS
    return tuple(root.strip().rstrip("/") for root in raw.split(",") if root.strip())


def _in_scope(location: str | None, roots: tuple[str, ...]) -> bool:
    if not roots:
        return True
    if not location:
        return False
    location = location.rstrip("/")
    return any(location == root or location.startswith(root + "/") for root in roots)


def _real_repo_path(raw_repo_path) -> str | None:
    """Return raw_repo_path unless it's a NEEDS_* placeholder sentinel.

    Real entries use ``NEEDS_CONFIRMATION`` (candidate local path not yet
    verified) and ``NEEDS_REMOTE_ACCESS`` (SSH-only project with no local
    repo_path at all) — both mean "no real repo_path here", not a literal
    path value.
    """
    if not raw_repo_path:
        return None
    text = str(raw_repo_path).strip()
    if text.upper().startswith("NEEDS_"):
        return None
    return text


def _raw_ssh_config(entry: dict) -> dict:
    """Extract SSH config from a raw WORKSPACES.yaml entry.

    Real entries (as authored by the agent-side registry tooling) put
    ``ssh_target`` / ``ssh_key`` / ``remote_path`` as TOP-LEVEL keys on the
    project, not nested under an ``ssh:`` sub-mapping. A nested ``ssh:``
    dict is also accepted (and preferred if both are somehow present) in
    case a future/alternate authoring path uses that shape instead.
    """
    nested = entry.get("ssh") if isinstance(entry.get("ssh"), dict) else {}
    return {
        "target": nested.get("target") or entry.get("ssh_target"),
        "key": nested.get("key") or entry.get("ssh_key"),
        "remote_path": nested.get("remote_path") or entry.get("remote_path"),
    }


def _infer_access_mode(entry: dict, ssh_cfg: dict) -> str | None:
    """Infer access_mode when the entry doesn't declare one explicitly.

    Real entries frequently omit ``access_mode`` for local projects (it's
    implied by having a confirmed ``repo_path`` and no SSH target) — only
    reject as "unknown" when neither a repo_path nor any SSH config is
    present to infer from.
    """
    declared = str(entry.get("access_mode") or "").strip().lower()
    if declared:
        return declared
    if ssh_cfg.get("target") or ssh_cfg.get("key") or ssh_cfg.get("remote_path"):
        return "ssh"
    if _real_repo_path(entry.get("repo_path")):
        return "local"
    return None


def _is_available(entry: dict) -> tuple[bool, str | None]:
    """Return (available, reason) for an already-normalized project dict."""
    repo_path = entry.get("repo_path")
    access_mode = entry.get("access_mode")
    status = entry.get("status") or ""
    status_lower = status.lower()

    if any(marker in status_lower for marker in _UNCONFIRMED_STATUS_MARKERS):
        return False, status or "needs confirmation"
    if access_mode not in ("local", "ssh"):
        return False, f"unknown access_mode: {access_mode or '(none)'}"
    if access_mode == "local":
        if not repo_path:
            return False, status or "repo path not confirmed"
        if not Path(str(repo_path)).is_dir():
            return False, f"repo_path does not exist: {repo_path}"
    if access_mode == "ssh":
        ssh = entry.get("ssh") or {}
        missing = [k for k in ("target", "key", "remote_path") if not ssh.get(k)]
        if missing:
            return False, f"ssh config missing: {', '.join(missing)}"
    return True, None


def _normalize_project(key: str, entry: dict) -> dict:
    entry = entry if isinstance(entry, dict) else {}
    ssh_cfg = _raw_ssh_config(entry)
    access_mode = _infer_access_mode(entry, ssh_cfg)
    repo_path = _real_repo_path(entry.get("repo_path"))
    candidate_path = _real_repo_path(entry.get("candidate_path"))
    normalized = {
        "key": key,
        "name": str(entry.get("display_name") or entry.get("name") or key),
        "access_mode": access_mode,
        "repo_path": repo_path,
        "ssh": ssh_cfg if access_mode == "ssh" else None,
        "status": str(entry.get("status") or ""),
        "required_docs": list(entry.get("required_docs") or []),
    }
    available, reason = _is_available(normalized)
    normalized["available"] = available
    normalized["unavailable_reason"] = reason
    # Scope location: prefer the confirmed repo_path, fall back to the
    # candidate_path for not-yet-confirmed local projects so they still show
    # up (as unavailable, with a reason) instead of disappearing entirely.
    normalized["_scope_location"] = repo_path or candidate_path
    return normalized


def list_registry_projects() -> list[dict]:
    """Return every in-scope project in WORKSPACES.yaml, normalized.

    Unavailable-but-in-scope projects (unconfirmed path, missing SSH
    config, etc.) are INCLUDED with ``available: False`` and a reason —
    never silently dropped, so the picker can show why a project can't be
    bound yet instead of just not listing it. Out-of-scope projects (not
    under a configured project-scope root — see
    HERMES_WEBUI_PROJECT_SCOPE_ROOTS) are dropped entirely; that's a
    deliberate presentation-scope exclusion, not an error state.
    """
    if not WORKSPACES_REGISTRY_FILE.is_file():
        return []
    try:
        raw = yaml.safe_load(WORKSPACES_REGISTRY_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.exception("Failed to parse WORKSPACES.yaml at %s", WORKSPACES_REGISTRY_FILE)
        return []
    projects = raw.get("projects") if isinstance(raw, dict) else None
    if not isinstance(projects, dict):
        return []
    roots = _project_scope_roots()
    result = []
    for key, entry in projects.items():
        normalized = _normalize_project(key, entry)
        if _in_scope(normalized.pop("_scope_location"), roots):
            result.append(normalized)
    return result


def resolve_registry_project(key: str) -> dict | None:
    """Resolve a single project by key, or None if it doesn't exist."""
    key = str(key or "").strip()
    if not key:
        return None
    for project in list_registry_projects():
        if project["key"] == key:
            return project
    return None


def read_project_lifecycle_skill_text() -> str | None:
    """Return the full text of project-lifecycle's SKILL.md, or None."""
    if not PROJECT_LIFECYCLE_SKILL_FILE.is_file():
        return None
    try:
        return PROJECT_LIFECYCLE_SKILL_FILE.read_text(encoding="utf-8")
    except Exception:
        logger.exception(
            "Failed to read project-lifecycle SKILL.md at %s", PROJECT_LIFECYCLE_SKILL_FILE
        )
        return None
