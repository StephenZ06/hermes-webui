"""Create a safe, documented starting point for a Hermes project folder.

The WebUI project record and its on-disk project are created together by the
projects route.  This module owns only the on-disk side so it can be tested
without a running server and so filesystem safety has one clear home.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from api.workspace import (
    _DIR_FD_OK,
    _O_DIRECTORY,
    _O_NOFOLLOW,
    open_anchored_create_fd,
    open_anchored_write_fd,
    rmtree_anchored,
    unlink_anchored,
)

logger = logging.getLogger(__name__)


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
            ("PRODUCT.md", "ARCHITECTURE.md", "UI_UX.md", "TESTING.md", "PERFORMANCE.md", "SECURITY.md")),
    "ios": ("iOS App", "iPhone and iPad apps in Swift.",
            ("PRODUCT.md", "ARCHITECTURE.md", "IOS.md", "UI_UX.md", "TESTING.md", "PERFORMANCE.md")),
    "android": ("Android App", "Phone and tablet apps in Kotlin.",
                ("PRODUCT.md", "ARCHITECTURE.md", "ANDROID.md", "UI_UX.md", "TESTING.md", "PERFORMANCE.md")),
    "api": ("API/Backend", "Services, endpoints and data stores.",
            ("PRODUCT.md", "ARCHITECTURE.md", "API.md", "TESTING.md", "SECURITY.md")),
    "website": ("Website", "Marketing sites, portfolios and content pages.",
                ("PRODUCT.md", "PAGES.md", "UI_UX.md", "SEO.md", "TESTING.md", "PERFORMANCE.md", "SECURITY.md")),
    "cli": ("CLI Tool", "Command-line tools and automation scripts.",
            ("PRODUCT.md", "ARCHITECTURE.md", "CLI.md", "TESTING.md")),
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
    "PAGES.md": ("Pages and content", [
        ("Sitemap", "Every page, its URL and what it is for."),
        ("Content", "Headings, copy and calls to action for each page, and who supplies them."),
        ("Media", "Images, video and fonts: source, licence and the sizes each page needs."),
        ("Editing", "How content is changed after launch (files, a CMS, or a form), and by whom."),
    ]),
    "SEO.md": ("SEO, performance and hosting", [
        ("Metadata", "Title, description and social preview for each page; sitemap.xml and robots.txt."),
        ("Performance budget", "Target load time and page weight, and how they are measured."),
        ("Analytics", "What is tracked, with what tool, and the consent it needs."),
        ("Hosting and domain", "Where the site is deployed, the domain and DNS, and who owns the accounts (no secrets in the repo)."),
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


# The owner's performance checklist, given to every web, website and app
# project as docs/PERFORMANCE.md (between hermes:performance markers, which
# the setup agent keeps word for word).
_PERFORMANCE_DOC = Path(__file__).with_name("starter_performance.md")
# The owner's security checklist (the SaaS web app one), the same way, between
# hermes:security markers. Given to web, website and API projects.
_SECURITY_DOC = Path(__file__).with_name("starter_security.md")
_CHECKLIST_DOCS = {"PERFORMANCE.md": _PERFORMANCE_DOC, "SECURITY.md": _SECURITY_DOC}


def _doc(name: str, brief: str) -> str:
    if name in _CHECKLIST_DOCS:
        return _CHECKLIST_DOCS[name].read_text(encoding="utf-8")
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
Dependencies install inside this project (a `.venv` for Python, `node_modules`
from `package.json` for JavaScript), never globally.

## Project map

- [Agent instructions](AGENTS.md): how AI agents must work in this repository.
- [Current status](.agent/PROJECT_STATUS.md) and [handoff](.agent/ECC_HANDOFF.md)
{links}

_Started from the Hermes **{label}** template._
"""


def _agents(name: str, docs: tuple[str, ...] = ()) -> str:
    doc_list = "\n".join(f"- `docs/{d}`" for d in docs) or "- (add docs/ files as the project grows)"
    perf = ("- <!-- hermes:performance:begin -->Before calling any work done, run `docs/PERFORMANCE.md`: do every\n"
            "  item that applies, skip the rest with a reason, and end your summary with a short\n"
            "  \"Performance checklist\" note (applied, already in place, skipped and why).<!-- hermes:performance:end -->\n"
            if "PERFORMANCE.md" in docs else "")
    sec = ("- <!-- hermes:security:begin -->Before calling any work done, run `docs/SECURITY.md`: do every\n"
           "  item that applies, skip the rest with a reason, and end your summary with a short\n"
           "  \"Security checklist\" note (applied, already in place, skipped and why).<!-- hermes:security:end -->\n"
           if "SECURITY.md" in docs else "")
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
{perf}{sec}- Install dependencies inside the project only: a virtual environment in `.venv`
  for Python (`python -m venv .venv`, then its own `pip`), `node_modules` from the
  project's `package.json` (or `npx`) for JavaScript, and the platform's own
  project-local tooling elsewhere. Never install globally: no `pip install`
  outside the environment, no `npm install -g`, no `sudo`. Keep `.venv/` and
  `node_modules/` out of version control.
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
    return {rel: content + _related(rel, files) for rel, content in files.items()}


def _related(rel: str, files: dict[str, str]) -> str:
    """A closing list linking each document to every other one in the pack,
    with paths relative to the document, so the set reads as one connected
    whole in any Markdown viewer (GitHub, Obsidian, the Files page)."""
    import posixpath

    here = posixpath.dirname(rel) or "."
    lines = []
    for other in files:
        if other == rel:
            continue
        title = posixpath.basename(other).removesuffix(".md").replace("_", " ")
        title = title if title.isupper() and len(title) <= 6 else title.title()
        lines.append(f"- [{title}]({posixpath.relpath(other, here)}) (`{other}`)")
    return "\n## Related documents\n\n" + "\n".join(lines) + "\n"


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
    pack = _pack_files(root.name, template_key, project_brief)
    # A project with its own docs/PERFORMANCE.md (or SECURITY.md) keeps it; the
    # owner's checklist goes beside it as PERFORMANCE_CHECKLIST.md and the rule
    # points there.
    for doc, (begin, _end) in _RULE_MARKERS.items():
        own = root / "docs" / doc
        if f"docs/{doc}" in pack and (own.is_symlink() or (own.exists() and begin not in _read_text(own))):
            stem = doc.removesuffix(".md")
            pack = {rel.replace(doc, f"{stem}_CHECKLIST.md"): text.replace(doc, f"{stem}_CHECKLIST.md")
                    for rel, text in pack.items()}
    candidates = {root / rel: content for rel, content in pack.items()}
    added: dict[str, list[str]] = {"files": [], "dirs": []}
    for directory in (root / ".agent", root / "docs"):
        if not directory.exists() and not directory.is_symlink():
            added["dirs"].append(str(directory))
    try:
        for path, content in candidates.items():
            if path.exists() or path.is_symlink():
                if path.name == "AGENTS.md" and path.parent == root:
                    what = _append_hermes_section(root, path, candidates[path])
                    if what == "section":
                        added["appended"] = [str(path)]
                    elif what:
                        # "performance", "security" or both ("performance+security").
                        for rule in what.split("+"):
                            added["perf_appended" if rule == "performance" else "security_appended"] = [str(path)]
                continue
            _write(root, path, content)
            added["files"].append(str(path))
    except Exception:
        rollback_adopted(root, {"added": added})
        raise
    added["dirs"] = [d for d in added["dirs"] if Path(d).is_dir()]
    return {"path": str(root), "template": template_key, "created": str(len(added["files"])), "added": added}


HERMES_BEGIN = "<!-- hermes:begin -->"
HERMES_END = "<!-- hermes:end -->"
PERF_BEGIN = "<!-- hermes:performance:begin -->"
SEC_BEGIN = "<!-- hermes:security:begin -->"
# docs file -> (begin marker, end marker) of the rule that runs it.
_RULE_MARKERS = {"PERFORMANCE.md": (PERF_BEGIN, "<!-- hermes:performance:end -->"),
                 "SECURITY.md": (SEC_BEGIN, "<!-- hermes:security:end -->")}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _rewrite(root: Path, path: Path, content: str) -> None:
    fd = open_anchored_write_fd(root, path)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _append_hermes_section(root: Path, path: Path, generated: str) -> str:
    """Add Hermes' continuity rules to a project's own AGENTS.md, once.

    The user's text is kept as it is; the rules go in a section between
    ``HERMES_BEGIN`` and ``HERMES_END`` that ``rollback_adopted`` removes.
    """
    if path.is_symlink() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    if HERMES_BEGIN in text:
        # Adopted before a checklist rule existed: add just that rule to the
        # Hermes section, once.
        added = []
        for name, (begin, end) in _RULE_MARKERS.items():
            rule = next((line for line in generated.splitlines(keepends=False) if begin in line), "")
            if rule and begin not in text and HERMES_END in text:
                start = generated.index(rule)
                block = generated[start:generated.index(end, start) + len(end)]
                head, tail = text.split(HERMES_END, 1)
                text = head.rstrip("\n") + "\n\n" + block + "\n" + HERMES_END + tail
                added.append(name.removesuffix(".md").lower())
        if added:
            _rewrite(root, path, text)
        return "+".join(added)
    rules = generated.split("## Before any change", 1)[-1].split("\n## Related documents", 1)[0].strip()
    section = (f"{HERMES_BEGIN}\n## Hermes continuity\n\nAdded when Hermes adopted this project. "
               "These rules sit alongside the ones above.\n\n### Before any change\n\n"
               + rules.replace("\n## ", "\n### ") + f"\n{HERMES_END}\n")
    _rewrite(root, path, text.rstrip("\n") + "\n\n" + section)
    return "section"


def _remove_hermes_section(root: Path, path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    if HERMES_BEGIN not in text or HERMES_END not in text:
        return
    head, rest = text.split(HERMES_BEGIN, 1)
    tail = rest.split(HERMES_END, 1)[1].lstrip("\n")
    head = head.rstrip("\n") + "\n"
    _rewrite(root, path, head + ("\n" + tail if tail else ""))


def _remove_rule(root: Path, path: Path, begin: str, end: str) -> None:
    """Take out only a checklist rule an adopt added to an older Hermes section."""
    text = _read_text(path)
    if begin not in text or end not in text:
        return
    start = text.rfind("\n", 0, text.index(begin)) + 1
    stop = text.index(end, start) + len(end)
    head = text[:start].rstrip("\n")
    _rewrite(root, path, head + "\n" + text[stop:].lstrip("\n"))


def rollback_adopted(project_root: Path, result: dict) -> None:
    """Undo an adopt: remove only the documents and folders it added."""
    root = Path(project_root).resolve()
    added = (result or {}).get("added") or {}
    for appended in added.get("appended") or []:
        try:
            _remove_hermes_section(root, Path(appended))
        except (OSError, ValueError):
            pass
    for key, doc in (("perf_appended", "PERFORMANCE.md"), ("security_appended", "SECURITY.md")):
        for appended in added.get(key) or []:
            try:
                _remove_rule(root, Path(appended), *_RULE_MARKERS[doc])
            except (OSError, ValueError):
                pass
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


def unregister_from_lifecycle_registry(key: str, path: Path, registry_file: Path | None = None) -> bool:
    """Remove the entry ``register_in_lifecycle_registry`` added for ``path``.

    Only the block under ``key`` is removed, and only when its ``repo_path``
    is still ``path``; anything else in the file is left byte for byte. An
    entry someone edited to point elsewhere is kept. Returns True when removed.
    """
    if not key:
        return False
    if registry_file is None:
        from api.project_registry import WORKSPACES_REGISTRY_FILE as registry_file  # noqa: N811
    registry_file = Path(registry_file)
    try:
        import yaml

        if not registry_file.is_file():
            return False
        text = registry_file.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        entry = (data.get("projects") or {}).get(key) if isinstance(data, dict) else None
        if not isinstance(entry, dict):
            return False
        if str(entry.get("repo_path") or "").rstrip("/") != str(Path(path).resolve()).rstrip("/"):
            return False
        lines = text.splitlines(keepends=True)
        start = next((i for i, line in enumerate(lines) if line.rstrip("\r\n") == f"  {key}:"), None)
        if start is None:
            return False
        end = start + 1
        while end < len(lines) and (lines[end].startswith("    ") or not lines[end].strip()):
            end += 1
        # Keep a blank line that separates the next entry.
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        kept = "".join(lines[:start] + lines[end:])
        check = yaml.safe_load(kept) or {}
        if not isinstance(check, dict) or key in (check.get("projects") or {}):
            return False  # unexpected layout: never guess
        registry_file.write_text(kept, encoding="utf-8")
        return True
    except Exception:
        logger.warning("Could not remove %s from the workspace registry", key, exc_info=True)
        return False
