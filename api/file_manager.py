"""Safe, workspace-scoped file operations for the Files page.

The page never accepts a filesystem root from the browser.  It only resolves
opaque IDs generated from the saved Spaces list or the agent project registry,
then performs every operation relative to that trusted root.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from api.project_registry import list_registry_projects
from api.ssh_workspace import SshWorkspaceError, ssh_list_dir, ssh_read_file, ssh_reachable
from api.workspace import (
    _normalize_workspace_rel_path,
    dir_signature,
    list_dir,
    load_workspaces,
    make_anchored_dir,
    open_anchored_create_fd,
    open_anchored_fd,
    open_anchored_write_fd,
    read_file_content,
    rename_anchored,
    rmtree_anchored,
    safe_resolve_ws,
    serialize_workspace_entries_for_browser,
    unlink_anchored,
    workspace_availability,
)
from api.config import MAX_FILE_BYTES


class FileManagerError(ValueError):
    """A browser-safe failure with its intended HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class WorkspaceFileContext:
    workspace_id: str
    name: str
    kind: str
    available: bool
    root: Path | None = None
    project: dict | None = None

    @property
    def read_only(self) -> bool:
        return self.kind == "ssh"


def _local_id(path: str) -> str:
    digest = hashlib.sha256(str(Path(path).expanduser().resolve()).encode("utf-8")).hexdigest()[:20]
    return f"local:{digest}"


def _context_from_local(entry: dict) -> WorkspaceFileContext | None:
    path = str(entry.get("path") or "").strip()
    if not path:
        return None
    root = Path(path).expanduser()
    return WorkspaceFileContext(
        workspace_id=_local_id(path),
        name=str(entry.get("name") or root.name or "Workspace"),
        kind="local",
        available=workspace_availability(entry) == "online",
        root=root,
    )


def _context_from_mount(entry: dict) -> WorkspaceFileContext | None:
    path = str(entry.get("path") or "").strip()
    if not path:
        return None
    # The id comes from the saved path as written: resolving it would stat through
    # the mount, which can hang while its host is unreachable.
    digest = hashlib.sha256(os.path.normpath(os.path.expanduser(path)).encode("utf-8")).hexdigest()[:20]
    root = Path(path).expanduser()
    return WorkspaceFileContext(
        workspace_id=f"mount:{digest}",
        name=str(entry.get("name") or root.name or "Remote space"),
        kind="local",
        available=workspace_availability(entry) == "online",
        root=root,
    )


def _contexts() -> list[WorkspaceFileContext]:
    """Build the only workspace allow-list accepted by the Files API."""
    contexts: list[WorkspaceFileContext] = []
    seen_roots: set[str] = set()
    for entry in load_workspaces():
        if entry.get("kind") == "remote":
            # A saved SSHFS space is a folder the remote host is mounted on, so it is
            # browsed like any local folder, every operation anchored under it. It is
            # offered only while the mount is live (checked again on every request),
            # so nothing is written into the empty mountpoint of a dropped mount.
            context = _context_from_mount(entry)
            if context is not None and context.workspace_id not in seen_roots:
                seen_roots.add(context.workspace_id)
                contexts.append(context)
            continue
        context = _context_from_local(entry)
        if context is None:
            continue
        resolved = str(context.root.resolve()) if context.root else ""
        if resolved in seen_roots:
            continue
        seen_roots.add(resolved)
        contexts.append(context)

    for project in list_registry_projects():
        if not project.get("available"):
            continue
        key = str(project.get("key") or "").strip()
        mode = project.get("access_mode")
        if not key or mode not in {"local", "ssh"}:
            continue
        if mode == "local":
            path = str(project.get("repo_path") or "").strip()
            if not path:
                continue
            root = Path(path).expanduser()
            resolved = str(root.resolve())
            if resolved in seen_roots:
                continue
            seen_roots.add(resolved)
            contexts.append(WorkspaceFileContext(
                workspace_id=f"project:{key}",
                name=str(project.get("name") or key),
                kind="local",
                available=root.is_dir(),
                root=root,
                project=project,
            ))
        else:
            contexts.append(WorkspaceFileContext(
                workspace_id=f"project:{key}",
                name=str(project.get("name") or key),
                kind="ssh",
                available=True,
                project=project,
            ))
    return contexts


# An SSH space is only known to be online once a connection to it succeeds. The
# answer is kept for a short while so the page's status poll does not open a
# connection per space on every call.
_SSH_STATUS_TTL_S = 45.0
_ssh_status: dict[str, tuple[float, bool]] = {}
_ssh_status_lock = threading.Lock()


def _ssh_online(context: WorkspaceFileContext) -> bool:
    now = time.monotonic()
    with _ssh_status_lock:
        cached = _ssh_status.get(context.workspace_id)
    if cached and now - cached[0] < _SSH_STATUS_TTL_S:
        return cached[1]
    online = ssh_reachable(context.project or {})
    with _ssh_status_lock:
        _ssh_status[context.workspace_id] = (time.monotonic(), online)
    return online


def list_file_manager_workspaces() -> list[dict]:
    """Every space the page may open, each with whether it can be reached right now."""
    return [
        {
            "id": context.workspace_id,
            "name": context.name,
            "kind": context.kind,
            "available": context.available and (context.kind != "ssh" or _ssh_online(context)),
            "read_only": context.read_only,
        }
        for context in _contexts()
    ]


def resolve_file_manager_workspace(workspace_id: str) -> WorkspaceFileContext:
    requested = str(workspace_id or "").strip()
    for context in _contexts():
        if context.workspace_id == requested:
            if not context.available:
                raise FileManagerError("Workspace is unavailable", 409)
            return context
    # Do not distinguish a malformed, absent, or inaccessible ID.
    raise FileManagerError("Workspace not found", 404)


def _normal_path(path: str) -> str:
    try:
        return _normalize_workspace_rel_path(path)
    except ValueError as exc:
        raise FileManagerError(str(exc)) from None


def _local_target(context: WorkspaceFileContext, path: str) -> tuple[Path, str]:
    if context.root is None:
        raise FileManagerError("Workspace is unavailable", 409)
    rel = _normal_path(path)
    try:
        return safe_resolve_ws(context.root, rel), rel
    except ValueError as exc:
        raise FileManagerError(str(exc)) from None


def _local_context(context: WorkspaceFileContext) -> Path:
    if context.kind != "local" or context.root is None:
        raise FileManagerError("This remote workspace is read-only", 409)
    return context.root


def _reject_symlink(root: Path, rel: str, action: str) -> None:
    if rel != "." and (root / rel).is_symlink():
        raise FileManagerError(f"Cannot {action} a symlinked entry")


def _parent(rel: str) -> str:
    parent = str(PurePosixPath(rel).parent)
    return "." if parent in ("", ".") else parent


def list_directory(workspace_id: str, path: str = ".") -> dict:
    context = resolve_file_manager_workspace(workspace_id)
    rel = _normal_path(path)
    try:
        if context.kind == "ssh":
            entries = ssh_list_dir(context.project or {}, rel)
            return {"workspace_id": context.workspace_id, "path": rel, "entries": entries, "read_only": True}
        root = _local_context(context)
        entries = list_dir(root, rel)
        return {
            "workspace_id": context.workspace_id,
            "path": rel,
            "entries": serialize_workspace_entries_for_browser(entries),
            "signature": dir_signature(root, rel, entries),
            "read_only": False,
        }
    except (SshWorkspaceError, FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc), 404 if isinstance(exc, FileNotFoundError) else 400) from None


def _looks_binary(content: str) -> bool:
    """Decoded bytes that are not text: a NUL, or many undecodable bytes, near the start."""
    head = content[:8192]
    return "\x00" in head or head.count("\ufffd") > max(8, len(head) // 100)


def _without_text(payload: dict, kind: str) -> dict:
    """A file the editor cannot show: its name and size, never its bytes as characters."""
    content = payload.get("content") or ""
    return {"path": payload.get("path"), "size": payload.get("size", len(content)), "preview_kind": kind}


def read_file(workspace_id: str, path: str) -> dict:
    context = resolve_file_manager_workspace(workspace_id)
    rel = _normal_path(path)
    try:
        if context.kind == "ssh":
            payload = ssh_read_file(context.project or {}, rel)
            if _looks_binary(str(payload.get("content") or "")):
                payload = _without_text(payload, "binary")
            return {**payload, "workspace_id": context.workspace_id, "read_only": True}
        root = _local_context(context)
        target, rel = _local_target(context, rel)
        if target.is_file():
            size = target.stat().st_size
            if size > MAX_FILE_BYTES:
                return {"path": rel, "size": size, "preview_kind": "too_large",
                        "workspace_id": context.workspace_id, "read_only": False}
        payload = read_file_content(root, rel)
        if not payload.get("preview_kind") and _looks_binary(str(payload.get("content") or "")):
            payload = _without_text(payload, "binary")
        return {**payload, "workspace_id": context.workspace_id, "read_only": False}
    except (SshWorkspaceError, FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc), 404 if isinstance(exc, FileNotFoundError) else 400) from None


def raw_file_target(workspace_id: str, path: str) -> tuple[Path, Path, str]:
    """The trusted root, the file inside it and its name, for streaming a local file.

    The caller opens the file anchored under the root (no symlink followed), so a
    path swapped after this check cannot escape the space. Remote spaces have no
    byte stream here.
    """
    context = resolve_file_manager_workspace(workspace_id)
    if context.kind != "local":
        raise FileManagerError("Previews of remote files are not available", 409)
    root = _local_context(context)
    target, rel = _local_target(context, path)
    if rel == "." or not target.is_file():
        raise FileManagerError("Not a file", 404)
    return root, target, PurePosixPath(rel).name or "download"


def download_file(workspace_id: str, path: str) -> tuple[bytes, str, str]:
    """Return verified bytes and a safe download name without disclosing roots."""
    context = resolve_file_manager_workspace(workspace_id)
    rel = _normal_path(path)
    try:
        if context.kind == "ssh":
            payload = ssh_read_file(context.project or {}, rel)
            return (
                str(payload.get("content") or "").encode("utf-8"),
                PurePosixPath(rel).name or "download",
                "text/plain; charset=utf-8",
            )
        root = _local_context(context)
        target, _ = _local_target(context, rel)
        fd = open_anchored_fd(root, target, want_dir=False)
        with os.fdopen(fd, "rb", closefd=True) as handle:
            size = os.fstat(handle.fileno()).st_size
            if size > MAX_FILE_BYTES:
                raise FileManagerError(f"File too large ({size} bytes, max {MAX_FILE_BYTES})", 413)
            raw = handle.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise FileManagerError(f"File too large (max {MAX_FILE_BYTES})", 413)
        mime = mimetypes.guess_type(PurePosixPath(rel).name)[0] or "application/octet-stream"
        return raw, PurePosixPath(rel).name or "download", mime
    except FileManagerError:
        raise
    except (SshWorkspaceError, FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc), 404 if isinstance(exc, FileNotFoundError) else 400) from None


def create_file(workspace_id: str, path: str, content: str = "") -> dict:
    context = resolve_file_manager_workspace(workspace_id)
    root = _local_context(context)
    target, rel = _local_target(context, path)
    if rel == "." or target.exists():
        raise FileManagerError("File already exists")
    try:
        fd = open_anchored_create_fd(root, target)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(str(content).encode("utf-8"))
    except FileExistsError:
        raise FileManagerError("File already exists") from None
    except (FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc)) from None
    return {"ok": True, "path": rel, "parent_path": _parent(rel)}


def create_directory(workspace_id: str, path: str) -> dict:
    context = resolve_file_manager_workspace(workspace_id)
    root = _local_context(context)
    target, rel = _local_target(context, path)
    if rel == "." or target.exists():
        raise FileManagerError("Path already exists")
    try:
        make_anchored_dir(root, target)
    except (FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc)) from None
    return {"ok": True, "path": rel, "parent_path": _parent(rel)}


def save_file(workspace_id: str, path: str, content: str) -> dict:
    context = resolve_file_manager_workspace(workspace_id)
    root = _local_context(context)
    target, rel = _local_target(context, path)
    _reject_symlink(root, rel, "save")
    if not target.exists() or target.is_dir():
        raise FileManagerError("File not found", 404)
    try:
        fd = open_anchored_write_fd(root, target)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            data = str(content).encode("utf-8")
            handle.write(data)
    except (FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc)) from None
    return {"ok": True, "path": rel, "parent_path": _parent(rel), "size": len(data)}


def rename_file(workspace_id: str, path: str, new_name: str) -> dict:
    context = resolve_file_manager_workspace(workspace_id)
    root = _local_context(context)
    target, rel = _local_target(context, path)
    _reject_symlink(root, rel, "rename")
    name = str(new_name or "").strip()
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise FileManagerError("Invalid file name")
    if not target.exists():
        raise FileManagerError("File not found", 404)
    dest = target.parent / name
    if dest.exists():
        raise FileManagerError(f'A file named "{name}" already exists')
    try:
        rename_anchored(root, target, dest)
    except (FileExistsError, FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc)) from None
    new_rel = dest.relative_to(root.resolve()).as_posix()
    return {"ok": True, "old_path": rel, "path": new_rel, "parent_path": _parent(new_rel)}


def move_path(workspace_id: str, path: str, destination: str) -> dict:
    context = resolve_file_manager_workspace(workspace_id)
    root = _local_context(context)
    source, rel = _local_target(context, path)
    _reject_symlink(root, rel, "move")
    dest_dir, dest_rel = _local_target(context, destination)
    if not source.exists():
        raise FileManagerError("File not found", 404)
    if not dest_dir.is_dir():
        raise FileManagerError("Destination folder not found", 404)
    if source.is_dir():
        try:
            dest_dir.resolve().relative_to(source.resolve())
        except ValueError:
            pass
        else:
            raise FileManagerError("Cannot move a folder into itself or its subfolder")
    target = dest_dir / source.name
    if target.exists():
        raise FileManagerError(f'A file named "{source.name}" already exists in that folder')
    try:
        rename_anchored(root, source, target)
    except (FileExistsError, FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc)) from None
    new_rel = target.relative_to(root.resolve()).as_posix()
    return {"ok": True, "old_path": rel, "path": new_rel, "parent_path": _parent(new_rel), "source_parent_path": _parent(rel), "destination_path": dest_rel}


def delete_path(workspace_id: str, path: str, recursive: bool = False) -> dict:
    context = resolve_file_manager_workspace(workspace_id)
    root = _local_context(context)
    target, rel = _local_target(context, path)
    _reject_symlink(root, rel, "delete")
    if rel == "." or not target.exists():
        raise FileManagerError("File not found", 404)
    if target.is_dir() and not recursive:
        raise FileManagerError("Set recursive=true to delete directories")
    try:
        if target.is_dir():
            rmtree_anchored(root, target)
        else:
            unlink_anchored(root, target)
    except (FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc)) from None
    return {"ok": True, "path": rel, "parent_path": _parent(rel)}


def upload_file(workspace_id: str, path: str, filename: str, data_b64: str) -> dict:
    """Create an uploaded file under the current workspace-relative directory."""
    clean_name = Path(str(filename or "")).name
    if not clean_name or clean_name in {".", ".."}:
        raise FileManagerError("Invalid upload filename")
    directory = _normal_path(path)
    destination = clean_name if directory == "." else f"{directory}/{clean_name}"
    try:
        raw = base64.b64decode(str(data_b64 or ""), validate=True)
    except Exception:
        raise FileManagerError("Invalid upload data") from None
    # Keep browser payloads bounded even when a caller bypasses the UI.
    if len(raw) > 25 * 1024 * 1024:
        raise FileManagerError("File too large (max 25 MB)", 413)
    context = resolve_file_manager_workspace(workspace_id)
    root = _local_context(context)
    target, rel = _local_target(context, destination)
    if target.exists():
        raise FileManagerError("File already exists")
    try:
        fd = open_anchored_create_fd(root, target)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(raw)
    except (FileExistsError, FileNotFoundError, PermissionError, OSError, ValueError) as exc:
        raise FileManagerError(str(exc)) from None
    return {"ok": True, "path": rel, "parent_path": _parent(rel), "size": len(raw)}
