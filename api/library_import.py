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
