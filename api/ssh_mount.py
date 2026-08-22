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
    if not path or not Path(path).exists():
        return "disconnected"
    try:
        proc = subprocess.run(
            ["mountpoint", "-q", str(path)],
            capture_output=True,
            timeout=STATUS_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "disconnected"
    return "connected" if proc.returncode == 0 else "disconnected"


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
            reconnect_all_on_boot()
        except Exception as e:
            print(f'[!!] WARNING: Remote workspace reconnect failed: {e}', flush=True)

    t = threading.Thread(target=_safe, daemon=True)
    t.start()
    t.join(timeout=5)
    if t.is_alive():
        print('[tip] Remote workspace reconnect still in progress (non-blocking)', flush=True)


def reconnect_all_on_boot() -> None:
    """Best-effort mount of every saved remote workspace at webui startup.

    Never raises — a host that's unreachable at boot just stays
    disconnected until the user hits Reconnect (or it comes back and a
    later reconcile succeeds); it must never block or fail webui startup.
    """
    from api.workspace import load_workspaces

    for entry in load_workspaces():
        if entry.get("kind") != "remote":
            continue
        try:
            mount_remote(entry)
        except SshMountError as exc:
            logger.warning(
                "Boot-time reconnect failed for remote workspace '%s': %s",
                entry.get("name") or entry.get("path"), exc,
            )
        except Exception:
            logger.exception(
                "Unexpected error reconnecting remote workspace '%s' at boot",
                entry.get("name") or entry.get("path"),
            )
