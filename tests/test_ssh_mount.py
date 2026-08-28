import subprocess
from pathlib import Path

import pytest

import api.ssh_mount as ssh_mount
from api.ssh_mount import SshMountError, mount_remote, mount_status, reconnect_all_on_boot, unmount_remote


def _entry(path, **remote_overrides):
    remote = {"host": "pi@192.168.1.50", "remote_path": "/home/pi/projects", "key_path": "/keys/id_rsa"}
    remote.update(remote_overrides)
    return {"path": str(path), "name": "Raspberry Pi 5", "kind": "remote", "remote": remote}


def _dispatched_run(handlers):
    """handlers: {argv[0]: fn(cmd) -> CompletedProcess}."""
    def _run(cmd, capture_output, timeout):
        fn = handlers.get(cmd[0])
        if fn is None:
            raise AssertionError(f"unexpected command: {cmd}")
        return fn(cmd)
    return _run


def test_mount_remote_incomplete_config_raises(tmp_path):
    entry = {"path": str(tmp_path / "x"), "name": "bad", "kind": "remote", "remote": {"host": "h"}}
    with pytest.raises(SshMountError, match="Incomplete remote config"):
        mount_remote(entry)


def test_mount_remote_success(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    entry = _entry(mountpoint)
    calls = []

    def _mountpoint_check(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1)  # not yet mounted

    def _sshfs(cmd):
        calls.append(cmd)
        assert cmd[0] == "sshfs"
        assert "pi@192.168.1.50:/home/pi/projects" in cmd
        assert str(mountpoint) in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", _dispatched_run({"mountpoint": _mountpoint_check, "sshfs": _sshfs}))

    mount_remote(entry)

    assert mountpoint.is_dir()
    # mount_status() short-circuits on a nonexistent path without touching
    # subprocess at all (see test_mount_status_missing_path_is_disconnected)
    # — the mountpoint dir doesn't exist until mount_remote() creates it, so
    # only the actual sshfs call is expected here.
    assert [c[0] for c in calls] == ["sshfs"]


def test_mount_remote_noop_if_already_connected(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)

    def _mountpoint_check(cmd):
        return subprocess.CompletedProcess(cmd, 0)  # already mounted

    def _sshfs(cmd):
        raise AssertionError("sshfs should not be called when already mounted")

    monkeypatch.setattr(subprocess, "run", _dispatched_run({"mountpoint": _mountpoint_check, "sshfs": _sshfs}))

    mount_remote(entry)  # must not raise, must not call sshfs


def test_mount_remote_classifies_failure(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    entry = _entry(mountpoint)

    def _mountpoint_check(cmd):
        return subprocess.CompletedProcess(cmd, 1)

    def _sshfs(cmd):
        return subprocess.CompletedProcess(cmd, 255, stdout=b"", stderr=b"Permission denied")

    monkeypatch.setattr(subprocess, "run", _dispatched_run({"mountpoint": _mountpoint_check, "sshfs": _sshfs}))

    with pytest.raises(SshMountError, match="authentication failed"):
        mount_remote(entry)


def test_mount_remote_timeout(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    entry = _entry(mountpoint)

    def _run(cmd, capture_output, timeout):
        if cmd[0] == "mountpoint":
            return subprocess.CompletedProcess(cmd, 1)
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(subprocess, "run", _run)

    with pytest.raises(SshMountError, match="timed out"):
        mount_remote(entry)


def test_unmount_remote_success(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)
    calls = []

    def _mountpoint_check(cmd):
        return subprocess.CompletedProcess(cmd, 0)  # connected

    def _fusermount(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", _dispatched_run({"mountpoint": _mountpoint_check, "fusermount": _fusermount}))

    unmount_remote(entry)

    assert calls[0] == ["fusermount", "-u", str(mountpoint)]


def test_unmount_remote_lazy_fallback_on_stale_mount(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)
    fusermount_calls = []

    def _mountpoint_check(cmd):
        return subprocess.CompletedProcess(cmd, 0)

    def _fusermount(cmd):
        fusermount_calls.append(cmd)
        # First (clean) unmount fails, as it does on a stale/dead mount;
        # second (lazy, -uz) succeeds.
        rc = 1 if len(fusermount_calls) == 1 else 0
        return subprocess.CompletedProcess(cmd, rc, stderr=b"Transport endpoint not connected")

    monkeypatch.setattr(subprocess, "run", _dispatched_run({"mountpoint": _mountpoint_check, "fusermount": _fusermount}))

    unmount_remote(entry)  # must not raise

    assert fusermount_calls == [
        ["fusermount", "-u", str(mountpoint)],
        ["fusermount", "-uz", str(mountpoint)],
    ]


def test_unmount_remote_noop_if_not_connected(tmp_path, monkeypatch):
    entry = _entry(tmp_path / "never-mounted")

    def _mountpoint_check(cmd):
        return subprocess.CompletedProcess(cmd, 1)

    def _fusermount(cmd):
        raise AssertionError("fusermount should not be called when not connected")

    monkeypatch.setattr(subprocess, "run", _dispatched_run({"mountpoint": _mountpoint_check, "fusermount": _fusermount}))

    unmount_remote(entry)  # must not raise


def test_mount_status_missing_path_is_disconnected(tmp_path):
    entry = _entry(tmp_path / "does-not-exist")
    assert mount_status(entry) == "disconnected"


def test_mount_status_reflects_mountpoint_check(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)

    monkeypatch.setattr(subprocess, "run", lambda cmd, capture_output, timeout: subprocess.CompletedProcess(cmd, 0))
    assert mount_status(entry) == "connected"

    monkeypatch.setattr(subprocess, "run", lambda cmd, capture_output, timeout: subprocess.CompletedProcess(cmd, 1))
    assert mount_status(entry) == "disconnected"


def test_reconnect_all_on_boot_never_raises(tmp_path, monkeypatch):
    local_entry = {"path": str(tmp_path / "local"), "name": "Home"}
    ok_entry = _entry(tmp_path / "ok")
    bad_entry = _entry(tmp_path / "bad", host="")  # incomplete -> SshMountError inside mount_remote

    monkeypatch.setattr(
        "api.workspace.load_workspaces",
        lambda: [local_entry, ok_entry, bad_entry],
    )

    mounted = []

    def _fake_mount_remote(entry):
        if entry is bad_entry:
            raise SshMountError("boom")
        mounted.append(entry["path"])

    monkeypatch.setattr(ssh_mount, "mount_remote", _fake_mount_remote)

    reconnect_all_on_boot()  # must not raise despite bad_entry failing

    assert mounted == [ok_entry["path"]]


# ── Stale FUSE endpoints after a container restart ──────────────────────────
#
# Restarting the container kills the sshfs process but leaves the kernel mount
# behind, so the mountpoint is simultaneously "already mounted" (nothing can
# mount over it) and unusable (every stat fails with EACCES/ENOTCONN). Before
# these cases were handled, mount_status() let the PermissionError propagate,
# which aborted reconnect_all_on_boot() before it could remount -- so a single
# restart made the remote workspace permanently empty.

def _stale_stat(monkeypatch, mountpoint):
    """Make stat() on *mountpoint* fail the way a dead FUSE endpoint does.

    Returns a dict whose "stale" flag the caller can clear, so a test can model
    the real sequence: the path is unreadable until the lazy unmount lands, and
    ordinary again afterwards.
    """
    state = {"stale": True}
    real_stat = Path.stat

    def _fake(self, *a, **kw):
        if state["stale"] and str(self) == str(mountpoint):
            raise PermissionError(13, "Permission denied")
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(Path, "stat", _fake)
    return state


def test_mount_status_does_not_raise_on_a_stale_endpoint(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)
    _stale_stat(monkeypatch, mountpoint)
    assert mount_status(entry) == "disconnected"


def test_stale_endpoint_is_not_reported_as_connected(tmp_path, monkeypatch):
    # It is still a kernel mountpoint, but nothing can read it, so calling it
    # connected would make mount_remote() a no-op and it could never recover.
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)
    _stale_stat(monkeypatch, mountpoint)
    monkeypatch.setattr(
        subprocess, "run",
        _dispatched_run({"mountpoint": lambda cmd: subprocess.CompletedProcess(cmd, 0)}),
    )
    assert mount_status(entry) == "disconnected"


def test_mount_remote_lazily_clears_a_stale_endpoint_first(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)
    state = _stale_stat(monkeypatch, mountpoint)
    calls = []

    def _mountpoint_check(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)  # kernel still lists it

    def _fusermount(cmd):
        calls.append(cmd)
        state["stale"] = False  # the endpoint is readable again once cleared
        return subprocess.CompletedProcess(cmd, 0)

    def _sshfs(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", _dispatched_run({
        "mountpoint": _mountpoint_check,
        "fusermount": _fusermount,
        "sshfs": _sshfs,
    }))

    mount_remote(entry)

    names = [c[0] for c in calls]
    assert "fusermount" in names, "a stale endpoint must be lazily unmounted"
    assert names.index("fusermount") < names.index("sshfs"), "clear before mounting"
    lazy = next(c for c in calls if c[0] == "fusermount")
    assert "-uz" in lazy, "a plain unmount cannot clear a stale endpoint"


def test_a_healthy_mount_is_never_lazily_unmounted(tmp_path, monkeypatch):
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)
    calls = []
    monkeypatch.setattr(subprocess, "run", _dispatched_run({
        "mountpoint": lambda cmd: (calls.append(cmd), subprocess.CompletedProcess(cmd, 0))[1],
        "fusermount": lambda cmd: (calls.append(cmd), subprocess.CompletedProcess(cmd, 0))[1],
    }))
    mount_remote(entry)  # already connected -> no-op
    assert not any(c[0] == "fusermount" for c in calls)


def test_missing_mountpoint_is_not_probed_for_a_stale_mount(tmp_path, monkeypatch):
    # Nothing to clear when the directory does not exist at all; probing would
    # just add a subprocess call on every first-time mount.
    from api.ssh_mount import _clear_stale_mountpoint

    calls = []
    monkeypatch.setattr(subprocess, "run", _dispatched_run({
        "mountpoint": lambda cmd: (calls.append(cmd), subprocess.CompletedProcess(cmd, 1))[1],
    }))
    assert _clear_stale_mountpoint(tmp_path / "does-not-exist") is False
    assert calls == []


def test_reconnect_all_on_boot_survives_a_stale_endpoint(tmp_path, monkeypatch):
    # The regression that made this permanent: mount_status() raised before
    # any mount was attempted, so the reconcile aborted on every boot.
    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    entry = _entry(mountpoint)
    state = _stale_stat(monkeypatch, mountpoint)
    monkeypatch.setattr("api.workspace.load_workspaces", lambda: [entry])
    sshfs_calls = []

    def _fusermount(cmd):
        state["stale"] = False
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", _dispatched_run({
        "mountpoint": lambda cmd: subprocess.CompletedProcess(cmd, 0),
        "fusermount": _fusermount,
        "sshfs": lambda cmd: (sshfs_calls.append(cmd), subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b""))[1],
    }))
    reconnect_all_on_boot()
    assert sshfs_calls, "boot reconcile must still attempt the remount"


def test_proc_mounts_detects_a_mount_mountpoint_cannot_see(tmp_path, monkeypatch):
    # The real failure: `mountpoint -q` stats the path to answer, so on a dead
    # FUSE endpoint it reports "not a mountpoint" and the stale mount was never
    # cleared. /proc is a plain string compare and still lists it.
    from api.ssh_mount import _is_stale_mountpoint

    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    _stale_stat(monkeypatch, mountpoint)
    monkeypatch.setattr(
        subprocess, "run",
        _dispatched_run({"mountpoint": lambda cmd: subprocess.CompletedProcess(cmd, 1)}),
    )
    monkeypatch.setattr(ssh_mount, "_proc_lists_mount", lambda p: str(p) == str(mountpoint))
    assert _is_stale_mountpoint(mountpoint) is True


def test_proc_mounts_parses_the_mount_point_column(tmp_path, monkeypatch):
    from api.ssh_mount import _proc_lists_mount

    proc = tmp_path / "mounts"
    proc.write_text(
        "proc /proc proc rw,relatime 0 0\n"
        "zola@10.0.0.5:/home/zola /workspace/remote/raspberry-pi-5 fuse.sshfs rw 0 0\n",
        encoding="utf-8",
    )
    real_open = open

    def _fake_open(path, *a, **kw):
        if str(path) == "/proc/self/mounts":
            return real_open(proc, *a, **kw)
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", _fake_open)
    assert _proc_lists_mount("/workspace/remote/raspberry-pi-5") is True
    assert _proc_lists_mount("/workspace/remote/raspberry-pi-5/") is True
    assert _proc_lists_mount("/workspace/remote") is False
    # The source column must never be mistaken for the mount point.
    assert _proc_lists_mount("zola@10.0.0.5:/home/zola") is False


def test_a_usable_path_is_never_treated_as_stale(tmp_path):
    from api.ssh_mount import _is_stale_mountpoint

    mountpoint = tmp_path / "pi5"
    mountpoint.mkdir()
    assert _is_stale_mountpoint(mountpoint) is False
