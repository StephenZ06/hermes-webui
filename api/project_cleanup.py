"""Stopping a project's work and removing its data when it is deleted.

A project the wizard has just created keeps working in the background: the
Architecture setup turn installs dependencies and writes files into the new
folder, and the commands it starts can outlive the turn. Deleting the project
(or its folder on the Files page) must stop all of that *before* the folder
goes, or an install still running would write the folder straight back.

Order on every path: stop the setup jobs (their hidden turns and the
processes those turns registered), then any other process whose working
directory is inside the folder, then remove the folder, then forget the
registry entry the wizard added.

Only folders the wizard created (``created_folder`` on the project record) are
ever removed here. An adopted project's folder belonged to the user before
Hermes saw it and is never deleted.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_TERM_GRACE_SECONDS = 2.0


def _cwd_inside(pid: int, root: Path) -> bool:
    try:
        cwd = Path(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        return False
    # A process whose folder is already gone shows " (deleted)" after its path.
    text = str(cwd)
    if text.endswith(" (deleted)"):
        cwd = Path(text[: -len(" (deleted)")])
    try:
        cwd.relative_to(root)
        return True
    except ValueError:
        return False


def _own_lineage() -> set[int]:
    """This server and its parents: never signalled, whatever their folder."""
    pids, pid = set(), os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
                pid = int(handle.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return pids


def processes_in(folder: str | Path) -> list[int]:
    """PIDs of this user's processes whose working directory is inside ``folder``."""
    root = Path(folder).resolve()
    if not Path("/proc").is_dir():
        return []
    uid, skip, found = os.getuid(), _own_lineage(), []
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in skip:
            continue
        try:
            if entry.stat(follow_symlinks=False).st_uid != uid:
                continue
        except OSError:
            continue
        if _cwd_inside(pid, root):
            found.append(pid)
    return found


def kill_processes_in(folder: str | Path) -> int:
    """Stop every process working inside ``folder``: SIGTERM, then SIGKILL.

    Returns how many were signalled.
    """
    pids = processes_in(folder)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + _TERM_GRACE_SECONDS
    alive = list(pids)
    while alive and time.monotonic() < deadline:
        time.sleep(0.1)
        alive = [pid for pid in alive if Path(f"/proc/{pid}").exists() and _cwd_inside_any(pid, folder)]
    for pid in alive:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if pids:
        logger.info("Stopped %d process(es) working in %s", len(pids), folder)
    return len(pids)


def _cwd_inside_any(pid: int, folder: str | Path) -> bool:
    # A PID reused by an unrelated process must not be killed.
    return _cwd_inside(pid, Path(folder).resolve())


def stop_work_in(folder: str | Path, *, project_id: str | None = None) -> dict:
    """Stop setup jobs for ``project_id`` or inside ``folder``, then the processes left there."""
    from api.project_starter_agent import stop_jobs

    jobs = stop_jobs(under=folder, project_id=project_id)
    killed = kill_processes_in(folder) if folder and Path(folder).exists() else 0
    return {"jobs": len(jobs), "processes": killed}


def remove_created_folder(project: dict) -> bool:
    """Delete the folder the wizard created for ``project``; True when removed.

    Refuses anything the wizard did not create, a symlink, or a path that is
    not a plain folder under its parent.
    """
    from api.workspace import rmtree_anchored

    if not project.get("created_folder"):
        return False
    path = Path(str(project.get("workspace_path") or ""))
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        return False
    resolved = path.resolve()
    if resolved.parent == resolved:
        return False
    rmtree_anchored(resolved.parent, resolved)
    return True


def forget_registry_entry(project: dict) -> bool:
    from api.project_starter import unregister_from_lifecycle_registry

    key = project.get("registry_key")
    path = project.get("workspace_path")
    return bool(key and path and unregister_from_lifecycle_registry(str(key), Path(str(path))))


def delete_project_data(project: dict, *, delete_folder: bool) -> dict:
    """Stop the project's work; with ``delete_folder`` also remove what the wizard made.

    Returns ``{"jobs", "processes", "folder_deleted", "registry_removed"}``.
    """
    folder = str(project.get("workspace_path") or "")
    remove = bool(delete_folder and project.get("created_folder") and folder)
    if remove:
        out = stop_work_in(folder, project_id=project.get("project_id"))
    else:
        from api.project_starter_agent import stop_jobs

        out = {"jobs": len(stop_jobs(project_id=project.get("project_id"))), "processes": 0}
    out["folder_deleted"] = remove_created_folder(project) if remove else False
    out["registry_removed"] = forget_registry_entry(project) if remove else False
    return out


def folder_deleted(folder: str | Path) -> list[str]:
    """After a folder is deleted on the Files page: drop the projects the wizard made in it.

    A project whose folder the wizard created and which is now gone is removed
    with its registry entry, when it has no chats or work items (the same rule
    as deleting a project by hand). Returns the removed project ids.
    """
    from api import work_hub
    from api.models import load_projects, save_projects

    root = Path(folder).resolve()
    projects = load_projects()
    gone = [p for p in projects if p.get("created_folder") and p.get("workspace_path")
            and not Path(str(p["workspace_path"])).exists() and _under(str(p["workspace_path"]), root)]
    if not gone:
        return []
    removable = set(work_hub.deletable_project_ids(gone))
    removed = []
    for project in gone:
        pid = project["project_id"]
        if pid not in removable:
            continue
        try:
            work_hub.delete_project_contents(pid)
        except work_hub.WorkHubError:
            logger.warning("Kept project %s: its Work Hub contents could not be removed", pid)
            continue
        forget_registry_entry(project)
        removed.append(pid)
    if removed:
        save_projects([p for p in load_projects() if p.get("project_id") not in removed])
        from api.routes import _reassign_project_sessions

        _reassign_project_sessions(set(removed), None)
    return removed


def _under(path: str, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False
