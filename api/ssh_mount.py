"""Real SSHFS mounting for remote Workspaces ("Spaces") entries.

Deliberately a separate module from ``api/ssh_workspace.py``, which does
read-only remote file browsing over raw ``ssh`` exec commands for an
unrelated "SSH-bound project" chat feature and is explicitly scoped to
never mount or write. This module's whole purpose — mounting a real
filesystem that the rest of the app (session file explorer, agent tool
calls, everything) then treats exactly like any local workspace path — is
precisely what that module's docstring rules out.

Every remote entry's private key must already exist as a file reachable
inside the container (bind-mounted via docker-compose, same convention
``ssh_workspace.py`` uses for its ``ssh.key`` config) — this module never
accepts or stores raw key material.

See docs/superpowers/specs/2026-08-22-sshfs-remote-workspaces-design.md.
"""
import logging
import subprocess
from pathlib import Path

from api.ssh_workspace import _classify_ssh_error

logger = logging.getLogger(__name__)

MOUNT_TIMEOUT_S = 15
UNMOUNT_TIMEOUT_S = 10
STATUS_TIMEOUT_S = 5


class SshMountError(Exception):
    """Raised for any SSHFS mount/unmount failure.

    Callers must surface this as a visible error — a failed mount must
    never be silently treated as "workspace unavailable" without telling
    the user why.
    """


def _is_kernel_mountpoint(path: str) -> bool:
    """True if the kernel still lists *path* as a mountpoint.

    Says nothing about whether the mount still works -- a FUSE endpoint whose
    userspace process is gone is still a mountpoint by this measure.
    """
    try:
        proc = subprocess.run(
            ["mountpoint", "-q", str(path)],
            capture_output=True,
            timeout=STATUS_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def _path_state(path: Path) -> str:
    """Classify *path* as 'ok', 'missing', or 'unusable'.

    ``Path.exists()`` is not usable here: on a stale FUSE endpoint the stat
    fails with EACCES or ENOTCONN, and on Python 3.12 ``exists()`` lets that
    propagate instead of returning False. An uncaught PermissionError out of
    mount_status() took down the whole boot-time reconcile, which is what made
    a stale mountpoint permanent -- every restart re-raised before it could
    remount.

    'missing' and 'unusable' are kept apart because only the latter is worth
    a lazy unmount: a path that is not there at all has no mount to clear.
    """
    try:
        path.stat()
        return "ok"
    except FileNotFoundError:
        return "missing"
    except NotADirectoryError:
        return "missing"
    except OSError:
        return "unusable"


def _proc_lists_mount(path: str) -> bool:
    """True if /proc/self/mounts lists *path* as a mount point.

    This is the only reliable probe for a stale endpoint: ``mountpoint -q``
    stats the path to answer, so on a dead FUSE mount it fails and reports
    "not a mountpoint" -- the exact case that needs detecting. Reading
    /proc is a pure string comparison and never touches the mount.
    """
    target = str(path).rstrip("/") or "/"
    try:
        with open("/proc/self/mounts", "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 2:
                    continue
                # Mount points are octal-escaped in /proc (space -> \040).
                mounted = parts[1].encode("utf-8", "replace").decode("unicode_escape")
                if mounted.rstrip("/") == target:
                    return True
    except OSError:
        return False
    return False


def _is_stale_mountpoint(mountpoint: Path) -> bool:
    """True if *mountpoint* is mounted but no longer usable."""
    if _path_state(mountpoint) != "unusable":
        return False
    return _proc_lists_mount(str(mountpoint)) or _is_kernel_mountpoint(str(mountpoint))


def _clear_stale_mountpoint(mountpoint: Path) -> bool:
    """Lazily unmount *mountpoint* if it is a mountpoint that no longer works.

    A container restart kills the sshfs process while leaving the kernel mount
    behind, so the path is simultaneously "already mounted" (nothing new can
    mount over it) and unusable (every stat fails). Only a lazy unmount clears
    that. Returns True if a stale mount was cleared.
    """
    if not _is_stale_mountpoint(mountpoint):
        return False
    try:
        subprocess.run(
            ["fusermount", "-uz", str(mountpoint)],
            capture_output=True,
            timeout=UNMOUNT_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        logger.warning("Could not clear stale mountpoint %s", mountpoint)
        return False
    logger.info("cleared stale mountpoint %s", mountpoint)
    return True


def _remote_cfg(entry: dict) -> dict:
    remote = entry.get("remote") or {}
    host = remote.get("host")
    remote_path = remote.get("remote_path")
    key_path = remote.get("key_path")
    if not host or not remote_path or not key_path:
        raise SshMountError(
            f"Incomplete remote config for workspace '{entry.get('name') or entry.get('path')}'"
        )
    return {"host": host, "remote_path": remote_path, "key_path": key_path}


def mount_remote(entry: dict) -> None:
    """Mount a remote workspace entry's mountpoint via sshfs.

    No-op if already mounted. Raises SshMountError (safe, classified
    message) on any failure — callers decide whether that's fatal
    (interactive add) or just logged (boot-time reconcile).
    """
    mountpoint = Path(entry["path"])
    if mount_status(entry) == "connected":
        return
    cfg = _remote_cfg(entry)
    # A dead mount from a previous run blocks both the mkdir below and sshfs
    # itself, so it has to go before anything else is attempted.
    _clear_stale_mountpoint(mountpoint)
    try:
        mountpoint.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SshMountError(f"Could not create mountpoint {mountpoint}: {exc}") from exc

    target = f"{cfg['host']}:{cfg['remote_path']}"
    cmd = [
        "sshfs",
        "-o", ",".join([
            "reconnect",
            "ServerAliveInterval=15",
            "ServerAliveCountMax=3",
            "IdentitiesOnly=yes",
            "StrictHostKeyChecking=accept-new",
            f"IdentityFile={cfg['key_path']}",
        ]),
        target,
        str(mountpoint),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=MOUNT_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise SshMountError(f"sshfs mount timed out after {MOUNT_TIMEOUT_S}s") from exc
    except OSError as exc:
        raise SshMountError(f"Failed to run sshfs: {exc}") from exc
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        logger.warning(
            "sshfs mount failed for workspace '%s' (%s): %s",
            entry.get("name"), target, stderr,
        )
        raise SshMountError(_classify_ssh_error(stderr, proc.returncode))
    logger.info("sshfs mounted %s at %s", target, mountpoint)


def unmount_remote(entry: dict) -> None:
    """Unmount a remote workspace's mountpoint.

    Tries a clean ``fusermount -u`` first; falls back to a lazy
    ``fusermount -uz`` if the mount has gone stale (e.g. "Transport
    endpoint not connected" after the remote host dropped without a clean
    disconnect) — a plain unmount can't clear that, only a lazy one can.
    """
    mountpoint = str(entry["path"])
    if mount_status(entry) != "connected":
        # "disconnected" covers a stale endpoint as well as a genuinely
        # unmounted path; the former still needs clearing, or nothing can ever
        # mount here again.
        _clear_stale_mountpoint(Path(mountpoint))
        return
    for args in (["fusermount", "-u", mountpoint], ["fusermount", "-uz", mountpoint]):
        try:
            proc = subprocess.run(args, capture_output=True, timeout=UNMOUNT_TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            raise SshMountError(f"Unmount timed out after {UNMOUNT_TIMEOUT_S}s") from exc
        except OSError as exc:
            raise SshMountError(f"Failed to run fusermount: {exc}") from exc
        if proc.returncode == 0:
            logger.info("unmounted %s", mountpoint)
            return
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
    raise SshMountError(f"Failed to unmount {mountpoint}: {stderr or 'unknown error'}")


def mount_status(entry: dict) -> str:
    """'connected' if entry['path'] is currently a live FUSE mountpoint, else 'disconnected'.

    Checks the local FUSE mount table only (``mountpoint -q``) — no SSH
    round-trip — so it's cheap enough to call on every Workspaces panel
    load rather than trusting a persisted last-known value.
    """
    path = entry.get("path")
    if not path:
        return "disconnected"
    # Missing, or present but unusable (stale FUSE endpoint) -- either way it
    # is not something the app can read, so it is disconnected. Reporting a
    # stale endpoint as "connected" would make mount_remote() a no-op and the
    # workspace could never recover on its own.
    if _path_state(Path(path)) != "ok":
        return "disconnected"
    return "connected" if _is_kernel_mountpoint(str(path)) else "disconnected"


def start_reconnect_thread() -> None:
    """Kick off reconnect_all_on_boot() in a background thread at webui startup.

    Self-contained (catches its own exceptions, prints its own warnings) so
    server.py's call site can be a single line — mirrors the other
    best-effort startup hooks there (gateway watcher, drain thread), which
    all wait up to 5s so boot-log ordering stays sane but never block
    startup on a slow/unreachable remote host.
    """
    import threading

    def _safe():
        try:
            summary = reconnect_all_on_boot()
        except Exception as e:
            print(f'[!!] WARNING: Remote workspace reconnect failed: {e}', flush=True)
            return
        if not summary.get("remote_entries"):
            return
        if summary.get("failed"):
            for err in summary.get("errors", []):
                print(f'[!!] WARNING: Remote workspace reconnect: {err}', flush=True)
        if summary.get("mounted"):
            print(
                f'[ok] Remote workspaces reconnected: {summary["mounted"]}'
                f'/{summary["remote_entries"]}',
                flush=True,
            )

    t = threading.Thread(target=_safe, daemon=True)
    t.start()
    t.join(timeout=5)
    if t.is_alive():
        print('[tip] Remote workspace reconnect still in progress (non-blocking)', flush=True)


def reconnect_all_on_boot() -> dict:
    """Best-effort mount of every saved remote workspace at webui startup.

    Never raises — a host that's unreachable at boot just stays
    disconnected until the user hits Reconnect (or it comes back and a
    later reconcile succeeds); it must never block or fail webui startup.

    Returns a small summary so the caller can say what happened on the boot
    log. This used to be entirely silent in both directions, which meant a
    remote workspace that quietly never reconnected looked exactly like one
    that had no folders on the far end.
    """
    from api.workspace import load_workspaces

    summary = {"mounted": 0, "failed": 0, "remote_entries": 0, "errors": []}
    for entry in load_workspaces():
        if entry.get("kind") != "remote":
            continue
        summary["remote_entries"] += 1
        label = entry.get("name") or entry.get("path")
        try:
            mount_remote(entry)
            summary["mounted"] += 1
        except SshMountError as exc:
            summary["failed"] += 1
            summary["errors"].append(f"{label}: {exc}")
            logger.warning(
                "Boot-time reconnect failed for remote workspace '%s': %s", label, exc,
            )
        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append(f"{label}: {exc}")
            logger.exception(
                "Unexpected error reconnecting remote workspace '%s' at boot", label,
            )
    return summary
