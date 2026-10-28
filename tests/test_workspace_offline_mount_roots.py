"""An offline remote workspace (dropped SSHFS mount) must not break trust checks for other paths.

Live failure: with the Raspberry Pi off, /api/list for a chat whose workspace folder was missing
returned 500, because building the trusted-root list stat'ed the saved Pi workspace and exists()
raised ENOTCONN instead of returning False.
"""
import errno
from pathlib import Path

import api.workspace as ws


def test_a_dropped_mount_is_skipped_instead_of_raising(tmp_path, monkeypatch):
    dead = tmp_path / "remote" / "raspberry-pi-5"
    dead.mkdir(parents=True)
    good = tmp_path / "projects"
    (good / "app").mkdir(parents=True)
    monkeypatch.setattr(ws, "load_workspaces", lambda: [{"path": str(dead)}, {"path": str(good)}])
    real_exists = Path.exists

    def exists(self, *args, **kwargs):
        if self == dead:
            raise OSError(errno.ENOTCONN, "Transport endpoint is not connected", str(self))
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", exists)
    roots = ws._trusted_workspace_roots()
    assert dead not in roots and good.resolve() in roots
    # A missing folder under a reachable saved root is still trusted (created later by the agent).
    assert ws._candidate_under_trusted_roots((good / "app" / "not-yet").resolve())


def test_a_hung_mount_is_not_stat_ed(tmp_path, monkeypatch):
    hung = tmp_path / "hung"
    hung.mkdir()
    monkeypatch.setattr(ws, "load_workspaces", lambda: [{"path": str(hung)}])
    monkeypatch.setattr(ws, "_mount_unresponsive", lambda p: Path(p) == hung.resolve())
    real_exists = Path.exists

    def exists(self, *args, **kwargs):
        assert self != hung.resolve(), "a stat on an unresponsive mount would block the request"
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", exists)
    assert hung.resolve() not in ws._trusted_workspace_roots()
