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

from api import library_catalog as lc

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
