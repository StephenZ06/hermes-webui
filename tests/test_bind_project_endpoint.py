"""Live-endpoint coverage for POST /api/session/bind_project and
GET /api/workspaces/registry.

Binds a chat to a WORKSPACES.yaml project: the endpoint must only accept
known, available registry keys, must lock session.workspace to the
project's repo_path for local projects, and must let a chat be unbound
again by passing project_key: null.

The test server runs in a separate subprocess (see tests/conftest.py), so
fixtures can't monkeypatch api.project_registry in-process. Instead, this
writes a real WORKSPACES.yaml to the exact path the subprocess resolves
(api.project_registry.WORKSPACES_REGISTRY_FILE — which honors the same
HERMES_HOME env var the test subprocess uses) and relies on the module
reading it fresh on every call (no caching).
"""
import json
import urllib.error
import urllib.request

import pytest
import yaml

from api.project_registry import WORKSPACES_REGISTRY_FILE

from tests._pytest_port import BASE


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read()), r.status


def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
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


def test_registry_endpoint_returns_written_projects(tmp_path):
    repo = tmp_path / "job-os"
    repo.mkdir()
    _write_registry({
        "job-os": {
            "repo_path": str(repo),
            "access_mode": "local",
            "status": "confirmed project root",
        }
    })

    d, status = get("/api/workspaces/registry")

    assert status == 200, d
    assert [p["key"] for p in d["projects"]] == ["job-os"]
    assert d["projects"][0]["available"] is True


def test_bind_project_locks_local_workspace_to_repo_path(tmp_path):
    repo = tmp_path / "job-os"
    repo.mkdir()
    _write_registry({
        "job-os": {
            "repo_path": str(repo),
            "access_mode": "local",
            "status": "confirmed project root",
        }
    })
    sid = _new_session()

    d, status = post("/api/session/bind_project", {"session_id": sid, "project_key": "job-os"})

    assert status == 200, d
    assert d["session"]["bound_project_key"] == "job-os"
    assert d["session"]["workspace"] == str(repo.resolve())


def test_bind_project_rejects_unknown_key():
    _write_registry({})
    sid = _new_session()

    d, status = post("/api/session/bind_project", {"session_id": sid, "project_key": "nope"})

    assert status == 400, d
    assert "Unknown project" in d.get("error", "")


def test_bind_project_rejects_unavailable_project():
    _write_registry({
        "candidate": {
            "repo_path": "NEEDS_CONFIRMATION",
            "access_mode": "local",
            "status": "candidate directory is empty; project root not confirmed",
        }
    })
    sid = _new_session()

    d, status = post("/api/session/bind_project", {"session_id": sid, "project_key": "candidate"})

    assert status == 400, d
    assert "unavailable" in d.get("error", "").lower()


def test_bind_project_then_unbind_is_rejected(tmp_path):
    # Once bound, unbinding is disallowed (by design) — a chat's project
    # context stays fixed for its lifetime rather than reverting. This is a
    # server-side guard, not just a UI restriction (the WebUI hides the
    # "Unbound" option once bound, but a direct API call must be rejected
    # too, e.g. from a stale client).
    repo = tmp_path / "job-os"
    repo.mkdir()
    _write_registry({
        "job-os": {
            "repo_path": str(repo),
            "access_mode": "local",
            "status": "confirmed project root",
        }
    })
    sid = _new_session()
    post("/api/session/bind_project", {"session_id": sid, "project_key": "job-os"})

    d, status = post("/api/session/bind_project", {"session_id": sid, "project_key": None})

    assert status == 400, d
    after, _ = get(f"/api/session?session_id={sid}")
    assert after["session"]["bound_project_key"] == "job-os"
    assert after["session"]["workspace"] == str(repo.resolve())


def test_rebind_chain_to_different_project_still_allowed_then_unbind_rejected(tmp_path):
    repo_a = tmp_path / "project-a"
    repo_a.mkdir()
    repo_b = tmp_path / "project-b"
    repo_b.mkdir()
    _write_registry({
        "project-a": {"repo_path": str(repo_a), "access_mode": "local", "status": "confirmed project root"},
        "project-b": {"repo_path": str(repo_b), "access_mode": "local", "status": "confirmed project root"},
    })
    sid = _new_session()
    post("/api/session/bind_project", {"session_id": sid, "project_key": "project-a"})
    # Rebinding to a DIFFERENT project is still allowed — only the
    # bound -> unbound transition is blocked.
    d_b, status_b = post("/api/session/bind_project", {"session_id": sid, "project_key": "project-b"})
    assert status_b == 200, d_b
    assert d_b["session"]["workspace"] == str(repo_b.resolve())

    d, status = post("/api/session/bind_project", {"session_id": sid, "project_key": None})

    assert status == 400, d
    after, _ = get(f"/api/session?session_id={sid}")
    assert after["session"]["bound_project_key"] == "project-b"


def test_bind_project_missing_session_id_is_400():
    d, status = post("/api/session/bind_project", {"project_key": "job-os"})

    assert status == 400, d


def test_bind_project_unknown_session_is_404():
    _write_registry({
        "job-os": {
            "repo_path": "/tmp",
            "access_mode": "local",
            "status": "confirmed project root",
        }
    })

    d, status = post("/api/session/bind_project", {"session_id": "does-not-exist", "project_key": "job-os"})

    assert status == 404, d
