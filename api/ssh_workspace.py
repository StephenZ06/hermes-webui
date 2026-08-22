"""Read-only remote file browsing for SSH-mode project-bound chats.

Scope (deliberately narrow): list a directory and read a text file's
content, both anchored under the registry's declared ``remote_path``, for
a session bound to an ``access_mode: ssh`` WORKSPACES.yaml project. No
writes, no arbitrary command execution, no interactive shell — that's a
separate, much larger feature (a real remote terminal) and stays out of
scope here. The agent itself still does real SSH work via its own tools
(per the project-lifecycle skill); this module only powers WebUI's file
explorer / preview panels for a bound SSH chat.

Every remote path is built by anchoring a validated, traversal-free
relative path under ``remote_path`` — never a raw user-supplied path —
and every value interpolated into the remote shell command is
``shlex.quote()``-escaped. A connection or auth failure is surfaced as an
error; this module never falls back to a local path (matching
project-lifecycle's own rule: never substitute a local mirror after an
SSH failure).
"""
import logging
import shlex
import subprocess

from api.config import MAX_FILE_BYTES
from api.workspace import _normalize_workspace_rel_path

logger = logging.getLogger(__name__)

SSH_CONNECT_TIMEOUT_S = 10
SSH_COMMAND_TIMEOUT_S = 20
MAX_LIST_ENTRIES = 200


class SshWorkspaceError(Exception):
    """Raised for any SSH connectivity/auth/remote-command failure.

    Callers must surface this as a visible error — never treat it as
    "no entries" / silently fall back to a local path.
    """


def _ssh_base_args(project: dict) -> list[str]:
    ssh_cfg = project.get("ssh") or {}
    target = ssh_cfg.get("target")
    key = ssh_cfg.get("key")
    if not target or not key:
        raise SshWorkspaceError(f"Incomplete SSH config for project '{project.get('key')}'")
    return [
        "ssh",
        "-i", key,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT_S}",
        target,
    ]


def _run_remote(project: dict, remote_command: str) -> str:
    cmd = _ssh_base_args(project) + [remote_command]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=SSH_COMMAND_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise SshWorkspaceError(
            f"SSH command timed out after {SSH_COMMAND_TIMEOUT_S}s"
        ) from exc
    except OSError as exc:
        raise SshWorkspaceError(f"Failed to run ssh: {exc}") from exc
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        logger.warning("SSH command failed for project '%s': %s", project.get("key"), stderr)
        raise SshWorkspaceError(_classify_ssh_error(stderr, proc.returncode))
    return (proc.stdout or b"").decode("utf-8", errors="replace")


def _classify_ssh_error(stderr: str, returncode: int) -> str:
    """Map raw ssh stderr to a generic, browser-safe error category.

    Raw ssh stderr can embed internal hostnames, IPs, or network paths
    (e.g. "connect to host 10.0.5.23 port 22", "Could not resolve hostname
    internal-db.corp.local") that shouldn't reach the browser even though
    they aren't credential material. The full text is still logged
    server-side above for debugging.
    """
    lowered = stderr.lower()
    if "permission denied" in lowered or "authentication" in lowered:
        return "SSH authentication failed (check the configured key/target)"
    if "could not resolve hostname" in lowered or "name or service not known" in lowered:
        return "SSH host could not be resolved"
    if "connection refused" in lowered:
        return "SSH connection refused by remote host"
    if "connection timed out" in lowered or "operation timed out" in lowered:
        return "SSH connection timed out"
    if "no route to host" in lowered or "network is unreachable" in lowered:
        return "SSH remote host unreachable"
    if "host key verification failed" in lowered:
        return "SSH host key verification failed"
    return f"SSH command failed (exit status {returncode})"


def _remote_root(project: dict) -> str:
    ssh_cfg = project.get("ssh") or {}
    remote_path = ssh_cfg.get("remote_path")
    if not remote_path:
        raise SshWorkspaceError(f"Project '{project.get('key')}' has no remote_path configured")
    return str(remote_path).rstrip("/") or "/"


def _anchored_remote_path(project: dict, rel: str) -> str:
    """Resolve rel (validated, traversal-free) under the project's remote_path."""
    norm = _normalize_workspace_rel_path(rel)
    root = _remote_root(project)
    if norm == ".":
        return root
    return f"{root}/{norm}"


def ssh_list_dir(project: dict, rel: str = ".") -> list[dict]:
    """List one directory level under the project's remote_path over SSH.

    Returns entries in the same shape api.workspace.list_dir() uses for
    plain (non-symlink) local entries: {name, path, type, size, mtime_ns}.
    Symlinks are skipped for v1 — resolving/validating a remote symlink
    target safely is out of scope for a read-only browse feature.
    """
    target = _anchored_remote_path(project, rel)
    norm_rel = _normalize_workspace_rel_path(rel)
    # %y: file-type letter (f=file, d=directory, l=symlink, ...); NUL-separated
    # so filenames containing tabs/newlines can't desync the parse.
    remote_command = (
        f"find {shlex.quote(target)} -mindepth 1 -maxdepth 1 "
        f"-printf '%f\\t%y\\t%s\\t%T@\\0' 2>/dev/null"
    )
    output = _run_remote(project, remote_command)
    entries: list[dict] = []
    for record in output.split("\0"):
        if not record:
            continue
        parts = record.split("\t")
        if len(parts) != 4:
            continue
        name, type_letter, size_s, mtime_s = parts
        if type_letter not in ("f", "d"):
            continue  # skip symlinks and other special types (v1 scope)
        is_dir = type_letter == "d"
        entry_path = name if norm_rel == "." else f"{norm_rel}/{name}"
        try:
            mtime_ns = int(float(mtime_s) * 1_000_000_000)
        except ValueError:
            mtime_ns = None
        entries.append({
            "name": name,
            "path": entry_path,
            "type": "dir" if is_dir else "file",
            "size": None if is_dir else int(size_s) if size_s.isdigit() else None,
            "mtime_ns": mtime_ns,
        })
        if len(entries) >= MAX_LIST_ENTRIES:
            break
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    return entries


def ssh_read_file(project: dict, rel: str) -> dict:
    """Read a remote text file's content over SSH.

    Returns the same shape api.workspace.read_file_content() returns for a
    plain text file: {path, content, size, lines}. Binary files, office
    documents, and images are out of scope for v1 — request them and get a
    clear SshWorkspaceError instead of a garbled preview.
    """
    target = _anchored_remote_path(project, rel)
    norm_rel = _normalize_workspace_rel_path(rel)
    stat_out = _run_remote(
        project,
        f"stat -c '%s|%F' {shlex.quote(target)} 2>&1 || echo MISSING",
    )
    stat_out = stat_out.strip()
    if stat_out == "MISSING" or "|" not in stat_out:
        raise SshWorkspaceError(f"Remote file not found: {rel}")
    size_s, file_type = stat_out.split("|", 1)
    if "regular file" not in file_type:
        raise SshWorkspaceError(f"Not a regular file: {rel}")
    try:
        size = int(size_s)
    except ValueError:
        raise SshWorkspaceError(f"Could not determine remote file size: {rel}")
    if size > MAX_FILE_BYTES:
        raise SshWorkspaceError(f"File too large ({size} bytes, max {MAX_FILE_BYTES})")
    content = _run_remote(
        project,
        f"head -c {MAX_FILE_BYTES + 1} {shlex.quote(target)}",
    )
    return {
        "path": norm_rel,
        "content": content,
        "size": size,
        "lines": content.count("\n") + 1,
    }
