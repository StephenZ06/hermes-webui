"""Project builder toolkit: the skills, look and UI components chosen in the
create-project wizard, and what they write into the new project.

The wizard sends ``{"look", "skills", "components"}``. ``normalize_toolkit``
keeps only installed skills and catalogued components (see
``api.library_catalog``); ``apply_toolkit`` writes marked sections into
``AGENTS.md`` and ``docs/UI_UX.md`` and copies the chosen copy-paste component
files into ``vendor/ui/<library>/``. ``kickoff_message`` is the first message
"Create & start building" sends.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from api import library_catalog as lc

BEGIN = "<!-- hermes:toolkit:begin -->"
END = "<!-- hermes:toolkit:end -->"

_PLATFORM = {"web": "web", "website": "web", "ios": "ios", "android": "android"}
_DEFAULT_FRAMEWORK = {"web": "react", "website": "vanilla", "ios": "swiftui", "android": "compose"}
_TEMPLATE_HINTS = {
    "web": "ui ux design frontend web react css component dashboard accessibility test",
    "website": "seo ui ux design web website landing content copy marketing frontend css page accessibility",
    "ios": "ios swift swiftui mobile ui ux design apple app test",
    "android": "android kotlin compose mobile ui ux design app test",
    "api": "api backend server database endpoint test security deploy",
    "cli": "cli command terminal shell script automation tool",
    "research": "research source paper writing literature citation analysis",
    "blank": "",
}
_STOP = set("the and for with that this from into your our are was were has have will can a an in of to on at by "
            "it its be as or is we us they them their want wants need needs well very more most".split())


def is_visual(template: str) -> bool:
    return template in _PLATFORM


def default_framework(template: str) -> str:
    return _DEFAULT_FRAMEWORK.get(template, "")


def platform_for(template: str, framework: str) -> str:
    if framework in ("react-native", "flutter"):
        return framework
    return _PLATFORM.get(template, "web")


def _words(text: str) -> set[str]:
    out = set()
    for word in re.findall(r"[a-z0-9]+", str(text or "").lower()):
        if len(word) < 2 or word in _STOP:
            continue
        out.add(word[:-1] if len(word) > 3 and word.endswith("s") else word)
    return out


def suggest_skills(skills: list[dict], *, template: str, brief: str, limit: int = 5) -> list[dict]:
    """Every skill with a score; the best ``limit`` scoring 2 or more are recommended."""
    hints = _words(_TEMPLATE_HINTS.get(template, ""))
    brief_words = _words(brief)
    scored = []
    for skill in skills:
        name = str(skill.get("name") or "")
        if not name:
            continue
        own = _words(" ".join([name.replace("-", " ").replace("_", " "), str(skill.get("category") or ""),
                               str(skill.get("description") or "")]))
        score = 2 * len(own & hints) + len(own & brief_words)
        scored.append({"name": name, "category": str(skill.get("category") or ""),
                       "description": str(skill.get("description") or "")[:240], "score": score, "recommended": False})
    scored.sort(key=lambda s: (-s["score"], s["name"]))
    for item in scored[:limit]:
        item["recommended"] = item["score"] >= 2
    return scored


def normalize_toolkit(raw, *, template: str, libraries_root: Path, skill_names: set[str]) -> dict | None:
    if not isinstance(raw, dict):
        return None
    from api.project_starter_agent import parse_look

    look = parse_look(raw.get("look"), palette_source="custom") if is_visual(template) else None
    if look and not look["framework"]:
        look["framework"] = default_framework(template)
    skills = []
    for name in raw.get("skills") or []:
        if isinstance(name, str) and name in skill_names and name not in skills:
            skills.append(name)
    components = []
    if is_visual(template):
        wanted = [(str(c.get("library") or ""), str(c.get("slug") or "")) for c in raw.get("components") or [] if isinstance(c, dict)]
        index = {}
        for lib in lc.list_libraries(libraries_root):
            for comp in lib["components"]:
                index[(lib["slug"], comp["slug"])] = {
                    "library": lib["slug"], "library_name": lib["name"], "slug": comp["slug"], "name": comp["name"],
                    "role": comp["role"], "kind": lib["kind"], "install": lib["install"], "source": lib["source"],
                    "demo": comp["demo"], "files": comp["files"]}
        for key in wanted:
            if key in index and index[key] not in components:
                components.append(index[key])
    return {"look": look, "skills": skills[:20], "components": components[:40]}


def _upsert(path: Path, block: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    section = f"{BEGIN}\n{block.strip()}\n{END}"
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        text = head + section + rest.split(END, 1)[1]
    else:
        text = text.rstrip() + "\n\n" + section + "\n"
    path.write_text(text, encoding="utf-8")


def _label(key: str) -> str:
    return {"react-native": "React Native", "swiftui": "SwiftUI", "vanilla": "plain HTML, CSS and JavaScript"}.get(
        key, key.replace("-", " ").title() if key else "")


def _copy_files(project: Path, comp: dict, libraries_root: Path) -> list[str]:
    if comp["kind"] != "copy-paste":
        return []
    try:
        source = lc.safe_child(libraries_root, comp["library"], "source")
    except ValueError:
        return []
    copied = []
    for rel in comp.get("files") or []:
        try:
            src = lc.safe_child(source, *[p for p in str(rel).split("/") if p])
        except ValueError:
            continue
        if not src.is_file() or src.is_symlink():
            continue
        dest = (project / "vendor" / "ui" / comp["library"] / src.relative_to(source)).resolve()
        if project.resolve() not in dest.parents:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied.append(dest.relative_to(project.resolve()).as_posix())
    return copied


def _look_lines(look: dict) -> list[str]:
    lines = [f"- Style: **{look['style'].title()}**", f"- Motion: **{look['motion'].title()}**"]
    if look.get("framework"):
        lines.append(f"- Built with: {_label(look['framework'])}" + (" and Tailwind CSS" if look.get("tailwind") else ""))
    if look.get("why"):
        lines.append(f"- Why: {look['why']}")
    if look.get("palette"):
        from api.project_palette import palette_lines
        lines += palette_lines(look["palette"])
    return lines


def apply_toolkit(project: Path, toolkit: dict | None, *, libraries_root: Path) -> list[str]:
    """Write the toolkit into ``project``; returns the project-relative files written."""
    if not toolkit or not (toolkit.get("look") or toolkit.get("skills") or toolkit.get("components")):
        return []
    project = Path(project)
    written: list[str] = []
    comp_lines = []
    for comp in toolkit.get("components") or []:
        copied = _copy_files(project, comp, libraries_root)
        written += copied
        how = {"npm": f"install with `{comp['install']}` (inside the project)" if comp.get("install") else "install from npm inside the project",
               "copy-paste": "copied to " + ", ".join(f"`{c}`" for c in copied) if copied else "copy its code from the source link",
               "link": "follow the source link"}.get(comp["kind"], "see the source link")
        link = comp.get("demo") or comp.get("source") or ""
        comp_lines.append(f"- **{comp['name']}** ({_label(comp['role'])}, from {comp['library_name']}): {how}."
                          + (f" [{link}]({link})" if link else ""))
    look = toolkit.get("look")
    ui_doc = project / "docs" / "UI_UX.md"
    if ui_doc.exists() and (look or comp_lines):
        block = []
        if look:
            block += ["## Look and feel", "", *_look_lines(look), ""]
        if comp_lines:
            block += ["## Approved components", "",
                      "Chosen in the create-project wizard. Use these before writing new UI from scratch.", "", *comp_lines, ""]
        _upsert(ui_doc, "\n".join(block))
        written.append("docs/UI_UX.md")
    rules = ["## Project toolkit", ""]
    skills = toolkit.get("skills") or []
    if skills:
        rules += ["Skills chosen for this project. Load each one before the work it covers:", ""]
        rules += [f"- Before work this skill covers, load the `{name}` skill." for name in skills]
        rules.append("")
    if look and not ui_doc.exists():
        rules += ["Look and feel:", "", *_look_lines(look), ""]
    if comp_lines:
        where = "`docs/UI_UX.md`" if ui_doc.exists() else "below"
        rules += [f"Use only the approved components listed in {where}; ask before adding another UI library.",
                  "Install every dependency inside the project, never globally.", ""]
        if not ui_doc.exists():
            rules += comp_lines + [""]
    _upsert(project / "AGENTS.md", "\n".join(rules))
    written.append("AGENTS.md")
    return written


def kickoff_message(name: str, template: str, toolkit: dict | None) -> str:
    """The first message "Create & start building" sends in the new project chat."""
    parts = [f"Build version 1 of \"{name}\" now.",
             "Read AGENTS.md, .agent/ECC_HANDOFF.md and the docs it links first, then:"]
    steps = ["Set up the stack recorded in the docs, installing every dependency inside the project "
             "(a .venv or node_modules), never globally."]
    if toolkit and toolkit.get("look"):
        steps.append("Follow the look and feel and use the approved components in docs/UI_UX.md.")
    if toolkit and toolkit.get("skills"):
        steps.append("Load the project skills named in AGENTS.md before the work they cover.")
    steps += ["Build the first working version of what the brief describes, page by page or screen by screen.",
              "Run it and its tests once to prove it works.",
              "Update .agent/ECC_HANDOFF.md, .agent/PROJECT_STATUS.md, .agent/TASKS.md and .agent/CHANGELOG.md.",
              "Finish by telling me exactly how to open the preview."]
    return "\n".join(parts + [f"{i}. {s}" for i, s in enumerate(steps, 1)])
