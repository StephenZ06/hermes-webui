"""End-of-turn check: did a turn that changed project files update the handoff?

``docs_check`` looks only at the turn's own tool calls. When one of them wrote or
edited a file outside ``.agent/`` in a workspace that has
``.agent/ECC_HANDOFF.md``, and the handoff was not modified since the turn
started, the WebUI shows a "Docs not updated" chip under the reply. Nothing is
sent to the model unless the user presses it.
"""

from __future__ import annotations

import re
from pathlib import Path

HANDOFF = ".agent/ECC_HANDOFF.md"
MUTATING_TOOLS = {"write_file", "patch", "edit_file", "create_file", "mcp_filesystem_write_file", "mcp_filesystem_edit_file"}
_PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)


def _changed_paths(args: dict) -> list[str]:
    paths = [str(args.get(k)) for k in ("path", "file_path") if args.get(k)]
    patch = args.get("patch")
    if isinstance(patch, str):
        paths += [m.strip() for m in _PATCH_FILE_RE.findall(patch)]
    return paths


def _inside_agent_dir(root: Path, raw: str) -> bool:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        rel = path.resolve().relative_to(root)
    except (OSError, ValueError):
        return False  # outside the project: does not count as a project change
    return rel.parts[:1] == (".agent",)


def _inside(root: Path, raw: str) -> bool:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        path.resolve().relative_to(root)
        return True
    except (OSError, ValueError):
        return False


def docs_check(workspace, tool_calls, since: float) -> dict | None:
    """``{"stale": True, "files": n}`` when the handoff should have been updated, else None."""
    if not workspace:
        return None
    root = Path(workspace).expanduser()
    try:
        root = root.resolve()
        handoff = root / HANDOFF
        if not handoff.is_file():
            return None
        changed = set()
        for call in tool_calls or []:
            if not isinstance(call, dict) or call.get("name") not in MUTATING_TOOLS:
                continue
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            for raw in _changed_paths(args):
                if _inside(root, raw) and not _inside_agent_dir(root, raw):
                    changed.add(raw)
        if not changed:
            return None
        if handoff.stat().st_mtime >= float(since) - 1:
            return None
    except OSError:
        return None
    return {"stale": True, "files": len(changed)}
