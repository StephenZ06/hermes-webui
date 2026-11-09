"""Skills page: add a category, and import a skill from a GitHub link.

Importing runs the agent's own installer (``hermes skills install``) for the
active profile, so the skill goes through the same fetch, quarantine and
security scan as a CLI install. Nothing here fetches or writes skill files
itself.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from api.gateway_restart import _gateway_restart_profile_context, _resolve_hermes_command

CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
_GITHUB_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
INSTALL_TIMEOUT_SECONDS = 240


def normalize_category(raw) -> str:
    """Lower-case slug for a category folder name; '' when empty, ValueError when unusable."""
    name = re.sub(r"\s+", "-", str(raw or "").strip().lower())
    if not name:
        return ""
    if not CATEGORY_RE.fullmatch(name):
        raise ValueError("Use letters, numbers, - or _ for the category (up to 48 characters).")
    return name


def skill_source_from_link(link) -> str:
    """Turn a pasted GitHub link into what ``hermes skills install`` accepts.

    - ``https://github.com/OWNER/REPO/tree/BRANCH/PATH`` and ``.../blob/BRANCH/PATH/SKILL.md``
      become the hub identifier ``OWNER/REPO/PATH``.
    - ``https://github.com/OWNER/REPO`` becomes ``OWNER/REPO``.
    - A raw ``SKILL.md`` link (raw.githubusercontent.com or gist) is passed through as a URL.

    Anything else is refused: only GitHub links are accepted.
    """
    text = str(link or "").strip()
    if not text:
        raise ValueError("Paste a GitHub link to the skill.")
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Use an https:// GitHub link.")
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.split("/") if part]
    if host in ("raw.githubusercontent.com", "gist.githubusercontent.com"):
        if not parts or parts[-1] != "SKILL.md":
            raise ValueError("A raw link must point at a SKILL.md file.")
        return text
    if host not in ("github.com", "www.github.com"):
        raise ValueError("Only GitHub links can be imported.")
    if len(parts) < 2:
        raise ValueError("That GitHub link does not name a repository.")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    rest = parts[2:]
    if rest and rest[0] in ("tree", "blob"):
        rest = rest[2:]  # drop tree|blob and the branch name
    elif rest:
        raise ValueError("Link to the skill's folder or its SKILL.md on GitHub.")
    if rest and rest[-1] == "SKILL.md":
        rest = rest[:-1]
    segments = [owner, repo, *rest]
    if not all(_GITHUB_PART_RE.fullmatch(seg) and seg not in (".", "..") for seg in segments):
        raise ValueError("That GitHub link has characters a skill path cannot use.")
    return "/".join(segments)


def create_category(skills_dir: Path, name: str, description: str = "") -> Path:
    """Create ``skills_dir/name`` with the DESCRIPTION.md the agent reads for a category."""
    folder = skills_dir / name
    try:
        folder.resolve().relative_to(skills_dir.resolve())
    except (OSError, ValueError):
        raise ValueError("Invalid category")
    if folder.exists():
        raise FileExistsError(f"The category '{name}' already exists.")
    folder.mkdir(parents=True)
    text = " ".join(str(description or "").split())[:300] or f"{name.replace('-', ' ').replace('_', ' ').capitalize()} skills."
    (folder / "DESCRIPTION.md").write_text(text + "\n", encoding="utf-8")
    return folder


def local_categories(skills_dir: Path) -> list[str]:
    """Top-level category folders (those with a DESCRIPTION.md) in the active skills directory."""
    try:
        return sorted(p.name for p in skills_dir.iterdir()
                      if p.is_dir() and not p.name.startswith(".") and (p / "DESCRIPTION.md").is_file())
    except OSError:
        return []


def install_skill(source: str, category: str = "") -> dict:
    """Run ``hermes skills install`` for the active profile; returns ok, status, output."""
    home, cli_profile = _gateway_restart_profile_context()
    env = os.environ.copy()
    env["HERMES_HOME"] = str(home)
    env["NO_COLOR"] = "1"
    cmd = [_resolve_hermes_command()]
    if cli_profile is not None:
        cmd += ["--profile", cli_profile]
    cmd += ["skills", "install", source, "--yes"]
    if category:
        cmd += ["--category", category]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                              timeout=INSTALL_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "output": "The install took too long and was stopped."}
    except OSError as exc:
        return {"ok": False, "status": "failed", "output": f"Could not run the Hermes CLI: {exc}"}
    output = _ANSI_RE.sub("", (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    tail = output[-1500:]
    if proc.returncode != 0:
        return {"ok": False, "status": "failed", "output": tail}
    if re.search(r"already installed", output, re.I):
        return {"ok": False, "status": "exists", "output": tail}
    return {"ok": True, "status": "installed", "output": tail}
