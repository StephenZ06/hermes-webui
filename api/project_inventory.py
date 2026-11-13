"""Skills & Tools of one project: what the project folder holds and what the
create-project wizard chose for it.

``inventory`` reads, never writes. Its sources, each item tagged with where it
came from:

* ``.agent/toolkit.json`` -- the manifest ``api.project_toolkit.apply_toolkit``
  writes for the wizard's skills and components, and ``set_skills`` updates.
  Without it, the skills named in AGENTS.md's toolkit block.
* project-local skills -- ``<dir>/<name>/SKILL.md`` under ``.agents/skills``,
  ``.claude/skills``, ``.hermes/skills`` or ``skills`` (where an agent puts a
  skill installed from a repo).
* packages -- ``package.json`` dependencies, ``requirements.txt`` and
  ``pyproject.toml`` ``[project] dependencies``.
* MCP servers -- ``.mcp.json`` ``mcpServers``.

Every read stays inside the project folder: symlinks are skipped, file sizes
and item counts are capped. ``set_skills`` is the one writer; it changes only
the manifest and the skill lines inside AGENTS.md's toolkit markers.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import yaml

from api.project_toolkit import BEGIN, END

MANIFEST = Path(".agent") / "toolkit.json"
SKILL_DIRS = (".agents/skills", ".claude/skills", ".hermes/skills", "skills")
MAX_ITEMS = 400
MAX_READ = 512 * 1024
SKILLS_INTRO = "Skills chosen for this project. Load each one before the work it covers:"
_SKILL_LINE = re.compile(r"^- Before work this skill covers, load the `([^`]+)` skill\.$")


def skill_line(name: str) -> str:
    return f"- Before work this skill covers, load the `{name}` skill."


def _read(path: Path) -> str | None:
    """Text of a regular file inside the project, or None."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_READ:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _inside(root: Path, path: Path) -> bool:
    try:
        return path.resolve() == root or root in path.resolve().parents
    except OSError:
        return False


def read_manifest(root: Path) -> dict:
    text = _read(root / MANIFEST)
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    skills = [s for s in data.get("skills") or [] if isinstance(s, dict) and isinstance(s.get("name"), str)]
    comps = [c for c in data.get("components") or [] if isinstance(c, dict) and isinstance(c.get("name"), str)]
    icons = [p for p in data.get("icon_packs") or [] if isinstance(p, dict) and isinstance(p.get("name"), str)]
    return {"version": 1, "skills": skills, "components": comps, "icon_packs": icons}


def write_manifest(root: Path, data: dict) -> None:
    path = root / MANIFEST
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("The project's .agent folder is a link; it was left alone.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def agents_skills(root: Path) -> list[str]:
    """Skills named inside AGENTS.md's toolkit block."""
    text = _read(root / "AGENTS.md") or ""
    if BEGIN not in text or END not in text:
        return []
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    return [m.group(1) for line in block.splitlines() if (m := _SKILL_LINE.match(line.strip()))]


def _front(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    try:
        meta = yaml.safe_load(parts[1]) if len(parts) > 2 else {}
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def _first_line(text: str) -> str:
    body = text.split("---", 2)[2] if text.startswith("---") and text.count("---") >= 2 else text
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:240]
    return ""


def _local_skills(root: Path) -> list[dict]:
    out = []
    for rel in SKILL_DIRS:
        base = root / rel
        if base.is_symlink() or not base.is_dir() or not _inside(root, base):
            continue
        for skill_dir in sorted(base.iterdir())[:MAX_ITEMS]:
            if skill_dir.is_symlink() or not skill_dir.is_dir():
                continue
            text = _read(skill_dir / "SKILL.md")
            if text is None:
                continue
            meta = _front(text)
            out.append({
                "kind": "skill", "name": str(meta.get("name") or skill_dir.name)[:80],
                "description": str(meta.get("description") or _first_line(text))[:240],
                "source": "folder", "where": f"{rel}/{skill_dir.name}/SKILL.md",
                "added_at": _mtime(skill_dir / "SKILL.md"), "removable": False})
    return out


def _packages(root: Path) -> list[dict]:
    out = []
    pkg = root / "package.json"
    text = _read(pkg)
    if text:
        try:
            data = json.loads(text)
        except ValueError:
            data = {}
        when = _mtime(pkg)
        for field, label in (("dependencies", "npm"), ("devDependencies", "npm · dev")):
            deps = data.get(field) if isinstance(data, dict) else None
            for name, version in (deps.items() if isinstance(deps, dict) else []):
                out.append({"kind": "package", "name": str(name)[:120], "description": f"{label} {version}"[:120],
                            "source": "folder", "where": "package.json", "added_at": when, "removable": False})
    req = root / "requirements.txt"
    text = _read(req)
    if text:
        when = _mtime(req)
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0]
            if name:
                out.append({"kind": "package", "name": name[:120], "description": f"pip {line}"[:120],
                            "source": "folder", "where": "requirements.txt", "added_at": when, "removable": False})
    pyproject = root / "pyproject.toml"
    text = _read(pyproject)
    if text:
        try:
            import tomllib
            deps = (tomllib.loads(text).get("project") or {}).get("dependencies") or []
        except Exception:
            deps = []
        when = _mtime(pyproject)
        for dep in deps if isinstance(deps, list) else []:
            name = re.split(r"[<>=!~\[; ]", str(dep), maxsplit=1)[0]
            if name:
                out.append({"kind": "package", "name": name[:120], "description": f"pip {dep}"[:120],
                            "source": "folder", "where": "pyproject.toml", "added_at": when, "removable": False})
    return out


def _mcp(root: Path) -> list[dict]:
    path = root / ".mcp.json"
    text = _read(path)
    try:
        servers = (json.loads(text) or {}).get("mcpServers") if text else None
    except (ValueError, AttributeError):
        servers = None
    when = _mtime(path)
    out = []
    for name, cfg in (servers.items() if isinstance(servers, dict) else []):
        cmd = ""
        if isinstance(cfg, dict):
            cmd = str(cfg.get("url") or " ".join([str(cfg.get("command") or "")] + [str(a) for a in cfg.get("args") or [] if isinstance(a, (str, int))][:3])).strip()
        out.append({"kind": "mcp", "name": str(name)[:120], "description": cmd[:160],
                    "source": "folder", "where": ".mcp.json", "added_at": when, "removable": False})
    return out


def project_root(project: dict) -> Path | None:
    raw = str(project.get("workspace_path") or "").strip()
    if not raw:
        return None
    try:
        root = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    return root if root.is_dir() else None


def inventory(project: dict, *, installed: dict[str, dict]) -> dict:
    """Skills, components, packages and MCP servers of ``project``.

    ``installed`` maps the profile's installed skill names to their details
    (description, category); wizard-chosen skills use it for their text.
    """
    root = project_root(project)
    if root is None:
        return {"folder": None, "items": [], "addable": []}
    manifest = read_manifest(root)
    items: list[dict] = []
    chosen = {s["name"]: s for s in manifest["skills"]}
    listed = agents_skills(root)
    agents_when = _mtime(root / "AGENTS.md")
    for name in list(chosen) + [n for n in listed if n not in chosen]:
        entry = chosen.get(name, {})
        info = installed.get(name) or {}
        items.append({
            "kind": "skill", "name": name, "description": str(info.get("description") or "")[:240],
            "category": str(info.get("category") or ""), "source": entry.get("source") or "wizard",
            "where": "AGENTS.md", "added_at": entry.get("added_at") or agents_when,
            "removable": True, "missing": name not in installed})
    for comp in manifest["components"]:
        files = [str(f) for f in comp.get("files") or []][:40]
        items.append({
            "kind": "component", "name": comp["name"][:120],
            "description": " · ".join(x for x in (str(comp.get("library_name") or ""), str(comp.get("role") or "").replace("-", " ")) if x),
            "source": comp.get("source") or "wizard", "where": files[0] if files else "docs/UI_UX.md",
            "files": files, "link": str(comp.get("link") or "")[:400],
            "added_at": comp.get("added_at") or _mtime(root / MANIFEST), "removable": False})
    from api.project_toolkit import ICON_PACKS
    packs = {p["name"]: p for p in ICON_PACKS}
    for entry in manifest["icon_packs"]:
        pack = packs.get(entry["name"]) or {}
        items.append({
            "kind": "icons", "name": entry["name"][:120], "description": str(pack.get("description") or "")[:240],
            "source": entry.get("source") or "added", "where": "AGENTS.md", "link": str(pack.get("browse") or pack.get("repo") or "")[:400],
            "added_at": entry.get("added_at") or _mtime(root / MANIFEST), "removable": False})
    seen = {(i["kind"], i["name"]) for i in items}
    for item in _local_skills(root) + _packages(root) + _mcp(root):
        if (item["kind"], item["name"]) not in seen:
            seen.add((item["kind"], item["name"]))
            items.append(item)
    in_project = {i["name"] for i in items if i["kind"] == "skill"}
    return {"folder": str(root), "items": items[:MAX_ITEMS],
            "addable": [{"name": n, "description": str(installed[n].get("description") or "")[:240],
                         "category": str(installed[n].get("category") or "")}
                        for n in sorted(installed) if n not in in_project]}


def _rewrite_agents(root: Path, names: list[str]) -> None:
    path = root / "AGENTS.md"
    if path.is_symlink():
        raise ValueError("AGENTS.md is a link; it was left alone.")
    text = _read(path) if path.exists() else ""
    if text is None:
        raise ValueError("AGENTS.md could not be read.")
    lines = ([SKILLS_INTRO, ""] + [skill_line(n) for n in names] + [""]) if names else []
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        block, tail = rest.split(END, 1)
        kept = [ln for ln in block.strip("\n").splitlines()
                if ln.strip() != SKILLS_INTRO and not _SKILL_LINE.match(ln.strip())]
        # Collapse the blank lines the removed skill lines leave behind.
        tidy: list[str] = []
        for ln in kept:
            if ln.strip() == "" and tidy and tidy[-1].strip() == "":
                continue
            tidy.append(ln)
        at = next((i + 1 for i, ln in enumerate(tidy) if ln.strip() == "## Project toolkit"), None)
        if at is None:
            tidy = ["## Project toolkit", ""] + tidy
            at = 1
        while at < len(tidy) and tidy[at].strip() == "":
            tidy.pop(at)
        body = tidy[:at] + [""] + lines + tidy[at:]
        while body and body[-1].strip() == "":
            body.pop()
        text = head + BEGIN + "\n" + "\n".join(body) + "\n" + END + tail
    elif names:
        text = (text or "").rstrip() + ("\n\n" if text.strip() else "") + BEGIN + "\n" + "\n".join(
            ["## Project toolkit", ""] + lines).rstrip() + "\n" + END + "\n"
    else:
        return
    path.write_text(text, encoding="utf-8")


def set_skills(project: dict, *, add: list[str], remove: list[str], installed: set[str]) -> list[str]:
    """Add installed skills to the project, or take wizard-listed ones off it.
    Returns the project's skill list afterwards."""
    root = project_root(project)
    if root is None:
        raise ValueError("Set a workspace folder for this project first.")
    unknown = [n for n in add if n not in installed]
    if unknown:
        raise ValueError(f"Not an installed skill: {unknown[0]}")
    manifest = read_manifest(root)
    names = [s["name"] for s in manifest["skills"]]
    for n in agents_skills(root):
        if n not in names:
            names.append(n)
            manifest["skills"].append({"name": n, "source": "wizard", "added_at": _mtime(root / "AGENTS.md")})
    now = time.time()
    for n in add:
        if n not in names:
            names.append(n)
            manifest["skills"].append({"name": n, "source": "added", "added_at": now})
    drop = set(remove)
    names = [n for n in names if n not in drop]
    manifest["skills"] = [s for s in manifest["skills"] if s["name"] not in drop]
    _rewrite_agents(root, names)
    write_manifest(root, manifest)
    return names
