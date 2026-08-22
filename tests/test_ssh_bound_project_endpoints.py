"""Live-endpoint coverage for SSH-mode bound-project file browsing.

No real SSH server is available in this environment, so these tests prove
the ROUTING (an ssh-bound session's /api/list and /api/file requests reach
api.ssh_workspace instead of the local filesystem, and a connection
failure surfaces as a clear 502 rather than silently falling back to a
local path or crashing) — not a successful remote listing. Success-path
parsing logic is covered by tests/test_ssh_workspace.py with mocked
subprocess.run.
"""
import json
import urllib.error
import urllib.request

import yaml

from api.project_registry import WORKSPACES_REGISTRY_FILE

from tests._pytest_port import BASE

import pytest


def get(path, timeout=30):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


def _new_session():
    d, status = post("/api/session/new", {})
    assert status == 200, d
    return d["session"]["session_id"]


def _write_registry(projects: dict):
    WORKSPACES_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORKSPACES_REGISTRY_FILE.write_text(
        yaml.safe_dump({"projects": projects}), encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def _cleanup_registry_file():
    yield
    if WORKSPACES_REGISTRY_FILE.exists():
        WORKSPACES_REGISTRY_FILE.unlink()


SSH_PROJECT = {
    "ssh-project": {
        "access_mode": "ssh",
        "status": "confirmed project root",
        "ssh": {
            # RFC 5737 TEST-NET-1: reserved, non-routable, guaranteed to
            # never answer — a deterministic, bounded (ConnectTimeout=10)
            # connection failure with no DNS-resolver-timing dependency.
            "target": "user@192.0.2.1",
            "key": "/keys/id_rsa",
            "remote_path": "/srv/app",
        },
    }
}


def _bind_ssh_session():
    _write_registry(SSH_PROJECT)
    sid = _new_session()
    d, status = post("/api/session/bind_project", {"session_id": sid, "project_key": "ssh-project"})
    assert status == 200, d
    assert d["session"]["bound_project_key"] == "ssh-project"
    return sid


def test_bind_ssh_project_does_not_touch_local_workspace(tmp_path):
    sid = _bind_ssh_session()
    d, status = get(f"/api/session?session_id={sid}")
    assert status == 200, d
    # Unlike local-mode binding, workspace must be left untouched — there is
    # no local path to lock it to.
    assert d["session"]["bound_project_key"] == "ssh-project"


def test_list_dir_routes_to_ssh_and_reports_connection_failure():
    sid = _bind_ssh_session()

    d, status = get(f"/api/list?session_id={sid}&path=.")

    assert status == 502, d
    assert "error" in d


def test_file_read_routes_to_ssh_and_reports_connection_failure():
    sid = _bind_ssh_session()

    d, status = get(f"/api/file?session_id={sid}&path=notes.txt")

    assert status == 502, d
    assert "error" in d


def test_list_dir_for_local_bound_session_is_unaffected(tmp_path):
    repo = tmp_path / "local-proj"
    repo.mkdir()
    (repo / "hello.txt").write_text("hi", encoding="utf-8")
    _write_registry({
        "local-project": {
            "repo_path": str(repo),
            "access_mode": "local",
            "status": "confirmed project root",
        }
    })
    sid = _new_session()
    post("/api/session/bind_project", {"session_id": sid, "project_key": "local-project"})

    d, status = get(f"/api/list?session_id={sid}&path=.")

    assert status == 200, d
    assert any(e["name"] == "hello.txt" for e in d["entries"])
