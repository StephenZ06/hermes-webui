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


def is_visual(template: str) -> bool:
    return template in _PLATFORM


def default_framework(template: str) -> str:
    return _DEFAULT_FRAMEWORK.get(template, "")


def platform_for(template: str, framework: str) -> str:
    if framework in ("react-native", "flutter"):
        return framework
    return _PLATFORM.get(template, "web")


def _words(text: str) -> set[str]:
    return lc.words(text)


def resolve_needs(template: str, raw) -> list[str]:
    """What the app needs: the planner's list, else the template's defaults."""
    return lc.parse_needs(raw) or list(lc.TEMPLATE_NEEDS.get(template, []))


def suggest_skills(skills: list[dict], *, template: str, brief: str, needs: list[str] | None = None,
                   limit: int = 6) -> list[dict]:
    """Every skill with a score; the best ``limit`` scoring 2 or more are recommended,
    imported skills that fit the project first.

    A word the brief shares with a skill counts twice as much as a word from
    the template's hints, so a detailed brief decides the picks; ``fit`` lists
    the brief's words a skill matched. ``needs`` (see ``library_catalog.NEEDS``)
    add what the app needs but the brief may not say; ``needs`` on a skill
    lists the ones it serves."""
    hints = _words(_TEMPLATE_HINTS.get(template, ""))
    forms = lc.word_forms(brief)
    brief_words = set(forms)
    needs = lc.parse_needs(needs or [])
    need_words = {n: lc.need_brief_words([n]) for n in needs}
    scored = []
    for skill in skills:
        name = str(skill.get("name") or "")
        if not name:
            continue
        own = _words(" ".join([name.replace("-", " ").replace("_", " "), str(skill.get("category") or ""),
                               str(skill.get("description") or "")]))
        fit = sorted(own & brief_words)
        served = [n for n in needs if len(own & need_words[n]) >= 1]
        score = len(own & hints) + 2 * len(fit) + 2 * min(2, len(served))
        scored.append({"name": name, "category": str(skill.get("category") or ""),
                       "description": str(skill.get("description") or "")[:240], "score": score,
                       "fit": [forms[w] for w in fit[:4]], "needs": [lc.NEEDS[n] for n in served][:3],
                       "imported": bool(skill.get("imported")), "recommended": False})
    # Skills the user imported come ahead of built-ins, but only when they fit the project.
    scored.sort(key=lambda s: (not (s["imported"] and s["score"] >= 2), -s["score"], s["name"]))
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
    return {"look": look, "skills": skills[:20], "components": components[:40], "needs": lc.parse_needs(raw.get("needs"))}


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
    # A catalogue entry without a file list falls back to the library's own registry.
    for rel in comp.get("files") or lc.registry_files(source, comp.get("slug") or ""):
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
    if look.get("custom"):
        from api.project_look import custom_lines
        lines += custom_lines(look["custom"])
    if look.get("palette"):
        from api.project_palette import palette_lines
        lines += palette_lines(look["palette"])
    return lines


def apply_toolkit(project: Path, toolkit: dict | None, *, libraries_root: Path) -> list[str]:
    """Write the toolkit into ``project``; returns the project-relative files written."""
    if not toolkit or not (toolkit.get("look") or toolkit.get("skills") or toolkit.get("components") or toolkit.get("needs")):
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
    needs = lc.parse_needs(toolkit.get("needs"))
    product = project / "docs" / "PRODUCT.md"
    if needs:
        lines = _needs_lines(needs, toolkit.get("components") or [])
        if product.exists():
            _upsert(product, "\n".join(["## What the app needs", "", *lines, ""]))
            written.append("docs/PRODUCT.md")
        else:
            rules += ["What the app needs:", "", *lines, ""]
    _upsert(project / "AGENTS.md", "\n".join(rules))
    written.append("AGENTS.md")
    return written


def _needs_lines(needs: list[str], components: list[dict]) -> list[str]:
    """What the app needs (the planner's reading of the brief, said or implied),
    each with the approved components that serve it."""
    lines = ["Worked out from the brief in the create-project wizard, including what it only implies.",
             "Treat it as the first feature list: confirm, refine or drop items with the owner.", ""]
    for need in needs:
        serving = [c for c in components if need in lc.need_fit(c, [need])]
        tail = (": " + ", ".join(f"{c['name']} ({c['library_name']})" for c in serving)) if serving else ""
        lines.append(f"- {lc.NEEDS[need]}{tail}")
    return lines


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
