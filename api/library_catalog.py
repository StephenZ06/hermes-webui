"""Library catalog for the project builder.

Each library lives in ``HERMES_HOME/libraries/<slug>/``: ``LIBRARY.md`` (front
matter: name, source, license, kind, frameworks, tailwind, install),
``components/<slug>.md`` (name, role, style, motion, platform, demo, files),
``previews/`` and an optional read-only ``source/`` copy. Tags come from fixed
lists so the wizard's matching stays predictable; anything else is dropped and
the entry is marked ``needs_details`` for the user to fix.
"""

from __future__ import annotations

import json
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
    suffixes = (".webp", ".png", ".jpg", ".gif") if suffix == ".webp" else (suffix,)
    for ext in suffixes:
        p = lib_dir / "previews" / f"{slug}{ext}"
        if p.is_file():
            return f"{lib_dir.name}/previews/{p.name}"
    return None


def _preview_status(lib_dir: Path) -> dict | None:
    try:
        data = json.loads((lib_dir / "previews" / "STATUS.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


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
        out.append({"slug": lib_dir.name, **lib, "components": comps, "preview_status": _preview_status(lib_dir)})
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


def _score(comp: dict, style: str, motion: str) -> int:
    score = 0
    if style in comp["style"]:
        score += 10 - comp["style"].index(style)  # primary style tag counts most
    if motion and comp["motion"] == motion:
        score += 3
    elif motion and comp["motion"] and abs(MOTIONS.index(comp["motion"]) - MOTIONS.index(motion)) == 1:
        score += 1
    return score


# What a brief has to talk about for a component to fit it. Each entry pairs
# words found in component names (and roles) with the brief words that call for
# them, so "a booking site with a login" reaches Calendar, Input OTP and
# Password Input, not only components in the chosen style.
_FIT = [
    ("dashboard", "Dashboard and stats", "dashboard analytic chart table status shell activity counter number sidebar",
     "dashboard admin analytic analytics metric metrics kpi kpis report reports reporting stats statistic insight insights monitor monitoring internal backoffice saas crm portal data"),
    ("auth", "Sign-in", "input otp password field form",
     "login log signin sign signup register registration account accounts auth authentication password verification verify 2fa otp onboarding checkout"),
    ("forms", "Forms", "input field form button error",
     "form forms contact subscribe newsletter enquiry enquiries inquiry quote survey application apply"),
    ("settings", "Settings", "checkbox switch toggle select radio slider",
     "settings setting preference preferences profile filter filters option options configure configuration"),
    ("ai", "AI features", "ai reasoning thinking stream streaming text-stream generation matrix orb voice search web-search placeholder",
     "ai assistant agent agents chatbot chat llm gpt copilot generate generative generation prompt prompts model models ml automation voice search"),
    ("pricing", "Pricing and plans", "pro get-pro pricing gradient badge",
     "pricing price prices plan plans subscription subscriptions premium upgrade paid billing tier tiers saas"),
    ("gallery", "Image gallery", "gallery art image hover-image parallax carousel showcase split marquee tilt halftone sketch",
     "portfolio gallery photo photos photography art artist artwork showcase product products image images visual creative studio agency design designer fashion brand"),
    ("help", "Help and FAQ", "faq accordion collapsible",
     "faq faqs question questions help support docs documentation knowledge guide"),
    ("docs", "Docs and code", "code block toc rail breadcrumb command pagination",
     "docs documentation developer developers api sdk blog article articles tutorial knowledge guide technical"),
    ("scheduling", "Scheduling", "calendar duration picker task list",
     "booking book appointment appointments schedule scheduling calendar event events reservation reservations task tasks todo planner productivity time timer"),
    ("notifications", "Notifications", "toast sonner notification bell alert banner",
     "notification notifications alert alerts message messages feedback reminder reminders inbox activity"),
    ("marketing", "Landing page", "hero showcase footer navigation menu menubar nav header scroll smooth text reveal headline",
     "landing homepage marketing startup launch campaign agency brand"),
    ("social", "Profiles and community", "emoji reaction like avatar session sessions family drawer",
     "social community profile profiles feed comment comments chat friend friends member members team share sharing"),
    ("theming", "Light and dark theme", "theme selector",
     "theme themes dark light customise customize customization personalise personalize"),
    ("celebration", "Success feedback", "confetti success check spark click",
     "celebrate celebration reward rewards game gamification achievement achievements success onboarding signup"),
    ("commerce", "Shop and products", "cart card stack tilt hover like",
     "shop store ecommerce commerce product products catalog catalogue retail marketplace cart checkout"),
    ("errors", "Error pages", "404 golden-gate",
     "error errors"),
    ("app", "App menus and dialogs", "tabs dropdown context menu sheet drawer dialog modal popover tooltip",
     "app apps tool tools editor workspace productivity settings"),
    ("uploads", "Uploads and files", "drag drop folder",
     "upload uploads file files drag kanban board organise organize"),
    ("loading", "Loading states", "loader loaders spinner skeleton progress shimmer",
     "loading upload uploads progress performance fast async"),
]
_FIT_STOP = set("the and for with that this from into your our are was were has have will can a an in of to on at by "
                "it its be as or is we us they them their want wants need needs well very more most app build make "
                "user users like also should would just using use new one all some page pages site website read get see "
                "pick show add let check fill able each every when then there what who how".split())


# Phrases a brief writes as two words that mean one thing.
_PHRASES = [(re.compile(r"\bone[\s-]*time\s+(?:pass)?codes?\b"), "otp"), (re.compile(r"\blog[\s-]*ins?\b"), "login"),
            (re.compile(r"\bsign[\s-]*ins?\b"), "signin"), (re.compile(r"\bsign[\s-]*ups?\b"), "signup"),
            (re.compile(r"\bdark\s+mode\b"), "dark")]


# How a folded phrase reads back to the user.
_PHRASE_LABELS = {"otp": "one-time code", "login": "log in", "signin": "sign in", "signup": "sign up"}


def word_forms(text: str) -> dict[str, str]:
    """Each folded word of ``text`` (see ``words``) and the form the text used."""
    text = str(text or "").lower()
    for pattern, repl in _PHRASES:
        text = pattern.sub(repl, text)
    out: dict[str, str] = {}
    for word in re.findall(r"[a-z0-9]+", text):
        if len(word) < 2 or word in _FIT_STOP:
            continue
        out.setdefault(word[:-1] if len(word) > 3 and word.endswith("s") else word, _PHRASE_LABELS.get(word, word))
    return out


def words(text: str) -> set[str]:
    """Lower-case words of a brief or description, plural ``s`` folded, filler dropped."""
    return set(word_forms(text))


_FIT_SETS = [(words(c), words(b)) for _, _, c, b in _FIT]
# What an app can need, for the planner to choose from: key -> label.
NEEDS = {key: label for key, label, _, _ in _FIT}
_NEED_WORDS = {key: words(c) for key, _, c, _ in _FIT}
_NEED_BRIEF_WORDS = {key: words(b) for key, _, _, b in _FIT}


def parse_needs(raw) -> list[str]:
    """Known need keys from a list (the planner's "needs"), in order, at most twelve."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        key = str(item or "").strip().lower()
        if key in NEEDS and key not in out:
            out.append(key)
    return out[:12]


# What every project of a template needs when the planner names nothing.
TEMPLATE_NEEDS = {"web": ["app", "forms", "notifications", "loading"],
                  "website": ["marketing", "forms", "help"],
                  "ios": ["app", "forms", "notifications", "loading"],
                  "android": ["app", "forms", "notifications", "loading"]}


def need_fit(comp: dict, needs: list[str]) -> list[str]:
    """The needs (keys) this component serves, from its name."""
    own = words(" ".join([str(comp.get("name") or ""), str(comp.get("slug") or "").replace("-", " ")]))
    return [n for n in needs if own & _NEED_WORDS.get(n, set())]


def need_brief_words(needs: list[str]) -> set[str]:
    """The words a brief would use for these needs (to match skills against)."""
    out: set[str] = set()
    for n in needs:
        out |= _NEED_BRIEF_WORDS.get(n, set())
    return out


def brief_fit(comp: dict, brief_words: set[str]) -> list[str]:
    """The brief's words that call for this component (its own name words count too).

    Only the name counts, not the role: every "forms" component is not a login form."""
    if not brief_words:
        return []
    own = words(" ".join([str(comp.get("name") or ""), str(comp.get("slug") or "").replace("-", " ")]))
    hits = set(own & brief_words)
    for comp_words, wanted in _FIT_SETS:
        if own & comp_words:
            hits |= wanted & brief_words
    return sorted(hits)


def match_components(libraries, *, platform, framework, tailwind, style, motion, brief: str = "",
                     needs: list[str] | None = None) -> dict:
    """Catalogued components that fit the stack, ranked by the brief and what
    the app needs, then style and motion.

    ``needs`` are keys of ``NEEDS``: what the planner judged the app needs,
    including what the brief only implies (a booking site needs sign-in). In
    each role the components the brief or a need calls for are recommended (up
    to three per library, best style match first); when nothing calls for any,
    the best style match per role is."""
    needs = parse_needs(needs or [])
    forms = word_forms(brief)
    brief_words = set(forms)
    by_role: dict[str, list[dict]] = {}
    for lib in libraries:
        if framework not in lib.get("frameworks", []):
            continue
        if lib.get("tailwind") and not tailwind:
            continue
        for comp in lib.get("components", []):
            if comp.get("needs_details") or platform not in comp.get("platform", []):
                continue
            fit = brief_fit(comp, brief_words)
            # The brief naming the component itself ("an FAQ", "OTP") counts most.
            named = words(" ".join([str(comp.get("name") or ""), str(comp.get("slug") or "").replace("-", " ")])) & brief_words
            served = need_fit(comp, needs)
            look = _score(comp, style, motion)
            item = dict(comp, library=lib["slug"], library_name=lib.get("name") or lib["slug"],
                        kind=lib.get("kind", ""), install=lib.get("install", ""), source=lib.get("source", ""),
                        license=lib.get("license", ""), fit=[forms[w] for w in fit[:4]],
                        needs=[NEEDS[n] for n in served],
                        score=look + 6 * min(3, len(fit)) + 8 * len(named) + 5 * min(2, len(served)),
                        recommended=False, pick=False)
            item["_look"] = look
            item["_served"] = served
            by_role.setdefault(comp["role"], []).append(item)
    called = lambda c: bool(c["fit"] or c["needs"])  # noqa: E731
    any_fit = any(called(c) for items in by_role.values() for c in items)
    out = {}
    for role in ROLES:
        items = sorted(by_role.get(role, []), key=lambda c: (-c["score"], c["library"], c["slug"]))
        if not items:
            continue
        if any_fit:  # the brief decides: up to three per role in each library that it calls for
            # The best of them is "pick" (ticked for the user); the rest are only starred.
            best = next((c for c in items if called(c)), None)
            if best:
                best["pick"] = True
            per_lib: dict[str, int] = {}
            for c in items:
                if called(c) and per_lib.get(c["library"], 0) < 3:
                    per_lib[c["library"]] = per_lib.get(c["library"], 0) + 1
                    c["recommended"] = True
        elif items[0]["score"] > 0:  # a brief that names nothing: the best style match
            items[0]["recommended"] = items[0]["pick"] = True
        out[role] = items
    if any_fit:
        # Every need gets its best component in each library (starred) and its
        # best overall is ticked, so "Scheduling" is not crowded out by three
        # sign-in fields in the same category.
        flat = sorted((c for items in out.values() for c in items), key=lambda c: (-c["score"], c["library"], c["slug"]))
        for need in needs:
            serving = [c for c in flat if need in c["_served"]]
            if serving:
                serving[0]["pick"] = True
            for lib in {c["library"] for c in serving}:
                next(c for c in serving if c["library"] == lib)["recommended"] = True
    for items in out.values():
        for c in items:
            c.pop("_look", None)
            c.pop("_served", None)
    return out


def delete_library(root: Path, slug: str) -> None:
    """Remove one library folder (entry, components, previews and source copy)."""
    import shutil

    clean = slugify(slug)
    if clean != str(slug).strip():
        raise ValueError("Unknown library.")
    target = safe_child(root, clean)
    if not target.is_dir() or target.is_symlink():
        raise FileNotFoundError("No such library.")
    shutil.rmtree(target)
