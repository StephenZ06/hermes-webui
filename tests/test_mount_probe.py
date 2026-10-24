"""A remote workspace whose host stops answering must not hang the server.

An SSHFS mount whose host powered off keeps the mountpoint in the kernel
table, and every stat() under it blocks until sshfs gives up -- for minutes,
or forever while the process is stalled. Workspace listing, last-workspace
lookup and the session list all stat those paths on the request thread, so
the browser saw "Request timed out" on boot.
"""
import os
import threading
import time
from pathlib import Path

import pytest

from api import mount_probe


@pytest.fixture
def hung_mount(tmp_path, monkeypatch):
    """A fake sshfs mountpoint whose stat() never returns until released."""
    mountpoint = tmp_path / "remote" / "rp5"
    mountpoint.mkdir(parents=True)
    mounts = tmp_path / "mounts"
    mounts.write_text(
        "proc /proc proc rw 0 0\n"
        f"zola@host:/home/zola {mountpoint} fuse.sshfs rw,nosuid 0 0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mount_probe, "MOUNTS_FILE", str(mounts))
    monkeypatch.setattr(mount_probe, "PROBE_TIMEOUT_S", 0.3)
    mount_probe._reset_for_tests()

    release = threading.Event()
    real_stat = os.stat
    calls = {"n": 0}

    def fake_stat(path, *args, **kwargs):
        if str(path).startswith(str(mountpoint)):
            calls["n"] += 1
            release.wait(10)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", fake_stat)
    yield mountpoint, calls
    release.set()
    mount_probe._reset_for_tests()


def _timed(fn):
    start = time.monotonic()
    result = fn()
    return result, time.monotonic() - start


def test_unresponsive_mount_is_detected_within_the_probe_budget(hung_mount):
    mountpoint, _ = hung_mount
    result, elapsed = _timed(lambda: mount_probe.path_unresponsive(mountpoint / "proj"))
    assert result is True
    assert elapsed < 1.5


def test_repeated_checks_reuse_the_one_stuck_probe(hung_mount):
    mountpoint, calls = hung_mount
    assert mount_probe.path_unresponsive(mountpoint) is True
    start = time.monotonic()
    for _ in range(5):
        assert mount_probe.path_unresponsive(mountpoint) is True
    # A known hang answers at once instead of re-waiting the probe budget.
    assert time.monotonic() - start < 0.1
    assert calls["n"] == 1


def test_local_paths_are_never_probed(hung_mount, tmp_path):
    assert mount_probe.path_unresponsive(tmp_path) is False


def test_ssh_mount_status_reports_a_hung_mount_disconnected_quickly(hung_mount):
    from api.ssh_mount import mount_status

    mountpoint, _ = hung_mount
    result, elapsed = _timed(lambda: mount_status({"path": str(mountpoint)}))
    assert result == "disconnected"
    assert elapsed < 1.5


def test_workspace_resolve_and_availability_do_not_block(hung_mount):
    from api.workspace import _safe_resolve, workspace_availability

    mountpoint, _ = hung_mount
    resolved, elapsed = _timed(lambda: _safe_resolve(mountpoint / "proj"))
    assert resolved == mountpoint / "proj"
    assert elapsed < 1.5
    avail, elapsed = _timed(lambda: workspace_availability({"path": str(mountpoint / "proj")}))
    assert avail == "offline"
    assert elapsed < 1.5


def test_last_workspace_on_a_hung_mount_falls_back_without_blocking(hung_mount, monkeypatch, tmp_path):
    from api import workspace

    mountpoint, _ = hung_mount
    lw = tmp_path / "last_workspace.txt"
    lw.write_text(str(mountpoint / "proj"), encoding="utf-8")
    monkeypatch.setattr(workspace, "_last_workspace_file", lambda: lw)
    monkeypatch.setattr(workspace, "_GLOBAL_LW_FILE", tmp_path / "missing.txt")
    monkeypatch.setattr(workspace, "_remote_terminal_cwd", lambda: None)
    monkeypatch.setattr(workspace, "_profile_default_workspace", lambda: str(tmp_path))
    result, elapsed = _timed(workspace.get_last_workspace)
    assert result == str(tmp_path)
    assert elapsed < 1.5
    # The remembered choice is kept for when the host comes back.
    assert lw.read_text(encoding="utf-8") == str(mountpoint / "proj")
