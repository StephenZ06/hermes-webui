"""Create a safe, documented starting point for a Hermes project folder.

The WebUI project record and its on-disk project are created together by the
projects route.  This module owns only the on-disk side so it can be tested
without a running server and so filesystem safety has one clear home.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from api.workspace import (
    _DIR_FD_OK,
    _O_DIRECTORY,
    _O_NOFOLLOW,
    open_anchored_create_fd,
    rmtree_anchored,
    unlink_anchored,
)


class ProjectStarterError(ValueError):
    """The requested starter pack cannot be created safely."""


# Workspaces often live on Windows drives (/mnt/c/...), so names must also be
# valid there: no reserved characters, reserved device names, or trailing
# dots/spaces. A leading dot would create a hidden folder the user can't see.
_FOLDER_RE = re.compile(r'^[^/\\<>:"|?*\x00-\x1f]{1,96}$')
_RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_TEMPLATES = {
    "blank": ("Blank project", ()),
    "web": ("Web application", ("PRODUCT.md", "ARCHITECTURE.md", "UI_UX.md", "TESTING.md")),
    "ios": ("iOS application", ("PRODUCT.md", "ARCHITECTURE.md", "IOS.md", "UI_UX.md", "TESTING.md")),
    "api": ("API or backend service", ("PRODUCT.md", "ARCHITECTURE.md", "API.md", "TESTING.md")),
    "research": ("Research project", ("RESEARCH.md", "SOURCES.md", "FINDINGS.md")),
}


def available_templates() -> tuple[str, ...]:
    return tuple(_TEMPLATES)


def _folder_name(value: str) -> str:
    name = str(value or "").strip()
    if not _FOLDER_RE.fullmatch(name):
        raise ProjectStarterError('A project folder name cannot contain / \\ < > : " | ? * or control characters.')
    if name.startswith(".") or name.endswith((".", " ")):
        raise ProjectStarterError("A project folder name cannot start with a dot or end with a dot or space.")
    if name.split(".")[0].lower() in _RESERVED_NAMES:
        raise ProjectStarterError("That project folder name is reserved by Windows.")
    return name


def _brief(value: str) -> str:
    text = str(value or "").strip()
    if len(text) > 100_000:
        raise ProjectStarterError("Project brief is too large (maximum 100,000 characters).")
    return text


def _write(root: Path, path: Path, content: str) -> None:
    fd = open_anchored_create_fd(root, path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _make_new_dir(root: Path, name: str) -> None:
    """Create ``root/name`` exclusively; never reuse a folder that appeared late."""
    try:
        if not _DIR_FD_OK:
            os.mkdir(root / name)
            return
        fd = os.open(str(root), os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW)
        try:
            os.mkdir(name, dir_fd=fd)
        finally:
            os.close(fd)
    except FileExistsError as exc:
        raise ProjectStarterError("A folder with that name already exists in the selected workspace.") from exc


def project_using_path(projects: list, path: Path) -> dict | None:
    """Return the sidebar project already bound to ``path``, if any."""
    wanted = os.path.normpath(str(Path(path).resolve()))
    for project in projects or []:
        bound = project.get("workspace_path") if isinstance(project, dict) else None
        if bound and os.path.normpath(str(Path(bound).resolve())) == wanted:
            return project
    return None


def _document(title: str, brief: str, guidance: str) -> str:
    context = brief or "Add the project brief, intended users, and success criteria here."
    return f"# {title}\n\n## Current context\n\n{context}\n\n## Working notes\n\n{guidance}\n"


def _agents(name: str) -> str:
    return f"""# {name} agent instructions

## Continuity is required

Before making any persisted project change (code, configuration, documentation,
tests, commits, or deployment), read `.agent/ECC_HANDOFF.md`. Update that file
before completing the work. Do not update it for read-only questions that do
not change this project.

Record only verified facts. Keep **changed**, **tested**, **committed**,
**deployed**, and **user-verified** as separate states. Never place secrets,
access tokens, or raw conversation logs in the handoff.

## Working agreement

Use the documents in `docs/` as the durable source for product, architecture,
and implementation decisions. Keep documentation proportional to the change;
do not replace user-authored content without an explicit request.
"""


def _handoff(name: str, template_label: str, brief: str) -> str:
    context = brief or "No detailed brief has been supplied yet."
    return f"""# ECC handoff — {name}

## Current verified state

- Project folder initialized from the **{template_label}** starter pack.
- Brief: {context}

## Recent changes

- Initial project documents were created by Hermes WebUI.

## Verification

- Filesystem creation: verified by the WebUI create request.
- Tests: not run for this project yet.
- Commit: not created.
- Deployment: not applicable.
- User verification: pending.

## Constraints and next steps

- Confirm the intended stack and the first delivery milestone.
- Keep this handoff current after every meaningful persisted change.
"""


def create_starter_pack(
    workspace_root: Path,
    folder_name: str,
    template: str,
    brief: str,
) -> dict[str, str]:
    """Create a template-specific project folder below ``workspace_root``.

    ``workspace_root`` must already be trusted by the caller. Every write uses
    the anchored workspace helpers, and an existing destination is never
    modified or merged into.
    """
    name = _folder_name(folder_name)
    template_key = str(template or "blank").strip().lower()
    if template_key not in _TEMPLATES:
        raise ProjectStarterError("Unknown project template.")
    project_brief = _brief(brief)
    root = Path(workspace_root).resolve()
    if not root.is_dir():
        raise ProjectStarterError("Selected workspace is unavailable.")
    target = root / name
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ProjectStarterError("Project folder must stay inside the selected workspace.") from exc
    if target.exists() or target.is_symlink():
        raise ProjectStarterError("A folder with that name already exists in the selected workspace.")

    label, documents = _TEMPLATES[template_key]
    _make_new_dir(root, name)
    try:
        _write(root, target / "AGENTS.md", _agents(name))
        _write(root, target / ".agent" / "ECC_HANDOFF.md", _handoff(name, label, project_brief))
        _write(root, target / "README.md", _document(name, project_brief, "Use this file for the quickest project orientation."))
        for doc in documents:
            topic = doc.removesuffix(".md").replace("_", " ").title()
            _write(root, target / "docs" / doc, _document(topic, project_brief, "Add verified decisions and keep this document current."))
    except Exception:
        try:
            rmtree_anchored(root, target)
        except Exception:
            pass
        raise
    return {"path": str(target), "template": template_key}


def adopt_starter_pack(project_root: Path, template: str, brief: str) -> dict[str, str]:
    """Add only missing Hermes continuity documents to an existing project."""
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ProjectStarterError("Selected project folder is unavailable.")
    template_key = str(template or "blank").strip().lower()
    if template_key not in _TEMPLATES:
        raise ProjectStarterError("Unknown project template.")
    project_brief = _brief(brief)
    label, documents = _TEMPLATES[template_key]
    candidates = {
        root / "AGENTS.md": _agents(root.name),
        root / ".agent" / "ECC_HANDOFF.md": _handoff(root.name, label, project_brief),
        root / "README.md": _document(root.name, project_brief, "Use this file for the quickest project orientation."),
    }
    for doc in documents:
        topic = doc.removesuffix(".md").replace("_", " ").title()
        candidates[root / "docs" / doc] = _document(topic, project_brief, "Add verified decisions and keep this document current.")
    added: dict[str, list[str]] = {"files": [], "dirs": []}
    for directory in (root / ".agent", root / "docs"):
        if not directory.exists() and not directory.is_symlink():
            added["dirs"].append(str(directory))
    try:
        for path, content in candidates.items():
            if path.exists() or path.is_symlink():
                continue
            _write(root, path, content)
            added["files"].append(str(path))
    except Exception:
        rollback_adopted(root, {"added": added})
        raise
    added["dirs"] = [d for d in added["dirs"] if Path(d).is_dir()]
    return {"path": str(root), "template": template_key, "created": str(len(added["files"])), "added": added}


def rollback_adopted(project_root: Path, result: dict) -> None:
    """Undo an adopt: remove only the documents and folders it added."""
    root = Path(project_root).resolve()
    added = (result or {}).get("added") or {}
    new_dirs = [Path(d) for d in added.get("dirs") or []]
    for file_path in added.get("files") or []:
        path = Path(file_path)
        if any(d in path.parents for d in new_dirs):
            continue
        try:
            unlink_anchored(root, path)
        except (OSError, ValueError):
            pass
    for directory in new_dirs:
        try:
            rmtree_anchored(root, directory)
        except (OSError, ValueError):
            pass
