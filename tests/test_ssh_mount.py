import subprocess

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
