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
