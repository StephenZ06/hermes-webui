"""Bounded liveness checks for paths on network/FUSE mounts.

An SSHFS mount whose host powered off stays in the kernel mount table, and
any stat() under it blocks until sshfs gives up -- minutes with the default
ServerAlive/reconnect settings, forever if the process is stalled. Python
cannot cancel a blocked syscall, so callers on a request thread must ask
here first and skip the filesystem when the mount is not answering.

Each mountpoint gets at most one probe thread at a time: a stuck probe is
reused, not stacked, so a dead host costs one parked thread, not one per
request. A responsive result is cached briefly; an unresponsive one lasts
until the stuck probe returns, after which the next check probes again.
"""
import os
import threading
import time

MOUNTS_FILE = "/proc/self/mounts"
PROBE_TIMEOUT_S = 1.5
OK_CACHE_S = 5.0

# Filesystems whose stat() can block on a remote peer. Local disks, tmpfs and
# WSL's 9p drives answer from the local kernel and are never probed.
_REMOTE_FSTYPES = ("fuse.sshfs", "sshfs", "nfs", "nfs4", "cifs", "smb3", "smbfs")

_lock = threading.Lock()
_probes: dict[str, dict] = {}


def _reset_for_tests() -> None:
    with _lock:
        _probes.clear()


def _remote_mountpoints() -> list[str]:
    points = []
    try:
        with open(MOUNTS_FILE, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3 or parts[2] not in _REMOTE_FSTYPES:
                    continue
                # Mount points are octal-escaped in /proc (space -> \040).
                points.append(parts[1].encode("utf-8", "replace").decode("unicode_escape"))
    except OSError:
        return []
    return points


def remote_mount_for(path) -> str | None:
    """The deepest network/FUSE mountpoint containing *path*, or None.

    Pure string work on an absolute path: never touches the filesystem.
    """
    target = os.path.abspath(str(path))
    best = None
    for point in _remote_mountpoints():
        root = point.rstrip("/") or "/"
        if target == root or target.startswith(root + "/"):
            if best is None or len(root) > len(best):
                best = root
    return best


def mount_responsive(mountpoint: str) -> bool:
    """True if a stat() of *mountpoint* returns within PROBE_TIMEOUT_S."""
    now = time.monotonic()
    with _lock:
        probe = _probes.get(mountpoint)
        if probe and probe["done"].is_set() and now - probe["at"] < OK_CACHE_S and probe["ok"]:
            return True
        if not probe or probe["done"].is_set():
            probe = {"done": threading.Event(), "ok": False, "at": now, "started": now}
            _probes[mountpoint] = probe

            def _run(p=probe):
                try:
                    os.stat(mountpoint)
                except OSError:
                    # An error answer (e.g. ENOTCONN) fails fast: not hung.
                    pass
                p["ok"] = True
                p["at"] = time.monotonic()
                p["done"].set()

            threading.Thread(target=_run, name="mount-probe", daemon=True).start()
    # Only a fresh probe is waited on; one already past its budget is a known
    # hang, and waiting on it again would cost every caller the full timeout.
    probe["done"].wait(max(0.0, PROBE_TIMEOUT_S - (now - probe["started"])))
    return probe["done"].is_set()


def path_unresponsive(path) -> bool:
    """True only if *path* sits on a network/FUSE mount that is not answering."""
    mountpoint = remote_mount_for(path)
    return mountpoint is not None and not mount_responsive(mountpoint)
