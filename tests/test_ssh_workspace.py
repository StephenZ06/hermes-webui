import shlex
import subprocess

import pytest

import api.ssh_workspace as ssh_workspace
from api.ssh_workspace import (
    SshWorkspaceError,
    _anchored_remote_path,
    ssh_list_dir,
    ssh_read_file,
)

PROJECT = {
    "key": "remote-project",
    "name": "Remote Project",
    "access_mode": "ssh",
    "ssh": {"target": "user@host", "key": "/keys/id_rsa", "remote_path": "/srv/app"},
}


def _fake_run(stdout=b"", stderr=b"", returncode=0):
    def _run(cmd, capture_output, timeout):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    return _run


def test_anchored_remote_path_joins_under_remote_root():
    assert _anchored_remote_path(PROJECT, ".") == "/srv/app"
    assert _anchored_remote_path(PROJECT, "sub/dir") == "/srv/app/sub/dir"


def test_anchored_remote_path_rejects_traversal():
    with pytest.raises(ValueError):
        _anchored_remote_path(PROJECT, "../etc/passwd")


def test_ssh_base_args_requires_target_and_key():
    with pytest.raises(SshWorkspaceError):
        ssh_workspace._ssh_base_args({"key": "remote-project", "ssh": {"target": "user@host"}})
    with pytest.raises(SshWorkspaceError):
        ssh_workspace._ssh_base_args({"key": "remote-project", "ssh": {"key": "/k"}})


def test_run_remote_raises_on_nonzero_exit(monkeypatch):
    # Raw ssh stderr (which can embed internal hostnames/IPs) is classified
    # into a generic, browser-safe message rather than echoed verbatim —
    # see _classify_ssh_error.
    monkeypatch.setattr(subprocess, "run", _fake_run(stderr=b"Permission denied", returncode=255))

    with pytest.raises(SshWorkspaceError, match="authentication failed"):
        ssh_workspace._run_remote(PROJECT, "ls")


def test_run_remote_raises_on_timeout(monkeypatch):
    def _timeout(cmd, capture_output, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout)
    monkeypatch.setattr(subprocess, "run", _timeout)

    with pytest.raises(SshWorkspaceError, match="timed out"):
        ssh_workspace._run_remote(PROJECT, "ls")


def test_ssh_list_dir_parses_files_and_dirs(monkeypatch):
    output = "sub\td\t4096\t1700000000.0\x00file.txt\tf\t42\t1700000001.5\x00"
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=output.encode()))

    entries = ssh_list_dir(PROJECT, ".")

    by_name = {e["name"]: e for e in entries}
    assert by_name["sub"]["type"] == "dir"
    assert by_name["sub"]["size"] is None
    assert by_name["file.txt"]["type"] == "file"
    assert by_name["file.txt"]["size"] == 42
    assert by_name["file.txt"]["path"] == "file.txt"
    # dirs sort before files
    assert entries[0]["name"] == "sub"


def test_ssh_list_dir_skips_symlinks(monkeypatch):
    output = "link\tl\t0\t1700000000.0\x00real.txt\tf\t10\t1700000000.0\x00"
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=output.encode()))

    entries = ssh_list_dir(PROJECT, ".")

    assert [e["name"] for e in entries] == ["real.txt"]


def test_ssh_list_dir_rejects_path_traversal():
    with pytest.raises(ValueError):
        ssh_list_dir(PROJECT, "../../etc")


def test_ssh_list_dir_command_is_safely_quoted(monkeypatch):
    captured = {}
    def _run(cmd, capture_output, timeout):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
    monkeypatch.setattr(subprocess, "run", _run)

    ssh_list_dir(PROJECT, "sub dir; rm -rf /")

    remote_command = captured["cmd"][-1]
    # The malicious segment must appear only inside a single-quoted argument,
    # never as an unescaped shell operator that `find` would never see.
    assert "; rm -rf" in remote_command
    quoted_target = shlex.split(remote_command)[1]
    assert quoted_target.startswith("/srv/app/sub dir; rm -rf")
    assert not remote_command.rstrip().endswith("rm -rf /")


def test_ssh_read_file_returns_content(monkeypatch):
    calls = []
    def _run(cmd, capture_output, timeout):
        calls.append(cmd[-1])
        if cmd[-1].startswith("stat"):
            return subprocess.CompletedProcess(cmd, 0, stdout=b"11|regular file\n", stderr=b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"hello world", stderr=b"")
    monkeypatch.setattr(subprocess, "run", _run)

    result = ssh_read_file(PROJECT, "notes.txt")

    assert result["content"] == "hello world"
    assert result["size"] == 11
    assert result["path"] == "notes.txt"


def test_ssh_read_file_missing_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=b"MISSING\n"))

    with pytest.raises(SshWorkspaceError, match="not found"):
        ssh_read_file(PROJECT, "nope.txt")


def test_ssh_read_file_rejects_directory(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=b"4096|directory\n"))

    with pytest.raises(SshWorkspaceError, match="Not a regular file"):
        ssh_read_file(PROJECT, "sub")


def test_ssh_read_file_rejects_oversized(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout=b"999999999|regular file\n"))

    with pytest.raises(SshWorkspaceError, match="too large"):
        ssh_read_file(PROJECT, "huge.bin")
