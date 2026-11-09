# Project Builder Part 1: Skill and Library Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-profile library catalog (one entry per component, with Style, Motion, Role and Platform tags), filled from any link the user imports or from folders already on disk, shown in a new Libraries tab on the Skills page, plus the matching function the wizard (Part 2) will call.

**Architecture:** A new `api/library_catalog.py` owns the `HERMES_HOME/libraries/` tree (parse, validate, list, save, match). A new `api/library_import.py` fetches a link into a staging folder without running anything and asks the Architecture planner profile, through the existing `api/project_starter_agent` job machinery, to draft the entry. Routes in `api/routes.py` expose list, import, job, save and edit; `static/panels.js` gets the Skill/Library switch in Import, the review form and the Libraries tab.

**Tech Stack:** Python 3.11+ stdlib, PyYAML (already in the WebUI venv, 6.0.3), git CLI (present in the container at `/usr/bin/git`), vanilla JS, Playwright for browser tests.

Spec: `docs/superpowers/specs/2026-11-09-project-builder-design.md` (Part 1).
Later parts (wizard, previews, docs check) get their own plans once this lands, because they consume the interfaces defined here.

## Global Constraints

- No new WebUI dependencies; no build tools.
- Imports accept any link; nothing is blocked by licence or source. The licence is informational only.
- Imported code is never run during import: no install scripts, builds or package managers.
- Every catalog path must resolve inside `HERMES_HOME/libraries/`; anything else is refused.
- Fixed vocabularies, exactly:
  - Style: `minimal, elegant, playful, bold, technical, editorial`
  - Motion: `none, subtle, expressive`
  - Role: `hero, navigation, text-effect, background, cards, forms, transitions, loaders, icons`
  - Platform: `web, ios, android, react-native, flutter`
  - Framework: `react, vue, svelte, vanilla, swiftui, compose, react-native, flutter`
  - Kind: `npm, copy-paste, link`
- One model call per library import (planner profile `architecture`, no tools).
- Skill installs that the Hermes scan refuses show the reason and an **Install anyway** button, except when the installer says it never installs that skill even with `--force`.
- UI: 8px spacing grid, equal card sizes per row, optically centred icons, verified by measuring browser tests at 1440×900, 820×900 and 390×844. No hover title labels on buttons. Popups use the existing `.app-dialog` and PopupPresence motion.
- Tests run through `./scripts/test.sh`. Each test must fail before its implementation.
- After each task: commit ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. After the last task: redeploy, `graphify update .`, push to `fork` only.
- Never edit `CHANGELOG.md`. Never print secrets.

## File Structure

| File | Responsibility |
|---|---|
| `api/library_catalog.py` (new) | Vocabularies, front matter parse/validate, list, save, edit, path guard, `match_components` |
| `api/library_import.py` (new) | Fetch a link into staging (git shallow clone or page text), gather README/package.json/tree, draft prompt, `parse_draft`, start draft job, commit staged entry |
| `api/skill_import.py` (modify) | Accept any skill link; `force` flag; detect scan blocks |
| `api/routes.py` (modify) | `/api/libraries*` routes; skill import `force` and `blocked` status |
| `static/panels.js` (modify) | Import form Skill/Library switch, library review form, Libraries tab, Install anyway |
| `static/index.html` (modify) | Skills/Libraries tab bar in `#panelSkills` |
| `static/style.css` (modify) | Tab bar, library and component cards, tag chips, review form |
| `tests/test_library_catalog.py` (new) | Unit tests for catalog and matching |
| `tests/test_library_import.py` (new) | Unit tests for fetch, gather, parse_draft, commit |
| `tests/test_skills_add_menu.py` (modify) | Any-link and force behaviour |
| `tests/test_library_catalog_browser.py` (new) | Libraries tab, import switch, review form, spacing |
| `docs/UIUX-GUIDE.md`, `ARCHITECTURE.md`, `.agent/PROJECT_STATUS.md` (modify) | Record the catalog |

---

### Task 1: Catalog model (parse, validate, list, save)

**Files:**
- Create: `api/library_catalog.py`
- Test: `tests/test_library_catalog.py`

**Interfaces:**
- Produces:
  - `STYLES, MOTIONS, ROLES, PLATFORMS, FRAMEWORKS, KINDS: tuple[str, ...]`
  - `libraries_root(home: Path) -> Path` → `home / "libraries"`
  - `slugify(raw: str) -> str` (raises `ValueError` on empty or invalid)
  - `parse_front_matter(text: str) -> tuple[dict, str]`
  - `normalize_library(meta: dict) -> dict` (adds `needs_details: bool`)
  - `normalize_component(meta: dict) -> dict` (adds `needs_details: bool`)
  - `list_libraries(root: Path) -> list[dict]` each `{"slug", **library fields, "components": [ {"slug", **component fields, "preview": str|None, "loop": str|None} ]}`
  - `save_library(root: Path, slug: str, library: dict, components: list[dict]) -> Path`
  - `update_component(root: Path, slug: str, component_slug: str, fields: dict) -> dict`
  - `safe_child(root: Path, *parts: str) -> Path` (raises `ValueError` outside root)

- [ ] **Step 1: Write the failing tests**

```python
"""Library catalog: one folder per library under HERMES_HOME/libraries, one
file per component, with fixed style / motion / role / platform tags."""

import pytest

from api import library_catalog as lc


LIB = """---
name: Rare UI
source: https://github.com/swamimalode07/rare-ui
license: MIT
kind: copy-paste
frameworks: [react]
tailwind: true
install: ""
---
Notes about the library.
"""

SOFT = """---
name: Soft fade text
role: text-effect
style: [minimal, elegant]
motion: subtle
platform: [web]
demo: https://example.com/soft
files: [src/soft.tsx]
---
"""


def _write_lib(root, slug="rare-ui", lib=LIB, comps=(("soft-fade", SOFT),)):
    d = root / slug
    (d / "components").mkdir(parents=True)
    (d / "LIBRARY.md").write_text(lib)
    for name, text in comps:
        (d / "components" / f"{name}.md").write_text(text)
    return d


def test_front_matter_is_split_from_the_body():
    meta, body = lc.parse_front_matter(LIB)
    assert meta["name"] == "Rare UI" and meta["frameworks"] == ["react"]
    assert body.strip() == "Notes about the library."
    assert lc.parse_front_matter("no front matter") == ({}, "no front matter")


def test_a_complete_library_and_component_need_no_details(tmp_path):
    _write_lib(tmp_path)
    [lib] = lc.list_libraries(tmp_path)
    assert lib["slug"] == "rare-ui" and lib["kind"] == "copy-paste" and lib["needs_details"] is False
    [comp] = lib["components"]
    assert comp["slug"] == "soft-fade" and comp["style"] == ["minimal", "elegant"]
    assert comp["motion"] == "subtle" and comp["needs_details"] is False
    assert comp["preview"] is None


def test_unknown_tags_are_dropped_and_mark_the_entry_as_needing_details(tmp_path):
    bad = SOFT.replace("[minimal, elegant]", "[shiny]").replace("subtle", "wild")
    _write_lib(tmp_path, comps=(("soft-fade", bad),))
    [comp] = lc.list_libraries(tmp_path)[0]["components"]
    assert comp["style"] == [] and comp["motion"] == "" and comp["needs_details"] is True


def test_malformed_front_matter_lists_with_needs_details_instead_of_crashing(tmp_path):
    _write_lib(tmp_path, lib="---\nname: [unclosed\n---\n")
    [lib] = lc.list_libraries(tmp_path)
    assert lib["needs_details"] is True and lib["name"] == "rare-ui"


def test_preview_files_are_reported_when_present(tmp_path):
    d = _write_lib(tmp_path)
    (d / "previews").mkdir()
    (d / "previews" / "soft-fade.webp").write_bytes(b"RIFF")
    (d / "previews" / "soft-fade.loop.webp").write_bytes(b"RIFF")
    [comp] = lc.list_libraries(tmp_path)[0]["components"]
    assert comp["preview"] == "rare-ui/previews/soft-fade.webp"
    assert comp["loop"] == "rare-ui/previews/soft-fade.loop.webp"


def test_save_writes_a_library_that_lists_back_the_same(tmp_path):
    lc.save_library(tmp_path, "my-lib", {"name": "My lib", "source": "https://x.dev", "kind": "link",
                                         "frameworks": ["vanilla"], "tailwind": False, "license": "", "install": ""},
                    [{"name": "Glow card", "role": "cards", "style": ["bold"], "motion": "expressive", "platform": ["web"]}])
    [lib] = lc.list_libraries(tmp_path)
    assert lib["name"] == "My lib" and lib["components"][0]["slug"] == "glow-card"
    assert lib["components"][0]["role"] == "cards"


def test_update_component_changes_only_the_given_tags(tmp_path):
    _write_lib(tmp_path)
    out = lc.update_component(tmp_path, "rare-ui", "soft-fade", {"style": ["playful"], "motion": "expressive"})
    assert out["style"] == ["playful"] and out["motion"] == "expressive" and out["role"] == "text-effect"
    assert lc.list_libraries(tmp_path)[0]["components"][0]["style"] == ["playful"]


@pytest.mark.parametrize("parts", [("..", "x"), ("a/../../b",), ("/etc",), ("",)])
def test_paths_outside_the_catalog_are_refused(tmp_path, parts):
    with pytest.raises(ValueError):
        lc.safe_child(tmp_path, *parts)


def test_slugs_are_lowercase_dashed_and_checked():
    assert lc.slugify("  Rare UI! ") == "rare-ui"
    for bad in ("", "...", "-" * 3):
        with pytest.raises(ValueError):
            lc.slugify(bad)
```

- [ ] **Step 2: Run to verify they fail**

Run: `./scripts/test.sh tests/test_library_catalog.py -q`
Expected: FAIL with `ImportError: cannot import name 'library_catalog'`

- [ ] **Step 3: Implement**

```python
"""Library catalog for the project builder.

Each library lives in ``HERMES_HOME/libraries/<slug>/``: ``LIBRARY.md`` (front
matter: name, source, license, kind, frameworks, tailwind, install),
``components/<slug>.md`` (name, role, style, motion, platform, demo, files),
``previews/`` and an optional read-only ``source/`` copy. Tags come from fixed
lists so the wizard's matching stays predictable; anything else is dropped and
the entry is marked ``needs_details`` for the user to fix.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

STYLES = ("minimal", "elegant", "playful", "bold", "technical", "editorial")
MOTIONS = ("none", "subtle", "expressive")
ROLES = ("hero", "navigation", "text-effect", "background", "cards", "forms", "transitions", "loaders", "icons")
PLATFORMS = ("web", "ios", "android", "react-native", "flutter")
FRAMEWORKS = ("react", "vue", "svelte", "vanilla", "swiftui", "compose", "react-native", "flutter")
KINDS = ("npm", "copy-paste", "link")

_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)


def libraries_root(home: Path) -> Path:
    return Path(home) / "libraries"


def slugify(raw) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(raw or "").strip().lower()).strip("-")[:64].strip("-")
    if not slug:
        raise ValueError("Give it a name with letters or numbers.")
    return slug


def safe_child(root: Path, *parts: str) -> Path:
    base = Path(root).resolve()
    if not parts or any(not str(p) for p in parts):
        raise ValueError("Empty catalog path.")
    target = base.joinpath(*[str(p) for p in parts]).resolve()
    if target == base or base not in target.parents:
        raise ValueError("That path is outside the library catalog.")
    return target


def parse_front_matter(text: str) -> tuple[dict, str]:
    match = _FM_RE.match(text or "")
    if not match:
        return {}, text or ""
    meta = yaml.safe_load(match.group(1))  # yaml.YAMLError propagates to the caller
    return (meta if isinstance(meta, dict) else {}), text[match.end():]


def _str(value, limit=300) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def _pick_list(value, allowed) -> list[str]:
    items = value if isinstance(value, list) else ([value] if value else [])
    out = []
    for item in items:
        key = str(item).strip().lower()
        if key in allowed and key not in out:
            out.append(key)
    return out


def normalize_library(meta: dict) -> dict:
    kind = _str(meta.get("kind")).lower()
    lib = {
        "name": _str(meta.get("name"), 120),
        "source": _str(meta.get("source"), 500),
        "license": _str(meta.get("license"), 80),
        "kind": kind if kind in KINDS else "",
        "frameworks": _pick_list(meta.get("frameworks"), FRAMEWORKS),
        "tailwind": bool(meta.get("tailwind")),
        "install": _str(meta.get("install"), 300),
    }
    lib["needs_details"] = not (lib["name"] and lib["kind"] and lib["frameworks"]) or bool(meta.get("needs_details"))
    return lib


def normalize_component(meta: dict) -> dict:
    role = _str(meta.get("role")).lower()
    motion = _str(meta.get("motion")).lower()
    comp = {
        "name": _str(meta.get("name"), 120),
        "role": role if role in ROLES else "",
        "style": _pick_list(meta.get("style"), STYLES),
        "motion": motion if motion in MOTIONS else "",
        "platform": _pick_list(meta.get("platform"), PLATFORMS),
        "demo": _str(meta.get("demo"), 500),
        "files": [_str(f, 300) for f in (meta.get("files") or []) if isinstance(f, str)][:50],
    }
    comp["needs_details"] = not (comp["name"] and comp["role"] and comp["style"] and comp["motion"] and comp["platform"])
    return comp


def _read_meta(path: Path) -> tuple[dict, bool]:
    try:
        meta, _ = parse_front_matter(path.read_text(encoding="utf-8"))
        return meta, False
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}, True


def _preview(lib_dir: Path, slug: str, suffix: str) -> str | None:
    p = lib_dir / "previews" / f"{slug}{suffix}"
    return f"{lib_dir.name}/previews/{p.name}" if p.is_file() else None


def list_libraries(root: Path) -> list[dict]:
    root = Path(root)
    if not root.is_dir():
        return []
    out = []
    for lib_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        meta, broken = _read_meta(lib_dir / "LIBRARY.md")
        lib = normalize_library(meta)
        lib["name"] = lib["name"] or lib_dir.name
        lib["needs_details"] = lib["needs_details"] or broken
        comps = []
        comp_dir = lib_dir / "components"
        for f in sorted(comp_dir.glob("*.md")) if comp_dir.is_dir() else []:
            cmeta, cbroken = _read_meta(f)
            comp = normalize_component(cmeta)
            comp["name"] = comp["name"] or f.stem
            comp["needs_details"] = comp["needs_details"] or cbroken
            comp.update(slug=f.stem, preview=_preview(lib_dir, f.stem, ".webp"), loop=_preview(lib_dir, f.stem, ".loop.webp"))
            comps.append(comp)
        out.append({"slug": lib_dir.name, **lib, "components": comps})
    return out


def _dump(meta: dict, body: str = "") -> str:
    return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip() + "\n---\n" + (body or "")


def save_library(root: Path, slug: str, library: dict, components: list[dict]) -> Path:
    lib_dir = safe_child(root, slugify(slug))
    (lib_dir / "components").mkdir(parents=True, exist_ok=True)
    lib = normalize_library(library)
    (lib_dir / "LIBRARY.md").write_text(_dump({k: lib[k] for k in lib if k != "needs_details"}), encoding="utf-8")
    for comp_meta in components:
        comp = normalize_component(comp_meta)
        cslug = slugify(comp_meta.get("slug") or comp["name"])
        safe_child(lib_dir, "components", f"{cslug}.md").write_text(
            _dump({k: comp[k] for k in comp if k != "needs_details"}), encoding="utf-8")
    return lib_dir


def update_component(root: Path, slug: str, component_slug: str, fields: dict) -> dict:
    path = safe_child(root, slugify(slug), "components", f"{slugify(component_slug)}.md")
    if not path.is_file():
        raise FileNotFoundError("No such component.")
    meta, _ = _read_meta(path)
    allowed = {"name", "role", "style", "motion", "platform", "demo"}
    meta.update({k: v for k, v in (fields or {}).items() if k in allowed})
    comp = normalize_component(meta)
    path.write_text(_dump({k: comp[k] for k in comp if k != "needs_details"}), encoding="utf-8")
    return comp
```

- [ ] **Step 4: Run to verify they pass**

Run: `./scripts/test.sh tests/test_library_catalog.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add api/library_catalog.py tests/test_library_catalog.py
git commit -m "library catalog: per-component entries with fixed style, motion, role and platform tags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Matching for the wizard

**Files:**
- Modify: `api/library_catalog.py` (append)
- Test: `tests/test_library_catalog.py` (append)

**Interfaces:**
- Consumes: `list_libraries` output from Task 1.
- Produces: `match_components(libraries: list[dict], *, platform: str, framework: str, tailwind: bool, style: str, motion: str) -> dict[str, list[dict]]`. The keys are roles in `ROLES` order, and only roles with matches appear. Each item is the component dict plus `"library": slug`, `"library_name"`, `"kind"`, `"install"`, `"source"`, `"score": int` and `"recommended": bool`. The best item per role has `recommended=True`.

- [ ] **Step 1: Write the failing tests**

```python
def _lib(slug, frameworks, tailwind, comps, kind="npm"):
    return {"slug": slug, "name": slug, "kind": kind, "frameworks": frameworks, "tailwind": tailwind,
            "install": f"npm i {slug}", "source": f"https://x/{slug}", "needs_details": False,
            "components": [dict(slug=c[0], name=c[0], role=c[1], style=c[2], motion=c[3], platform=c[4],
                                needs_details=False, preview=None, loop=None) for c in comps]}


LIBS = [
    _lib("calm", ["react"], False, [("fade", "text-effect", ["minimal", "elegant"], "subtle", ["web"]),
                                     ("glitch", "text-effect", ["technical"], "expressive", ["web"])]),
    _lib("tw", ["react"], True, [("aurora", "background", ["minimal"], "subtle", ["web"])]),
    _lib("vue-kit", ["vue"], False, [("fade-vue", "text-effect", ["minimal"], "subtle", ["web"])]),
    _lib("mobile", ["react-native"], False, [("sheet", "transitions", ["minimal"], "subtle", ["react-native"])]),
]


def test_framework_platform_and_tailwind_are_hard_filters():
    out = lc.match_components(LIBS, platform="web", framework="react", tailwind=False, style="minimal", motion="subtle")
    names = [c["slug"] for items in out.values() for c in items]
    assert "fade-vue" not in names and "sheet" not in names and "aurora" not in names
    with_tw = lc.match_components(LIBS, platform="web", framework="react", tailwind=True, style="minimal", motion="subtle")
    assert [c["slug"] for c in with_tw["background"]] == ["aurora"]


def test_style_then_motion_ranks_and_only_the_top_per_role_is_recommended():
    out = lc.match_components(LIBS, platform="web", framework="react", tailwind=False, style="minimal", motion="subtle")
    assert [c["slug"] for c in out["text-effect"]] == ["fade", "glitch"]
    assert [c["recommended"] for c in out["text-effect"]] == [True, False]
    tech = lc.match_components(LIBS, platform="web", framework="react", tailwind=False, style="technical", motion="expressive")
    assert tech["text-effect"][0]["slug"] == "glitch"


def test_mobile_projects_only_see_their_platform():
    out = lc.match_components(LIBS, platform="react-native", framework="react-native", tailwind=False, style="minimal", motion="subtle")
    assert list(out) == ["transitions"] and out["transitions"][0]["slug"] == "sheet"


def test_untagged_components_are_never_suggested():
    libs = [_lib("raw", ["react"], False, [("x", "", [], "", [])])]
    libs[0]["components"][0]["needs_details"] = True
    assert lc.match_components(libs, platform="web", framework="react", tailwind=False, style="minimal", motion="subtle") == {}
```

- [ ] **Step 2: Run to verify they fail**

Run: `./scripts/test.sh tests/test_library_catalog.py -q -k "filters or ranks or mobile or untagged"`
Expected: FAIL with `AttributeError: module 'api.library_catalog' has no attribute 'match_components'`

- [ ] **Step 3: Implement (append to `api/library_catalog.py`)**

```python
def _score(comp: dict, style: str, motion: str) -> int:
    score = 0
    if style in comp["style"]:
        score += 10 - comp["style"].index(style)  # primary style tag counts most
    if motion and comp["motion"] == motion:
        score += 3
    elif motion and comp["motion"] and abs(MOTIONS.index(comp["motion"]) - MOTIONS.index(motion)) == 1:
        score += 1
    return score


def match_components(libraries, *, platform, framework, tailwind, style, motion) -> dict:
    by_role: dict[str, list[dict]] = {}
    for lib in libraries:
        if framework not in lib.get("frameworks", []):
            continue
        if lib.get("tailwind") and not tailwind:
            continue
        for comp in lib.get("components", []):
            if comp.get("needs_details") or platform not in comp.get("platform", []):
                continue
            item = dict(comp, library=lib["slug"], library_name=lib.get("name") or lib["slug"],
                        kind=lib.get("kind", ""), install=lib.get("install", ""), source=lib.get("source", ""),
                        score=_score(comp, style, motion), recommended=False)
            by_role.setdefault(comp["role"], []).append(item)
    out = {}
    for role in ROLES:
        items = sorted(by_role.get(role, []), key=lambda c: (-c["score"], c["library"], c["slug"]))
        if items:
            items[0]["recommended"] = items[0]["score"] > 0
            out[role] = items
    return out
```

- [ ] **Step 4: Run to verify they pass**

Run: `./scripts/test.sh tests/test_library_catalog.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add api/library_catalog.py tests/test_library_catalog.py
git commit -m "library catalog: match components by platform, framework and Tailwind, rank by style and motion

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Fetch a link into staging without running anything

**Files:**
- Create: `api/library_import.py`
- Test: `tests/test_library_import.py`

**Interfaces:**
- Consumes: `library_catalog.libraries_root`, `safe_child`.
- Produces:
  - `fetch_source(link: str, dest: Path) -> dict` returns `{"mode": "git"|"page", "link": str}`. Git mode leaves a shallow clone in `dest/source`; page mode writes `dest/page.txt`.
  - `gather(dest: Path) -> dict` returns `{"readme": str, "package_json": str, "tree": list[str], "page": str}`, each text capped (README 20k, package.json 8k, page 20k, tree 400 entries).
  - `FETCH_TIMEOUT_SECONDS = 120`

- [ ] **Step 1: Write the failing tests**

```python
"""Library import: any link is fetched into staging and only read."""

import subprocess

import pytest

from api import library_import as li


def _bare_repo(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "README.md").write_text("# Calm UI\nSoft React animations.")
    (work / "package.json").write_text('{"name":"calm-ui","peerDependencies":{"react":"^18"}}')
    (work / "src").mkdir()
    (work / "src" / "fade.tsx").write_text("export const Fade = () => null")
    # A postinstall script that must never run.
    (work / "install.sh").write_text("touch PWNED")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(cmd, cwd=work, check=True)
    return work


def test_a_git_link_is_shallow_cloned_and_gathered(tmp_path):
    repo = _bare_repo(tmp_path)
    dest = tmp_path / "stage"
    info = li.fetch_source(f"file://{repo}", dest)
    assert info["mode"] == "git"
    got = li.gather(dest)
    assert "Calm UI" in got["readme"] and "calm-ui" in got["package_json"]
    assert "src/fade.tsx" in got["tree"] and ".git" not in " ".join(got["tree"])
    assert not (dest / "source" / ".git").exists()  # history is dropped
    assert not list(tmp_path.rglob("PWNED"))


def test_a_non_git_link_becomes_page_text(tmp_path, monkeypatch):
    monkeypatch.setattr(li, "_is_git", lambda link: False)
    monkeypatch.setattr(li, "_fetch_page", lambda link: "<html><title>Docs</title><p>Bold cards</p></html>")
    dest = tmp_path / "stage"
    assert li.fetch_source("https://example.com/ui", dest)["mode"] == "page"
    assert "Bold cards" in li.gather(dest)["page"] and "<p>" not in li.gather(dest)["page"]


@pytest.mark.parametrize("link", ["", "   ", "--upload-pack=touch x", "-x"])
def test_empty_links_and_option_lookalikes_are_refused(tmp_path, link):
    with pytest.raises(ValueError):
        li.fetch_source(link, tmp_path / "stage")


def test_gather_caps_large_text(tmp_path):
    dest = tmp_path / "stage"
    (dest / "source").mkdir(parents=True)
    (dest / "source" / "README.md").write_text("x" * 50000)
    assert len(li.gather(dest)["readme"]) == 20000
```

- [ ] **Step 2: Run to verify they fail**

Run: `./scripts/test.sh tests/test_library_import.py -q`
Expected: FAIL with `ImportError: cannot import name 'library_import'`

- [ ] **Step 3: Implement**

```python
"""Bring a UI library into the catalog from any link.

The link is only read: a git remote is shallow-cloned with hooks, submodules and
the ``ext`` transport disabled and its history dropped; any other link is
fetched once as page text. Nothing is installed, built or executed. A single
planner turn then drafts the catalog entry for the user to review.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

FETCH_TIMEOUT_SECONDS = 120
_PAGE_LIMIT = 2_000_000
_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "true", "GIT_CONFIG_NOSYSTEM": "1"}
_GIT_SAFE = ["-c", "protocol.ext.allow=never", "-c", "core.hooksPath=/dev/null",
             "-c", "submodule.recurse=false", "-c", "core.symlinks=false"]


def _check_link(link) -> str:
    link = str(link or "").strip()
    if not link or link.startswith("-") or any(c in link for c in "\r\n\0"):
        raise ValueError("Paste a link to the library.")
    return link


def _git(*args, cwd=None):
    env = {**os.environ, **_GIT_ENV}
    return subprocess.run(["git", *_GIT_SAFE, *args], cwd=cwd, env=env, capture_output=True, text=True,
                          timeout=FETCH_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)


def _is_git(link: str) -> bool:
    try:
        return _git("ls-remote", "--heads", "--", link).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _fetch_page(link: str) -> str:
    req = urllib.request.Request(link, headers={"User-Agent": "hermes-webui-library-import"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - the user's own link
        return resp.read(_PAGE_LIMIT).decode("utf-8", "replace")


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def fetch_source(link, dest: Path) -> dict:
    link = _check_link(link)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if _is_git(link):
        target = dest / "source"
        proc = _git("clone", "--depth", "1", "--no-tags", "--single-branch", "--", link, str(target))
        if proc.returncode != 0:
            raise RuntimeError("The repository could not be downloaded: " + (proc.stderr or "").strip()[-300:])
        shutil.rmtree(target / ".git", ignore_errors=True)
        return {"mode": "git", "link": link}
    try:
        page = _fetch_page(link)
    except Exception as exc:
        raise RuntimeError(f"The link could not be opened: {exc}") from exc
    (dest / "page.txt").write_text(_strip_html(page), encoding="utf-8")
    return {"mode": "page", "link": link}


def _read(path: Path, limit: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def gather(dest: Path) -> dict:
    src = Path(dest) / "source"
    readme = next((p for p in sorted(src.glob("*")) if p.is_file() and p.name.lower().startswith("readme")), None) if src.is_dir() else None
    tree = []
    if src.is_dir():
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(src).as_posix()
            if p.is_file() and not any(part in {"node_modules", ".git"} for part in p.parts):
                tree.append(rel)
            if len(tree) >= 400:
                break
    return {
        "readme": _read(readme, 20000) if readme else "",
        "package_json": _read(src / "package.json", 8000) if src.is_dir() else "",
        "tree": tree,
        "page": _read(Path(dest) / "page.txt", 20000),
    }
```

- [ ] **Step 4: Run to verify they pass**

Run: `./scripts/test.sh tests/test_library_import.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add api/library_import.py tests/test_library_import.py
git commit -m "library import: fetch any link into staging without running it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Draft the entry with the planner and commit it

**Files:**
- Modify: `api/library_import.py` (append)
- Test: `tests/test_library_import.py` (append)

**Interfaces:**
- Consumes: `project_starter_agent._start_job`, `_run_ephemeral_turn`, `_planner_run`, `get_job`; `library_catalog.save_library`, `normalize_library`, `normalize_component`, `slugify`, `safe_child`, and the vocabularies.
- Produces:
  - `parse_draft(text: str) -> dict` returns `{"slug": str, "library": dict, "components": list[dict]}` (normalized; raises `ValueError` without JSON).
  - `start_import(link: str, root: Path) -> str` returns a job id. Job result: `{"staging": str, "mode": str, "draft": dict}`, or on a model failure `{"staging", "mode", "draft": {"slug", "library": {"source": link, "needs_details": True}, "components": []}, "draft_error": str}`.
  - `commit_import(root: Path, staging: str, slug: str, library: dict, components: list[dict]) -> Path`. This moves `staging/source` to `<slug>/source` when present, saves, and removes the staging folder.
  - `STAGING_DIR = ".staging"`

- [ ] **Step 1: Write the failing tests**

```python
DRAFT = """Here you go:
{"slug": "Calm UI", "library": {"name": "Calm UI", "license": "MIT", "kind": "npm",
 "frameworks": ["react", "angular"], "tailwind": false, "install": "npm i calm-ui"},
 "components": [{"name": "Fade", "role": "text-effect", "style": ["minimal"], "motion": "subtle",
   "platform": ["web"], "demo": "https://calm.dev/fade", "files": ["src/fade.tsx"]},
   {"name": "", "role": "nope"}]}"""


def test_parse_draft_normalizes_and_keeps_only_named_components():
    out = li.parse_draft(DRAFT)
    assert out["slug"] == "calm-ui"
    assert out["library"]["frameworks"] == ["react"]  # unknown framework dropped
    assert [c["name"] for c in out["components"]] == ["Fade"]
    with pytest.raises(ValueError):
        li.parse_draft("no json here")


def test_commit_moves_the_source_and_clears_staging(tmp_path):
    root = tmp_path / "libraries"
    stage = root / li.STAGING_DIR / "job1"
    (stage / "source").mkdir(parents=True)
    (stage / "source" / "README.md").write_text("hi")
    out = li.parse_draft(DRAFT)
    lib_dir = li.commit_import(root, "job1", out["slug"], {**out["library"], "source": "https://x"}, out["components"])
    assert (lib_dir / "source" / "README.md").read_text() == "hi"
    assert not stage.exists()
    from api import library_catalog as lc
    [lib] = lc.list_libraries(root)
    assert lib["slug"] == "calm-ui" and lib["components"][0]["slug"] == "fade"


def test_staging_names_cannot_escape(tmp_path):
    with pytest.raises(ValueError):
        li.commit_import(tmp_path, "../../etc", "x", {"name": "x"}, [])


def test_the_catalog_listing_skips_the_staging_folder(tmp_path):
    (tmp_path / li.STAGING_DIR / "job1").mkdir(parents=True)
    from api import library_catalog as lc
    assert lc.list_libraries(tmp_path) == []


def test_a_failed_draft_still_returns_an_editable_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(li, "fetch_source", lambda link, dest: (Path(dest).mkdir(parents=True, exist_ok=True), {"mode": "page", "link": link})[1])
    monkeypatch.setattr(li, "_draft_with_planner", lambda link, gathered: (_ for _ in ()).throw(RuntimeError("no model")))
    result = li._import_work("https://x.dev/ui", tmp_path, "job9")
    assert result["draft"]["library"]["source"] == "https://x.dev/ui"
    assert result["draft"]["library"]["needs_details"] is True and result["draft_error"] == "no model"
```

Add `from pathlib import Path` to the test imports.

- [ ] **Step 2: Run to verify they fail**

Run: `./scripts/test.sh tests/test_library_import.py -q`
Expected: FAIL with `AttributeError: module 'api.library_import' has no attribute 'parse_draft'`

- [ ] **Step 3: Implement (append to `api/library_import.py`)**

```python
from api import library_catalog as lc

STAGING_DIR = ".staging"
_DRAFT_TIMEOUT_SECONDS = 240

_DRAFT_PROMPT = """You are cataloguing a UI library for a project builder.
Do not use any tools. Reply with ONLY one JSON object:
{{"slug": "short-name", "library": {{"name": "...", "license": "SPDX id or empty",
  "kind": "npm|copy-paste|link", "frameworks": [{frameworks}], "tailwind": true|false,
  "install": "npm command for kind npm, else empty"}},
 "components": [{{"name": "...", "role": "{roles}", "style": [up to 2 of: {styles}],
   "motion": "{motions}", "platform": [{platforms}], "demo": "URL of its demo page or empty",
   "files": ["paths of its source files inside the repository"]}}]}}

List every distinct component or animation set (at most 60). Pick tags only
from the lists given; put the closest style first.

Link: {link}
README:
{readme}
package.json:
{package_json}
Files:
{tree}
Page text:
{page}
"""


def parse_draft(text: str) -> dict:
    match = re.search(r"\{.*\}", str(text or ""), re.S)
    if not match:
        raise ValueError("Hermes did not return a readable draft.")
    data = json.loads(match.group(0))
    lib = lc.normalize_library(data.get("library") or {})
    comps = []
    for raw in (data.get("components") or [])[:60]:
        if isinstance(raw, dict):
            comp = lc.normalize_component(raw)
            if comp["name"]:
                comps.append(comp)
    try:
        slug = lc.slugify(data.get("slug") or lib["name"])
    except ValueError:
        slug = ""
    return {"slug": slug, "library": lib, "components": comps}


def _draft_with_planner(link: str, gathered: dict) -> dict:
    from api.project_starter_agent import _planner_run, _run_ephemeral_turn
    prompt = _DRAFT_PROMPT.format(
        frameworks=", ".join(lc.FRAMEWORKS), roles="|".join(lc.ROLES), styles=", ".join(lc.STYLES),
        motions="|".join(lc.MOTIONS), platforms=", ".join(lc.PLATFORMS), link=link,
        readme=gathered["readme"], package_json=gathered["package_json"],
        tree="\n".join(gathered["tree"]), page=gathered["page"])
    return parse_draft(_run_ephemeral_turn(prompt, timeout=_DRAFT_TIMEOUT_SECONDS, **_planner_run()))


def _import_work(link: str, root: Path, job_key: str) -> dict:
    stage = lc.safe_child(root, STAGING_DIR, job_key)
    info = fetch_source(link, stage)
    try:
        draft = _draft_with_planner(link, gather(stage))
        draft["library"]["source"] = link
        error = ""
    except Exception as exc:  # the user fills the form by hand
        draft = {"slug": "", "library": {"source": link, "needs_details": True}, "components": []}
        error = str(exc) or "Hermes could not draft this library."
    out = {"staging": job_key, "mode": info["mode"], "draft": draft}
    if error:
        out["draft_error"] = error
    return out


def start_import(link: str, root: Path) -> str:
    import uuid
    from api.project_starter_agent import _start_job
    link = _check_link(link)
    key = uuid.uuid4().hex[:16]
    return _start_job("library-import", lambda: _import_work(link, Path(root), key))


def commit_import(root: Path, staging: str, slug: str, library: dict, components: list[dict]) -> Path:
    root = Path(root)
    stage = lc.safe_child(root, STAGING_DIR, lc.slugify(staging)) if staging else None
    if staging and stage.name != str(staging):
        raise ValueError("Unknown import.")
    lib_dir = lc.save_library(root, slug, library, components)
    if stage and (stage / "source").is_dir() and not (lib_dir / "source").exists():
        shutil.move(str(stage / "source"), str(lib_dir / "source"))
    if stage:
        shutil.rmtree(stage, ignore_errors=True)
    return lib_dir
```

Note: `list_libraries` already skips dot folders, so `.staging` never lists. `slugify("../../etc")` returns `etc`, and the `stage.name != staging` check refuses it.

- [ ] **Step 4: Run to verify they pass**

Run: `./scripts/test.sh tests/test_library_import.py tests/test_library_catalog.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add api/library_import.py tests/test_library_import.py
git commit -m "library import: one planner turn drafts the entry; review commits it into the catalog

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Skill import accepts any link and can install anyway

**Files:**
- Modify: `api/skill_import.py` (`skill_source_from_link`, `install_skill`)
- Modify: `api/routes.py:19344-19363` (`_route_post_api_skills_import`)
- Test: `tests/test_skills_add_menu.py`

**Interfaces:**
- Produces:
  - `skill_source_from_link(link) -> str`: GitHub links are converted exactly as today. Any other non-empty link that doesn't start with `-` is returned stripped.
  - `install_skill(source: str, category: str = "", force: bool = False) -> dict`: status is one of `installed | exists | blocked | hard_blocked | failed | timeout`. `blocked` and `hard_blocked` carry `"reason"`.
  - Route body accepts `"force": true`. The response for `blocked` is 409 with `{"status": "blocked", "reason", "can_force": true}`; for `hard_blocked` it's 409 with `can_force: false`.

- [ ] **Step 1: Update and add failing tests**

Replace `test_anything_but_a_github_skill_link_is_refused` with:

```python
@pytest.mark.parametrize("link", ["https://gitlab.com/o/r", "https://skills.dev/pdf/SKILL.md", "owner/repo/skills/pdf"])
def test_other_links_are_passed_to_the_installer_unchanged(link):
    assert skill_import.skill_source_from_link(f"  {link} ") == link


@pytest.mark.parametrize("link", ["", "   ", "--force", "-x", "a\nb"])
def test_empty_links_and_option_lookalikes_are_still_refused(link):
    with pytest.raises(ValueError):
        skill_import.skill_source_from_link(link)
```

Append:

```python
def test_a_scan_refusal_is_reported_as_blocked_and_force_adds_the_flag(monkeypatch, tmp_path):
    calls = []

    class Done:
        returncode = 1
        stdout = "Not installed: high-risk patterns found (network exfiltration).\nRe-run with --force to install anyway."
        stderr = ""

    monkeypatch.setattr(skill_import, "_gateway_restart_profile_context", lambda: (tmp_path, None))
    monkeypatch.setattr(skill_import, "_resolve_hermes_command", lambda: "/bin/hermes")
    monkeypatch.setattr(skill_import.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Done())
    out = skill_import.install_skill("o/r/s")
    assert out["status"] == "blocked" and "high-risk" in out["reason"]
    skill_import.install_skill("o/r/s", force=True)
    assert calls[-1][-1] == "--force"
    Done.stdout = "Hermes never installs unverified skills with high-risk findings, even with --force."
    assert skill_import.install_skill("o/r/s")["status"] == "hard_blocked"
```

- [ ] **Step 2: Run to verify they fail**

Run: `./scripts/test.sh tests/test_skills_add_menu.py -q`
Expected: FAIL: `ValueError` for gitlab links, and `TypeError: unexpected keyword argument 'force'`

- [ ] **Step 3: Implement**

At the very top of `skill_source_from_link`, add the newline/empty/dash guard. Where the function currently raises for a non-GitHub host or shape, return `link` (stripped) instead. Keep the GitHub conversions unchanged:

```python
def skill_source_from_link(link) -> str:
    link = str(link or "").strip()
    if not link or link.startswith("-") or any(c in link for c in "\r\n\0"):
        raise ValueError("Paste a link to the skill.")
    try:
        return _github_source(link)   # the current GitHub conversion body, moved verbatim into this helper
    except ValueError:
        return link
```

Move the current body (after its own stripping) into `def _github_source(link: str) -> str:` unchanged, so the existing GitHub test cases keep passing.

In `install_skill`, add the `force: bool = False` parameter and `if force: cmd.append("--force")` after the category args. Replace the `returncode != 0` branch with:

```python
    if proc.returncode != 0:
        if re.search(r"even with --force", output, re.I):
            return {"ok": False, "status": "hard_blocked", "output": tail, "reason": _reason(output)}
        if re.search(r"--force to install anyway|high-risk|blocked by scan", output, re.I):
            return {"ok": False, "status": "blocked", "output": tail, "reason": _reason(output)}
        return {"ok": False, "status": "failed", "output": tail}
```

with:

```python
def _reason(output: str) -> str:
    lines = [l.strip() for l in output.splitlines() if l.strip() and "--force" not in l]
    return " ".join(lines[-3:])[:600] or "The security scan refused this skill."
```

In the route, pass `force=bool(body.get("force"))` and add before the generic failure:

```python
    if result["status"] in ("blocked", "hard_blocked"):
        result["can_force"] = result["status"] == "blocked"
        result["error"] = result["reason"]
        return j(handler, result, 409)
```

- [ ] **Step 4: Run to verify they pass**

Run: `./scripts/test.sh tests/test_skills_add_menu.py -q`
Expected: all PASS. The existing `test_install_runs_the_hermes_cli_for_the_active_profile` still passes, because "Blocked by scan" with returncode 1 now maps to `blocked`. Update its last assertion to `assert skill_import.install_skill("a/b/c")["status"] == "blocked"`, and note in the commit message that this assertion changed.

- [ ] **Step 5: Commit**

```bash
git add api/skill_import.py api/routes.py tests/test_skills_add_menu.py
git commit -m "skills import: accept any link; report scan refusals so the user can install anyway

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Library routes

**Files:**
- Modify: `api/routes.py` (handlers next to `_route_post_api_skills_import`; GET table near line 16468, POST table near line 21083)
- Test: `tests/test_library_catalog_browser.py` (new; the routes are exercised through the live test server)

**Interfaces:**
- Consumes: Tasks 1, 3 and 4; `api.profiles.get_active_hermes_home()`; `project_starter_agent.get_job`.
- Produces (all JSON):
  - `GET /api/libraries` returns `{"libraries": list_libraries(...), "vocab": {"styles", "motions", "roles", "platforms", "frameworks", "kinds"}}`
  - `GET /api/libraries/preview?path=<slug>/previews/<file>` returns the image bytes (resolved with `safe_child`; only `.webp`, `.png`, `.jpg` and `.gif`)
  - `POST /api/libraries/import {link}` returns `{"job_id"}`
  - `GET /api/libraries/job?job_id=` returns the job dict
  - `POST /api/libraries/save {staging?, slug, library, components}` returns `{"ok": true, "slug"}`. It answers 409 when the slug exists and the body has no `"replace": true`.
  - `POST /api/libraries/component {library, component, fields}` returns `{"ok": true, "component"}`

- [ ] **Step 1: Write the failing test**

```python
"""Skills page Libraries tab: catalog listing, tag editing, import review."""

import json
import shutil

import pytest
import requests

from tests._pytest_port import BASE, TEST_STATE_DIR

LIBROOT = TEST_STATE_DIR / "libraries"


@pytest.fixture
def catalog():
    shutil.rmtree(LIBROOT, ignore_errors=True)
    d = LIBROOT / "calm-ui"
    (d / "components").mkdir(parents=True)
    (d / "LIBRARY.md").write_text("---\nname: Calm UI\nsource: https://github.com/x/calm\nlicense: MIT\nkind: npm\nframeworks: [react]\ntailwind: false\ninstall: npm i calm-ui\n---\n")
    (d / "components" / "fade.md").write_text("---\nname: Fade\nrole: text-effect\nstyle: [minimal]\nmotion: subtle\nplatform: [web]\n---\n")
    (d / "components" / "loose.md").write_text("---\nname: Loose\n---\n")
    yield LIBROOT
    shutil.rmtree(LIBROOT, ignore_errors=True)


def test_libraries_api_lists_vocab_and_edits_tags(catalog):
    data = requests.get(BASE + "/api/libraries", timeout=10).json()
    assert data["vocab"]["styles"][0] == "minimal"
    [lib] = data["libraries"]
    assert [c["slug"] for c in lib["components"]] == ["fade", "loose"]
    r = requests.post(BASE + "/api/libraries/component", json={"library": "calm-ui", "component": "loose",
                      "fields": {"role": "cards", "style": ["bold"], "motion": "expressive", "platform": ["web"]}}, timeout=10)
    assert r.status_code == 200 and r.json()["component"]["needs_details"] is False
    bad = requests.post(BASE + "/api/libraries/component", json={"library": "../x", "component": "a", "fields": {}}, timeout=10)
    assert bad.status_code in (400, 404)


def test_save_refuses_an_existing_slug_without_replace(catalog):
    body = {"slug": "calm-ui", "library": {"name": "Calm UI", "kind": "npm", "frameworks": ["react"]}, "components": []}
    assert requests.post(BASE + "/api/libraries/save", json=body, timeout=10).status_code == 409
    assert requests.post(BASE + "/api/libraries/save", json={**body, "replace": True}, timeout=10).status_code == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `./scripts/test.sh tests/test_library_catalog_browser.py -q -k "api or slug"`
Expected: FAIL with a 404 from `/api/libraries`

- [ ] **Step 3: Implement**

```python
# ── Libraries (project builder catalog) ──
def _libraries_root() -> Path:
    from api.library_catalog import libraries_root
    from api.profiles import get_active_hermes_home
    return libraries_root(get_active_hermes_home())


def _route_get_api_libraries(handler, parsed):
    from api import library_catalog as lc
    vocab = {"styles": lc.STYLES, "motions": lc.MOTIONS, "roles": lc.ROLES, "platforms": lc.PLATFORMS,
             "frameworks": lc.FRAMEWORKS, "kinds": lc.KINDS}
    return j(handler, {"libraries": lc.list_libraries(_libraries_root()), "vocab": {k: list(v) for k, v in vocab.items()}})


def _route_get_api_libraries_preview(handler, parsed):
    from api.library_catalog import safe_child
    rel = (parse_qs(parsed.query).get("path") or [""])[0]
    try:
        path = safe_child(_libraries_root(), *rel.split("/"))
    except ValueError as exc:
        return bad(handler, str(exc))
    types = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".gif": "image/gif"}
    if path.suffix.lower() not in types or "previews" not in path.parts or not path.is_file():
        return bad(handler, "No such preview.", 404)
    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", types[path.suffix.lower()])
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(data)


def _route_get_api_libraries_job(handler, parsed):
    from api.project_starter_agent import get_job
    job = get_job((parse_qs(parsed.query).get("job_id") or [""])[0])
    return j(handler, job) if job else bad(handler, "No such import.", 404)


def _route_post_api_libraries_import(handler, parsed, body, diag):
    from api.library_import import start_import
    body = body if isinstance(body, dict) else {}
    try:
        return j(handler, {"job_id": start_import(body.get("link"), _libraries_root())})
    except ValueError as exc:
        return bad(handler, str(exc))


def _route_post_api_libraries_save(handler, parsed, body, diag):
    from api.library_catalog import safe_child, slugify
    from api.library_import import commit_import
    body = body if isinstance(body, dict) else {}
    try:
        slug = slugify(body.get("slug") or (body.get("library") or {}).get("name"))
        if safe_child(_libraries_root(), slug).exists() and not body.get("replace"):
            return bad(handler, "A library with that name is already in the catalog.", 409)
        commit_import(_libraries_root(), str(body.get("staging") or ""), slug,
                      body.get("library") or {}, [c for c in body.get("components") or [] if isinstance(c, dict)])
    except ValueError as exc:
        return bad(handler, str(exc))
    return j(handler, {"ok": True, "slug": slug})


def _route_post_api_libraries_component(handler, parsed, body, diag):
    from api.library_catalog import update_component
    body = body if isinstance(body, dict) else {}
    try:
        comp = update_component(_libraries_root(), str(body.get("library") or ""), str(body.get("component") or ""),
                                body.get("fields") if isinstance(body.get("fields"), dict) else {})
    except ValueError as exc:
        return bad(handler, str(exc))
    except FileNotFoundError as exc:
        return bad(handler, str(exc), 404)
    return j(handler, {"ok": True, "component": comp})
```

Register `(Exact("/api/libraries"), _route_get_api_libraries)`, `(Exact("/api/libraries/preview"), _route_get_api_libraries_preview)` and `(Exact("/api/libraries/job"), _route_get_api_libraries_job)` beside the `/api/skills` GET entries. Register `/api/libraries/import`, `/api/libraries/save` and `/api/libraries/component` beside the `/api/skills/import` POST entry. Check that `parse_qs` is already imported in `api/routes.py` (`grep -n "parse_qs" api/routes.py | head -1`); if it isn't, add `from urllib.parse import parse_qs`.

- [ ] **Step 4: Run to verify it passes**

Run: `./scripts/test.sh tests/test_library_catalog_browser.py -q -k "api or slug"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes.py tests/test_library_catalog_browser.py
git commit -m "libraries API: list, preview, import job, save and tag edits

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Skills page UI (tabs, Libraries list, import switch, review form, Install anyway)

**Files:**
- Modify: `static/index.html` (`#panelSkills`, after `.panel-head`)
- Modify: `static/panels.js` (`loadSkills`/`renderSkills` area at about 6423; `_renderSkillImport` at about 6940)
- Modify: `static/style.css` (append)
- Test: `tests/test_library_catalog_browser.py` (append; reuse the `page` fixture pattern from `tests/test_skills_add_menu_browser.py`)

**Interfaces:**
- Consumes: the Task 6 routes; `_skillAddForm`, `_skillAddSwap`, `_closeSkillAddMenu`, `showToast` and `api` from `static/panels.js`.
- Produces (JS globals used by later parts):
  - `loadLibraries(): Promise<void>`
  - `_librariesData: object|null` (the last `/api/libraries` payload)
  - `switchSkillsTab(name: 'skills'|'libraries')`

- [ ] **Step 1: Write the failing browser tests**

```python
@pytest.fixture
def page(catalog):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove())")
            tab.evaluate("async () => { await switchPanel('skills'); }")
            tab.wait_for_timeout(400)
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def test_libraries_tab_lists_components_grouped_by_role_with_a_needs_details_badge(page):
    page.click("#skillsTabLibraries")
    page.wait_for_selector(".lib-card")
    assert page.locator(".lib-card .lib-name").all_inner_texts() == ["Calm UI"]
    roles = page.locator(".lib-role-head").all_inner_texts()
    assert roles[0].lower().startswith("text effect")
    assert page.locator(".lib-comp[data-comp=loose] .lib-badge-needs").count() == 1
    assert page.locator(".lib-comp[data-comp=fade] .lib-chip").all_inner_texts()[:2] == ["Minimal", "Subtle"]
    page.click("#skillsTabSkills")
    assert page.locator("#skillsList").is_visible() and not page.locator("#librariesList").is_visible()


def test_filters_narrow_components_by_style(page):
    page.click("#skillsTabLibraries")
    page.wait_for_selector(".lib-comp")
    page.select_option("#libFilterStyle", "bold")
    assert page.locator(".lib-comp:visible").count() == 0
    page.select_option("#libFilterStyle", "")
    assert page.locator(".lib-comp:visible").count() == 2


def test_editing_tags_clears_needs_details(page):
    page.click("#skillsTabLibraries")
    page.click(".lib-comp[data-comp=loose] [data-lib-edit]")
    page.wait_for_selector(".lib-tag-form")
    page.select_option(".lib-tag-form [name=role]", "cards")
    page.click(".lib-tag-form [data-style=bold]")
    page.select_option(".lib-tag-form [name=motion]", "expressive")
    page.click(".lib-tag-form [data-platform=web]")
    page.click(".lib-tag-form [type=submit]")
    page.wait_for_selector(".lib-comp[data-comp=loose] .lib-badge-needs", state="detached")


def test_import_has_a_skill_library_switch_and_library_review_saves(page):
    page.evaluate("openSkillAddMenu()")
    page.click("[data-choice=import]")
    page.wait_for_selector(".skill-add-kind")
    assert page.locator(".skill-add-kind button").all_inner_texts() == ["Skill", "Library"]
    # Review form directly from a draft (the planner is not available in tests).
    page.evaluate("""() => _renderLibraryReview(_skillAddOverlay, {staging: '', mode: 'page',
        draft: {slug: 'glow', library: {name: 'Glow', source: 'https://glow.dev', kind: 'link', frameworks: ['vanilla']},
                components: [{name: 'Glow card', role: 'cards', style: ['bold'], motion: 'expressive', platform: ['web']}]}})""")
    page.wait_for_selector(".lib-review")
    page.click(".lib-review [type=submit]")
    page.wait_for_selector(".skill-add-overlay", state="detached")
    page.click("#skillsTabLibraries")
    page.wait_for_selector(".lib-card[data-lib=glow]")


@pytest.mark.parametrize("width", [1440, 820, 390])
def test_component_cards_share_one_size_and_sit_on_the_8px_grid(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.click("#skillsTabLibraries")
    page.wait_for_selector(".lib-comp")
    boxes = page.evaluate("() => [...document.querySelectorAll('.lib-comp')].map(e => {const r = e.getBoundingClientRect(); return [r.width, r.height, r.left]})")
    assert len({round(b[0]) for b in boxes}) == 1 and len({round(b[1]) for b in boxes}) == 1
    gap = page.evaluate("() => { const [a, b] = document.querySelectorAll('.lib-comp'); const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(); return rb.top > ra.top + 1 ? rb.top - ra.bottom : rb.left - ra.right; }")
    assert gap == 8
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
```

- [ ] **Step 2: Run to verify they fail**

Run: `./scripts/test.sh tests/test_library_catalog_browser.py -q`
Expected: FAIL with a timeout waiting for `#skillsTabLibraries`

- [ ] **Step 3: Implement**

`static/index.html`, inside `#panelSkills` directly after the `.panel-head` div:

```html
      <div class="skills-tabs" role="tablist" aria-label="Skills and libraries">
        <button type="button" role="tab" id="skillsTabSkills" class="skills-tab is-active" aria-selected="true" onclick="switchSkillsTab('skills')">Skills</button>
        <button type="button" role="tab" id="skillsTabLibraries" class="skills-tab" aria-selected="false" onclick="switchSkillsTab('libraries')">Libraries</button>
      </div>
```

After `#skillsList`:

```html
      <div class="libraries-pane" id="librariesPane" hidden>
        <div class="lib-filters">
          <select id="libFilterStyle" aria-label="Style" onchange="renderLibraries()"><option value="">Any style</option></select>
          <select id="libFilterMotion" aria-label="Motion" onchange="renderLibraries()"><option value="">Any motion</option></select>
          <select id="libFilterPlatform" aria-label="Platform" onchange="renderLibraries()"><option value="">Any platform</option></select>
        </div>
        <div class="skills-list" id="librariesList"></div>
      </div>
```

`static/panels.js`, a new block placed after `renderSkills`:

```js
// ── Libraries tab (project builder catalog) ──
let _librariesData = null;
let _skillsTab = 'skills';
const _libLabel = (s) => String(s || '').replace(/-/g, ' ').replace(/^./, c => c.toUpperCase());

function switchSkillsTab(name) {
  _skillsTab = name === 'libraries' ? 'libraries' : 'skills';
  const libs = _skillsTab === 'libraries';
  $('skillsTabSkills').classList.toggle('is-active', !libs);
  $('skillsTabSkills').setAttribute('aria-selected', String(!libs));
  $('skillsTabLibraries').classList.toggle('is-active', libs);
  $('skillsTabLibraries').setAttribute('aria-selected', String(libs));
  $('skillsList').hidden = libs;
  document.querySelector('#panelSkills .skills-search').hidden = libs;
  $('librariesPane').hidden = !libs;
  if (libs) loadLibraries();
}

async function loadLibraries(force = false) {
  const box = $('librariesList');
  if (_librariesData && !force) { renderLibraries(); return; }
  _panelLoading(box);
  try {
    _librariesData = await api('/api/libraries');
    const v = _librariesData.vocab;
    [['libFilterStyle', v.styles], ['libFilterMotion', v.motions], ['libFilterPlatform', v.platforms]].forEach(([id, list]) => {
      const sel = $(id), keep = sel.value, first = sel.options[0].outerHTML;
      sel.innerHTML = first + list.map(x => `<option value="${esc(x)}">${esc(_libLabel(x))}</option>`).join('');
      sel.value = keep;
    });
    renderLibraries();
  } catch (e) { box.innerHTML = `<div class="lib-error">Error: ${esc(e.message)}</div>`; }
}

function _libCompHtml(lib, c) {
  const chips = [...c.style, c.motion, ...c.platform].filter(Boolean).map(t => `<span class="lib-chip">${esc(_libLabel(t))}</span>`).join('');
  const img = c.preview ? `<img src="api/libraries/preview?path=${encodeURIComponent(c.preview)}" alt="" loading="lazy" decoding="async">` : `<span class="lib-thumb-empty" aria-hidden="true">${esc((c.name || '?').slice(0, 1))}</span>`;
  return `<div class="lib-comp" data-lib="${esc(lib.slug)}" data-comp="${esc(c.slug)}">
    <div class="lib-thumb">${img}</div>
    <div class="lib-comp-text"><strong>${esc(c.name)}</strong>${c.needs_details ? '<span class="lib-badge-needs">Needs details</span>' : ''}<div class="lib-chips">${chips}</div></div>
    <button type="button" class="lib-edit" data-lib-edit aria-label="Edit tags for ${esc(c.name)}"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg></button>
  </div>`;
}

function renderLibraries() {
  const box = $('librariesList');
  if (!_librariesData) return;
  const fs = $('libFilterStyle').value, fm = $('libFilterMotion').value, fp = $('libFilterPlatform').value;
  const roles = _librariesData.vocab.roles;
  const libs = _librariesData.libraries;
  if (!libs.length) { box.innerHTML = '<div class="lib-empty">No libraries yet. Use + → Import and choose Library.</div>'; return; }
  box.innerHTML = libs.map(lib => {
    const comps = lib.components.filter(c => (!fs || c.style.includes(fs)) && (!fm || c.motion === fm) && (!fp || c.platform.includes(fp)));
    const groups = [...roles, ''].map(role => {
      const list = comps.filter(c => (c.role || '') === role);
      if (!list.length) return '';
      return `<div class="lib-role-head">${esc(role ? _libLabel(role) : 'Untagged')}</div><div class="lib-grid">${list.map(c => _libCompHtml(lib, c)).join('')}</div>`;
    }).join('');
    const meta = [lib.kind && _libLabel(lib.kind), ...lib.frameworks.map(_libLabel), lib.tailwind && 'Tailwind', lib.license].filter(Boolean).join(' · ');
    return `<section class="lib-card" data-lib="${esc(lib.slug)}"><header class="lib-head"><span class="lib-name">${esc(lib.name)}</span>${lib.needs_details ? '<span class="lib-badge-needs">Needs details</span>' : ''}<small class="lib-meta">${esc(meta)}</small></header>${groups}</section>`;
  }).join('');
  box.querySelectorAll('[data-lib-edit]').forEach(btn => btn.onclick = () => {
    const el = btn.closest('.lib-comp');
    const lib = libs.find(l => l.slug === el.dataset.lib);
    _openLibraryTagForm(lib, lib.components.find(c => c.slug === el.dataset.comp));
  });
}

function _libTagFields(v, c, prefix = '') {
  const pick = (name, list, value) => `<select name="${prefix}${name}">${['', ...list].map(x => `<option value="${esc(x)}"${x === value ? ' selected' : ''}>${x ? esc(_libLabel(x)) : 'Choose…'}</option>`).join('')}</select>`;
  const toggles = (attr, list, chosen) => `<div class="lib-toggles">${list.map(x => `<button type="button" class="lib-toggle${chosen.includes(x) ? ' is-on' : ''}" data-${attr}="${esc(x)}" aria-pressed="${chosen.includes(x)}">${esc(_libLabel(x))}</button>`).join('')}</div>`;
  return `<label class="skill-add-field"><span>Role</span>${pick('role', v.roles, c.role)}</label>
    <div class="skill-add-field"><span>Style</span>${toggles('style', v.styles, c.style)}</div>
    <label class="skill-add-field"><span>Motion</span>${pick('motion', v.motions, c.motion)}</label>
    <div class="skill-add-field"><span>Platform</span>${toggles('platform', v.platforms, c.platform)}</div>`;
}

function _readLibTags(root, prefix = '') {
  const on = (attr) => [...root.querySelectorAll(`.lib-toggle.is-on[data-${attr}]`)].map(b => b.dataset[attr]);
  return {role: root.querySelector(`[name=${prefix}role]`).value, style: on('style'), motion: root.querySelector(`[name=${prefix}motion]`).value, platform: on('platform')};
}

function _wireLibToggles(root) {
  root.querySelectorAll('.lib-toggle').forEach(b => b.onclick = () => { const on = !b.classList.contains('is-on'); b.classList.toggle('is-on', on); b.setAttribute('aria-pressed', String(on)); });
}

async function _openLibraryTagForm(lib, comp) {
  await openSkillAddMenu();
  const overlay = _skillAddOverlay;
  const form = _skillAddForm(overlay, comp.name, `<div class="lib-tag-form">${_libTagFields(_librariesData.vocab, comp)}</div>`, 'Save', async (f, status) => {
    try {
      await api('/api/libraries/component', {method: 'POST', body: JSON.stringify({library: lib.slug, component: comp.slug, fields: _readLibTags(f)}), retries: 0});
      _closeSkillAddMenu();
      await loadLibraries(true);
    } catch (err) { status.classList.add('is-error'); status.textContent = (err && err.message) || 'Could not save.'; }
  });
  form.classList.add('lib-tag-form');
  _wireLibToggles(form);
}
```

Replace `_renderSkillImport` so that it shows the Skill/Library switch, handles `blocked` with Install anyway, and starts library imports:

```js
function _renderSkillImport(overlay, kind = 'skill') {
  const isLib = kind === 'library';
  const form = _skillAddForm(overlay, isLib ? 'Import library' : 'Import skill', `
    <div class="skill-add-kind" role="radiogroup" aria-label="What to import"><button type="button" role="radio" data-kind="skill" aria-checked="${!isLib}" class="${isLib ? '' : 'is-on'}">Skill</button><button type="button" role="radio" data-kind="library" aria-checked="${isLib}" class="${isLib ? 'is-on' : ''}">Library</button></div>
    <label class="skill-add-field"><span>Link</span><input type="url" name="url" required placeholder="${isLib ? 'https://github.com/owner/ui-library' : 'https://github.com/owner/repo/tree/main/skills/name'}" autocomplete="off" spellcheck="false"></label>
    ${isLib ? '' : `<label class="skill-add-field"><span>Keep it in</span>${_skillCategorySelect('skillImportCategory', '')}</label>`}
    <p class="skill-add-hint">${isLib ? 'Hermes downloads it without running anything, then drafts tags for each component for you to check.' : "Link to the skill's folder or its SKILL.md. Hermes downloads it, scans it, then installs it for this profile."}</p>`,
  isLib ? 'Import' : 'Install', async (f, status) => isLib ? _importLibrary(overlay, f, status) : _installSkillFrom(f, status, false));
  form.querySelectorAll('.skill-add-kind button').forEach(b => b.onclick = () => { if (b.dataset.kind !== kind && !overlay._busy) _renderSkillImport(overlay, b.dataset.kind); });
}

async function _installSkillFrom(form, status, force) {
  const before = new Set((_skillsData || []).map(s => s.name));
  status.textContent = 'Installing…'; status.className = 'skill-add-status is-busy';
  try {
    await api('/api/skills/import', {method: 'POST', body: JSON.stringify({url: form.url.value, category: form.querySelector('select').value, force}), timeoutMs: 260000, retries: 0});
  } catch (err) {
    status.className = 'skill-add-status is-error';
    const data = err && err.data || {};
    status.textContent = (err && err.message) || 'The install failed.';
    if (data.status === 'blocked' && data.can_force) {
      const btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'app-dialog-btn skill-add-force'; btn.textContent = 'Install anyway';
      btn.onclick = () => _installSkillFrom(form, status, true);
      status.append(' ', btn);
    }
    return;
  }
  status.className = 'skill-add-status';
  showToast('Skill imported');
  _closeSkillAddMenu();
  await _afterSkillAdded(null);
  const added = (_skillsData || []).find(s => !before.has(s.name));
  if (added) await _afterSkillAdded(added.name);
}

async function _importLibrary(overlay, form, status) {
  status.textContent = 'Downloading and drafting…'; status.className = 'skill-add-status is-busy';
  try {
    const {job_id} = await api('/api/libraries/import', {method: 'POST', body: JSON.stringify({link: form.url.value}), retries: 0});
    let job;
    do { await new Promise(r => setTimeout(r, 2000)); job = await api('/api/libraries/job?job_id=' + encodeURIComponent(job_id)); } while (job.status === 'running' && overlay.isConnected);
    if (!overlay.isConnected) return;
    if (job.status !== 'done') throw new Error(job.error || 'The import failed.');
    _renderLibraryReview(overlay, job.result);
  } catch (err) { status.className = 'skill-add-status is-error'; status.textContent = (err && err.message) || 'The import failed.'; }
}

async function _renderLibraryReview(overlay, result) {
  if (!_librariesData) _librariesData = await api('/api/libraries');
  const v = _librariesData.vocab, d = result.draft, lib = d.library || {};
  const pick = (name, list, value) => `<select name="${name}">${['', ...list].map(x => `<option value="${esc(x)}"${x === value ? ' selected' : ''}>${x ? esc(_libLabel(x)) : 'Choose…'}</option>`).join('')}</select>`;
  const comps = (d.components || []).map((c, i) => `<fieldset class="lib-review-comp" data-i="${i}"><legend><input name="c${i}name" value="${esc(c.name)}" aria-label="Component name"></legend>${_libTagFields(v, {style: [], platform: [], ...c}, 'c' + i)}</fieldset>`).join('');
  const form = _skillAddForm(overlay, 'Check the draft', `<div class="lib-review">
    ${result.draft_error ? `<p class="skill-add-hint is-warn">Hermes could not draft this one (${esc(result.draft_error)}). Fill it in below.</p>` : ''}
    <label class="skill-add-field"><span>Name</span><input name="name" required value="${esc(lib.name || '')}"></label>
    <label class="skill-add-field"><span>Kind</span>${pick('kind', v.kinds, lib.kind)}</label>
    <div class="skill-add-field"><span>Frameworks</span><div class="lib-toggles">${v.frameworks.map(x => `<button type="button" class="lib-toggle${(lib.frameworks || []).includes(x) ? ' is-on' : ''}" data-framework="${esc(x)}" aria-pressed="${(lib.frameworks || []).includes(x)}">${esc(_libLabel(x))}</button>`).join('')}</div></div>
    <label class="skill-add-check"><input type="checkbox" name="tailwind"${lib.tailwind ? ' checked' : ''}> Needs Tailwind</label>
    <label class="skill-add-field"><span>Install command <em>(npm only)</em></span><input name="install" value="${esc(lib.install || '')}"></label>
    <p class="skill-add-hint">Licence: ${esc(lib.license || 'not stated')} · ${esc(lib.source || '')}</p>
    ${comps || '<p class="skill-add-hint">No components found. Save it and add tags later.</p>'}</div>`, 'Save to catalog', async (f, status) => {
    const components = [...f.querySelectorAll('.lib-review-comp')].map(fs => ({name: fs.querySelector(`[name=c${fs.dataset.i}name]`).value, ...(d.components[fs.dataset.i] || {}), ..._readLibTags(fs, 'c' + fs.dataset.i)}));
    components.forEach((c, i) => { c.name = f.querySelector(`[name=c${i}name]`).value; });
    const library = {...lib, name: f.name.value, kind: f.kind.value, tailwind: f.tailwind.checked, install: f.install.value,
      frameworks: [...f.querySelectorAll('.lib-toggle.is-on[data-framework]')].map(b => b.dataset.framework)};
    try {
      await api('/api/libraries/save', {method: 'POST', body: JSON.stringify({staging: result.staging, slug: d.slug || library.name, library, components}), retries: 0});
      showToast('Library added');
      _closeSkillAddMenu();
      await loadLibraries(true);
    } catch (err) { status.classList.add('is-error'); status.textContent = (err && err.message) || 'Could not save.'; }
  });
  _wireLibToggles(form);
}
```

Before relying on `err.data`, check how `api()` in `static/ui.js` exposes the JSON body of an error (`grep -n "function api" static/*.js`). If it uses a different property (for example `err.body` or `err.payload`), use that name in `_installSkillFrom`. If it doesn't keep the body at all, add `error.data = parsedBody` at the place it builds the thrown `Error`, in the same commit.

`static/style.css` (append):

```css
/* ── Skills page: Skills / Libraries tabs and the library catalog ── */
.skills-tabs{display:flex;gap:8px;padding:0 16px 8px;}
.skills-tab{flex:1;height:32px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--muted);font:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:background .16s ease,color .16s ease,border-color .16s ease;}
.skills-tab:hover{color:var(--text);border-color:var(--accent-border,var(--border));}
.skills-tab.is-active{background:var(--accent-bg,var(--hover));color:var(--text);border-color:var(--accent,var(--border));}
.lib-filters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0 16px 8px;}
.lib-filters select{height:32px;min-width:0;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--text);font:inherit;font-size:12px;padding:0 8px;}
.lib-card{padding:8px 16px 16px;}
.lib-head{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;padding:8px 0;}
.lib-name{font-weight:700;font-size:13px;}
.lib-meta{color:var(--muted);font-size:11px;}
.lib-role-head{font-size:11px;font-weight:600;letter-spacing:.02em;color:var(--muted);text-transform:uppercase;padding:8px 0;}
.lib-grid{display:grid;grid-template-columns:1fr;gap:8px;}
.lib-comp{display:grid;grid-template-columns:56px minmax(0,1fr) 32px;align-items:center;gap:8px;height:72px;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--surface);box-sizing:border-box;}
.lib-thumb{width:56px;height:56px;border-radius:8px;overflow:hidden;background:var(--hover);display:grid;place-items:center;}
.lib-thumb img{width:100%;height:100%;object-fit:cover;display:block;}
.lib-thumb-empty{font-weight:700;color:var(--muted);}
.lib-comp-text{min-width:0;display:flex;flex-direction:column;gap:4px;}
.lib-comp-text strong{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.lib-chips{display:flex;gap:4px;overflow:hidden;}
.lib-chip{font-size:10px;line-height:16px;padding:0 6px;border-radius:8px;background:var(--hover);color:var(--muted);white-space:nowrap;}
.lib-badge-needs{font-size:10px;line-height:16px;padding:0 6px;border-radius:8px;background:color-mix(in srgb,var(--warning,#d97706) 16%,transparent);color:var(--warning,#d97706);align-self:flex-start;}
.lib-edit{width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:8px;background:transparent;color:var(--muted);cursor:pointer;}
.lib-edit:hover{background:var(--hover);color:var(--text);}
.lib-empty,.lib-error{padding:16px;font-size:12px;color:var(--muted);}
.skill-add-kind{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;}
.skill-add-kind button,.lib-toggle{height:32px;border:1px solid var(--border);border-radius:8px;background:transparent;color:var(--muted);font:inherit;font-size:12px;cursor:pointer;transition:background .16s ease,color .16s ease,border-color .16s ease;}
.skill-add-kind button.is-on,.lib-toggle.is-on{background:var(--accent-bg,var(--hover));color:var(--text);border-color:var(--accent,var(--border));}
.lib-toggles{display:flex;flex-wrap:wrap;gap:8px;}
.lib-toggle{padding:0 12px;}
.lib-review{display:flex;flex-direction:column;gap:8px;max-height:min(60vh,560px);overflow:auto;}
.lib-review-comp{border:1px solid var(--border);border-radius:8px;padding:8px 16px 16px;display:flex;flex-direction:column;gap:8px;}
.lib-review-comp legend input{font:inherit;font-weight:600;border:0;background:transparent;color:var(--text);padding:0 4px;}
.skill-add-force{margin-left:8px;}
```

Before writing the CSS, read the nearby skills panel rules (`grep -n "\.skills-search\|\.skill-add-field\|--accent-bg\|--surface" static/style.css | head`). Use the token names that actually exist (for example the theme's accent and surface variables) instead of these guessed fallbacks, so the cards follow every theme including Zeus 2.

- [ ] **Step 4: Run to verify they pass**

Run: `./scripts/test.sh tests/test_library_catalog_browser.py tests/test_skills_add_menu_browser.py tests/test_popup_motion_round_browser.py -q`
Expected: all PASS. If the gap assertion is off by a sub-pixel amount, fix the CSS rather than loosening the test.

- [ ] **Step 5: Look at it.** Run the isolated server on :8796 with scratch `HERMES_HOME` (see `AGENTS.md`), seed a library, and take screenshots of the Libraries tab, the tag form and the review form at 1440, 820 and 390 widths, in the default theme and Zeus 2. Fix anything misaligned before committing.

- [ ] **Step 6: Commit**

```bash
git add static/index.html static/panels.js static/style.css tests/test_library_catalog_browser.py
git commit -m "skills page: Libraries tab, tag editing, library import review, install anyway

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Docs, broader verification, ship

**Files:**
- Modify: `ARCHITECTURE.md` (module list: `api/library_catalog.py`, `api/library_import.py`)
- Modify: `docs/UIUX-GUIDE.md` (Skills page: tabs, library cards, 8px grid)
- Modify: `.agent/PROJECT_STATUS.md` (new dated entry: Part 1 shipped, next is Part 2)

- [ ] **Step 1: Write the docs.** Use short factual entries, and say where the catalog lives (`HERMES_HOME/libraries/`) and that imports never run code.

- [ ] **Step 2: Run the neighbouring suites**

Run: `./scripts/test.sh tests/test_library_catalog.py tests/test_library_import.py tests/test_library_catalog_browser.py tests/test_skills_add_menu.py tests/test_skills_add_menu_browser.py tests/test_skills_security_scan.py tests/test_issue1880_profile_scoped_skills.py tests/test_popup_motion_round_browser.py tests/test_project_starter.py -q`
Expected: all PASS. Report any failure with its output, and compare against `HEAD~8` before calling it pre-existing.

- [ ] **Step 3: Commit, deploy, graph, push**

```bash
git add ARCHITECTURE.md docs/UIUX-GUIDE.md .agent/PROJECT_STATUS.md
git commit -m "docs: library catalog (project builder part 1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Redeploy with the live build and compose sequence (`git archive HEAD | docker build …`, then the three-file compose `build -q` and `up -d --no-deps hermes-webui`, run with `setsid nohup`). Check `/sw.js` returns 200 and `/api/libraries` returns JSON in the container. Then:

```bash
graphify update .
```

```bash
git push fork master
```
