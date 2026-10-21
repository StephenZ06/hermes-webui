"""Create a safe, documented starting point for a Hermes project folder.

The WebUI project record and its on-disk project are created together by the
projects route.  This module owns only the on-disk side so it can be tested
without a running server and so filesystem safety has one clear home.
"""

from __future__ import annotations

import json
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
# key: (label, description, docs/ files). Every template also gets the agent
# continuity files listed in _pack_files().
_TEMPLATES = {
    "blank": ("Blank Project", "Just the continuity files; shape it later.", ()),
    "web": ("Web App", "Sites, dashboards and SaaS front ends.",
            ("PRODUCT.md", "ARCHITECTURE.md", "UI_UX.md", "TESTING.md")),
    "ios": ("iOS App", "iPhone and iPad apps in Swift.",
            ("PRODUCT.md", "ARCHITECTURE.md", "IOS.md", "UI_UX.md", "TESTING.md")),
    "android": ("Android App", "Phone and tablet apps in Kotlin.",
                ("PRODUCT.md", "ARCHITECTURE.md", "ANDROID.md", "UI_UX.md", "TESTING.md")),
    "api": ("API/Backend", "Services, endpoints and data stores.",
            ("PRODUCT.md", "ARCHITECTURE.md", "API.md", "TESTING.md")),
    "cli": ("CLI Tool", "Command-line tools and automation scripts.",
            ("PRODUCT.md", "ARCHITECTURE.md", "CLI.md", "TESTING.md")),
    "data": ("Data / ML", "Analysis, pipelines and model training.",
             ("PRODUCT.md", "DATA.md", "EXPERIMENTS.md", "TESTING.md")),
    "research": ("Research", "Investigations, reviews and write-ups.",
                 ("RESEARCH.md", "SOURCES.md", "FINDINGS.md")),
}


def available_templates() -> tuple[str, ...]:
    return tuple(_TEMPLATES)


def template_catalog() -> list[dict]:
    """Templates with the files each one creates, for the starter wizard."""
    return [
        {"key": key, "label": label, "description": description,
         "files": list(_pack_files("project", key, ""))}
        for key, (label, description, docs) in _TEMPLATES.items()
    ]


def list_child_folders(workspace_root: Path, rel: str = "") -> list[dict]:
    """Visible sub-folders of ``rel`` inside a trusted workspace, sorted by name."""
    root = Path(workspace_root).resolve()
    target = (root / (rel or ".")).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ProjectStarterError("That folder is outside the workspace.") from exc
    if not target.is_dir():
        raise ProjectStarterError("That folder is unavailable.")
    folders = []
    for child in target.iterdir():
        if child.name.startswith(".") or child.is_symlink():
            continue
        try:
            if child.is_dir():
                folders.append({"name": child.name, "path": child.relative_to(root).as_posix()})
        except OSError:
            continue
    return sorted(folders, key=lambda item: item["name"].casefold())


def resolve_parent(workspace_root: Path, rel: str = "") -> Path:
    """Resolve the chosen folder inside a trusted workspace (no escapes)."""
    root = Path(workspace_root).resolve()
    target = (root / (rel or ".")).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ProjectStarterError("That folder is outside the workspace.") from exc
    if not target.is_dir():
        raise ProjectStarterError("That folder is unavailable.")
    return target


def _decisions(answers) -> str:
    lines = []
    for item in answers or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()[:300]
        answer = str(item.get("answer") or "").strip()[:2000]
        if question and answer:
            lines.append(f"- **{question}** {answer}")
    return "\n".join(lines)


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


# Section scaffolds per document. Each heading is a question the document
# must answer; "TBD" markers are deliberate so agents can find gaps quickly.
_DOC_SECTIONS = {
    "PRODUCT.md": ("Product", [
        ("Problem", "Who is struggling, with what, today?"),
        ("Users", "Primary and secondary users, and the context they use it in."),
        ("Goals and success criteria", "Measurable outcomes that mean this project worked."),
        ("Scope", "In scope for the first milestone, and explicitly out of scope."),
        ("Open questions", "Decisions still needed from the owner."),
    ]),
    "ARCHITECTURE.md": ("Architecture", [
        ("Stack", "Languages, frameworks, runtime and key libraries, with versions once chosen."),
        ("Components", "Each component, what it owns, and how they talk to each other."),
        ("Data", "Stores, schemas or formats, and where each piece of state lives."),
        ("Integrations", "External services and APIs, and how credentials are provided (never committed)."),
        ("Constraints and decisions", "Rules the code must keep, with the reason for each."),
    ]),
    "UI_UX.md": ("UI and UX", [
        ("Primary flows", "The few paths users must be able to complete, step by step."),
        ("Design language", "Typography, colour, spacing and components to reuse."),
        ("States", "Loading, empty, error and success for each screen."),
        ("Accessibility", "Keyboard, contrast, screen-reader and motion requirements."),
        ("Responsive targets", "Breakpoints and devices that must be verified."),
    ]),
    "TESTING.md": ("Testing", [
        ("Commands", "How to run the tests, linters and type checks locally."),
        ("Strategy", "What is unit tested, what is integration tested, what is checked manually."),
        ("Definition of done", "Checks that must pass before a change is called complete."),
        ("Known gaps", "Areas without coverage and the risk they carry."),
    ]),
    "IOS.md": ("iOS", [
        ("Targets", "Minimum iOS version, devices and orientations."),
        ("Project setup", "Xcode project, signing approach and schemes (no secrets in the repo)."),
        ("Architecture", "SwiftUI or UIKit, state management and navigation pattern."),
        ("Distribution", "TestFlight and App Store steps, and who owns them."),
    ]),
    "ANDROID.md": ("Android", [
        ("Targets", "minSdk / targetSdk, devices and form factors."),
        ("Project setup", "Gradle modules, build variants and signing approach (no secrets in the repo)."),
        ("Architecture", "Compose or Views, state management and navigation pattern."),
        ("Distribution", "Play Console tracks and release steps."),
    ]),
    "API.md": ("API", [
        ("Endpoints", "Resource, method, request, response and errors for each endpoint."),
        ("Authentication", "How callers authenticate and how secrets are stored."),
        ("Versioning and compatibility", "How breaking changes are introduced."),
        ("Limits", "Rate limits, payload limits and timeouts."),
    ]),
    "CLI.md": ("CLI", [
        ("Commands", "Each command, its arguments, flags and exit codes."),
        ("Configuration", "Config files, environment variables and precedence."),
        ("Output", "Human and machine-readable output formats."),
        ("Distribution", "How the tool is packaged and installed."),
    ]),
    "DATA.md": ("Data", [
        ("Sources", "Where data comes from, its licence, and how it is refreshed."),
        ("Pipeline", "Each step from raw data to output, and where intermediate files live."),
        ("Quality checks", "Validation that runs before data is used."),
        ("Privacy", "Personal or sensitive fields and how they are handled."),
    ]),
    "EXPERIMENTS.md": ("Experiments", [
        ("Log", "One entry per run: date, hypothesis, setup, metrics and result."),
        ("Baselines", "Reference results new runs are compared against."),
        ("Reproducibility", "Seeds, environment and data versions needed to repeat a run."),
    ]),
    "RESEARCH.md": ("Research", [
        ("Question", "The question this research must answer."),
        ("Method", "How sources are found, judged and recorded."),
        ("Deliverable", "What the final output is and who reads it."),
    ]),
    "SOURCES.md": ("Sources", [
        ("Sources", "One entry per source: citation, link, date accessed and reliability notes."),
    ]),
    "FINDINGS.md": ("Findings", [
        ("Findings", "Each finding with the evidence that supports it and its confidence."),
        ("Open threads", "Leads not yet followed up."),
    ]),
}


def _brief_block(brief: str) -> str:
    return brief or "_No brief yet. Ask the owner what this project is for before making product decisions._"


def _doc(name: str, brief: str) -> str:
    title, sections = _DOC_SECTIONS.get(name, (name.removesuffix(".md").replace("_", " ").title(), []))
    body = [f"# {title}", "", "## Project brief", "", _brief_block(brief), ""]
    for heading, prompt in sections:
        body += [f"## {heading}", "", f"<!-- {prompt} -->", "TBD", ""]
    body += ["---", "", "Keep this document true to the code. Record only verified facts; mark guesses as open questions."]
    return "\n".join(body) + "\n"


def _readme(name: str, label: str, brief: str, docs: tuple[str, ...]) -> str:
    links = "\n".join(f"- [{d.removesuffix('.md').replace('_', ' ').title()}](docs/{d})" for d in docs)
    return f"""# {name}

{_brief_block(brief)}

## Getting started

TBD: prerequisites, install and run commands. Keep these copy-pasteable and tested.

## Project map

- [Agent instructions](AGENTS.md): how AI agents must work in this repository.
- [Current status](.agent/PROJECT_STATUS.md) and [handoff](.agent/ECC_HANDOFF.md)
{links}

_Started from the Hermes **{label}** template._
"""


def _agents(name: str, docs: tuple[str, ...] = ()) -> str:
    doc_list = "\n".join(f"- `docs/{d}`" for d in docs) or "- (add docs/ files as the project grows)"
    return f"""# {name}: agent instructions

These rules apply to every AI agent working in this repository.

## Before any change

1. Invoke the **project-lifecycle** skill. It resolves this project in the Hermes
   workspace registry, reads the documents below, and picks the working mode
   (Understand, Plan, Maintain, Implement, Review, Release). A small or
   already-diagnosed task still goes through it; size only changes the mode.
2. Read `.agent/ECC_HANDOFF.md` and `.agent/PROJECT_STATUS.md`.
3. Read the documents relevant to the task:
{doc_list}

## While working

- Keep the change to the requested scope; note adjacent problems instead of fixing them silently.
- Follow the commands and checks in `docs/TESTING.md` (or the README) before calling work done.
- Never commit secrets, tokens, `.env` files or personal data.
- Do not deploy, migrate, push or delete outside the repository without explicit approval.

## Before finishing

Update, in proportion to the change:

- `.agent/ECC_HANDOFF.md`: what changed, what was verified, what is next.
- `.agent/PROJECT_STATUS.md`: current objective, blockers and next action.
- `.agent/TASKS.md`: tick off or add tasks.
- `.agent/CHANGELOG.md`: one dated line per meaningful change.

Keep **changed**, **tested**, **committed**, **deployed** and **user-verified**
as separate states. Never write raw chat logs into these files. Skip the updates
for read-only questions that change nothing.
"""


def _handoff(name: str, template_label: str, brief: str) -> str:
    return f"""# Handoff: {name}

The next agent starts here. Keep it short and current; history belongs in CHANGELOG.md.

## Current state

- Project created from the **{template_label}** template by Hermes WebUI.
- Brief: {brief.splitlines()[0] if brief else "not provided yet"}

## Last change

- Initial project documents created.

## Verification

| State | Status |
| --- | --- |
| Changed | Starter documents written |
| Tested | Not run |
| Committed | No |
| Deployed | Not applicable |
| User-verified | Pending |

## Next steps

1. Confirm the stack and first milestone with the owner.
2. Fill the TBD sections in `docs/` from verified decisions.
3. Set up the repository's run and test commands, then record them in `docs/TESTING.md`.
"""


def _context(name: str, label: str, brief: str) -> str:
    return f"""# Context: {name}

## Purpose

{_brief_block(brief)}

## Paths

- Project root: this folder.
- Agent documents: `.agent/`
- Product and technical documents: `docs/`

## Commands

TBD: install, run, test, lint. Record only commands that have been run successfully.

## Conventions

TBD: naming, formatting, branching and commit style.

_Template: {label}._
"""


def _status(name: str) -> str:
    return f"""# Project status: {name}

## Objective

TBD: the current milestone in one sentence.

## Status

Not started: documents scaffolded, no code yet.

## Blockers

None recorded.

## Validation

Nothing has been run yet.

## Next action

Confirm the stack and first milestone with the owner.
"""


def _tasks() -> str:
    return """# Tasks

## Now

- [ ] Confirm stack and first milestone with the owner
- [ ] Fill the TBD sections in docs/

## Next

- [ ] Set up the run and test commands

## Done

"""


def _changelog(label: str) -> str:
    from datetime import date

    return f"""# Changelog

Dated, factual, newest first. One line per meaningful change.

## {date.today().isoformat()}

- Project created from the Hermes {label} template.
"""


def _pack_files(name: str, template_key: str, brief: str) -> dict[str, str]:
    """Every file a template writes, in display order (relative path → content).

    The single source for create, adopt and the wizard's file preview.
    """
    label, _description, docs = _TEMPLATES[template_key]
    files = {
        "AGENTS.md": _agents(name, docs),
        "README.md": _readme(name, label, brief, docs),
        ".agent/ECC_HANDOFF.md": _handoff(name, label, brief),
        ".agent/CONTEXT.md": _context(name, label, brief),
        ".agent/PROJECT_STATUS.md": _status(name),
        ".agent/TASKS.md": _tasks(),
        ".agent/CHANGELOG.md": _changelog(label),
    }
    for doc in docs:
        files[f"docs/{doc}"] = _doc(doc, brief)
    return files


def create_starter_pack(
    workspace_root: Path,
    folder_name: str,
    template: str,
    brief: str,
    answers=None,
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
    decisions = _decisions(answers)
    if decisions:
        project_brief = f"{project_brief}\n\n### Decisions\n\n{decisions}".strip()
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

    _make_new_dir(root, name)
    try:
        for rel, content in _pack_files(name, template_key, project_brief).items():
            _write(root, target / rel, content)
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
    candidates = {root / rel: content for rel, content in _pack_files(root.name, template_key, project_brief).items()}
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


def register_in_lifecycle_registry(display_name: str, path: Path, registry_file: Path | None = None) -> str | None:
    """Add the project to the Hermes WORKSPACES.yaml registry if it is missing.

    project-lifecycle resolves a repository through this registry before any
    work and stops on unmapped projects, so new and adopted projects are
    registered up front. Append-only: existing entries are never rewritten or
    reordered, and a path already registered under any key is left alone.
    Returns the key used, or None when nothing was written.
    """
    if registry_file is None:
        from api.project_registry import WORKSPACES_REGISTRY_FILE as registry_file  # noqa: N811
    registry_file = Path(registry_file)
    repo_path = str(Path(path).resolve())
    try:
        import yaml

        existing = {}
        if registry_file.is_file():
            data = yaml.safe_load(registry_file.read_text(encoding="utf-8")) or {}
            existing = data.get("projects") if isinstance(data, dict) and isinstance(data.get("projects"), dict) else {}
            if not isinstance(data, dict) or ("projects" in data and not isinstance(data.get("projects"), dict)):
                return None  # unexpected shape: never guess
        for entry in existing.values():
            if isinstance(entry, dict) and str(entry.get("repo_path") or "").rstrip("/") == repo_path.rstrip("/"):
                return None
        base = re.sub(r"[^a-z0-9]+", "-", str(display_name).lower()).strip("-")[:48] or "project"
        key, n = base, 2
        while key in existing:
            key, n = f"{base}-{n}", n + 1
        block = (f"  {key}:\n"
                 f"    display_name: {json.dumps(str(display_name)[:80])}\n"
                 f"    access_mode: local\n"
                 f"    repo_path: {json.dumps(repo_path)}\n"
                 f"    status: confirmed project root\n")
        if not registry_file.is_file() or not registry_file.read_text(encoding="utf-8").strip():
            registry_file.parent.mkdir(parents=True, exist_ok=True)
            registry_file.write_text("projects:\n" + block, encoding="utf-8")
        else:
            text = registry_file.read_text(encoding="utf-8")
            if "projects:" not in text:
                return None
            with registry_file.open("a", encoding="utf-8") as handle:
                handle.write(("" if text.endswith("\n") else "\n") + block)
        return key
    except Exception:
        return None
