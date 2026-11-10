"""Deleting a project the wizard just created stops everything still working
in it (the setup agent, the processes it started, anything else running in
the folder) before the folder and its registry entry are removed. Adopted
projects keep their folder."""

import io
import json
import os
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from api import project_cleanup, project_starter, project_starter_agent as agent


def _sleeper(cwd: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=str(cwd))


def _gone(proc: subprocess.Popen, timeout: float = 5.0) -> bool:
    try:
        proc.wait(timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


@pytest.fixture
def procs():
    started = []
    yield started
    for proc in started:
        if proc.poll() is None:
            proc.kill()
            proc.wait(5)


def test_processes_working_in_the_folder_are_stopped_and_others_are_not(tmp_path, procs):
    inside, outside = tmp_path / "proj" / "node_modules", tmp_path / "other"
    inside.mkdir(parents=True)
    outside.mkdir()
    procs += [_sleeper(inside), _sleeper(outside)]
    time.sleep(0.3)
    assert project_cleanup.kill_processes_in(tmp_path / "proj") == 1
    assert _gone(procs[0])
    assert procs[1].poll() is None


def test_stopping_a_setup_job_cancels_its_turn_and_kills_what_it_started(tmp_path, monkeypatch):
    cancelled, killed = [], []
    fake_registry = types.SimpleNamespace(kill_all=lambda task_id, **kw: killed.append((task_id, kw["source"])) or 0)
    monkeypatch.setitem(sys.modules, "tools.process_registry", types.SimpleNamespace(process_registry=fake_registry))
    import api.streaming

    monkeypatch.setattr(api.streaming, "cancel_stream", lambda stream_id: cancelled.append(stream_id) or True)
    release = threading.Event()

    def work(report, on_run):
        on_run("sess-1", "stream-1")
        report("Running npm install")
        release.wait(5)
        raise RuntimeError("Architecture stopped before answering.")

    folder = tmp_path / "shop"
    folder.mkdir()
    job_id = agent._start_job("setup", work, with_progress=True, workspace=str(folder), project_id="p1")
    for _ in range(100):
        if (agent.get_job(job_id) or {}).get("progress"):
            break
        time.sleep(0.02)
    other = agent._start_job("setup", lambda report, on_run: release.wait(5) and {}, with_progress=True,
                             workspace=str(tmp_path / "elsewhere"), project_id="p2")
    stopped = agent.stop_jobs(under=folder)
    assert [s["job_id"] for s in stopped] == [job_id]
    assert cancelled == ["stream-1"] and killed == [("sess-1", "project_deleted")]
    release.set()
    time.sleep(0.2)
    job = agent.get_job(job_id)
    assert job["status"] == "cancelled" and "deleted" in job["error"], job  # the turn's own error does not replace it
    assert "session_id" not in job and "workspace" not in job
    assert agent.get_job(other)["status"] != "cancelled"


def test_the_registry_entry_is_removed_and_the_rest_of_the_file_is_untouched(tmp_path):
    registry = tmp_path / "WORKSPACES.yaml"
    keep = ("projects:\n"
            "  hermes:\n    display_name: \"Hermes\"\n    access_mode: local\n    repo_path: \"/srv/hermes\"\n")
    registry.write_text(keep, encoding="utf-8")
    shop = tmp_path / "shop"
    shop.mkdir()
    key = project_starter.register_in_lifecycle_registry("Shop", shop, registry_file=registry)
    other = tmp_path / "blog"
    other.mkdir()
    project_starter.register_in_lifecycle_registry("Blog", other, registry_file=registry)
    before = registry.read_text(encoding="utf-8")
    assert not project_starter.unregister_from_lifecycle_registry(key, other, registry_file=registry)  # wrong path: kept
    assert project_starter.unregister_from_lifecycle_registry(key, shop, registry_file=registry)
    after = registry.read_text(encoding="utf-8")
    assert key not in after and "Blog" in after and after.startswith(keep)
    assert len(after.splitlines()) == len(before.splitlines()) - 5


class _Handler:
    def __init__(self):
        self.status, self.sent, self.wfile = None, [], io.BytesIO()
        self.headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.sent.append((key, value))

    def end_headers(self):
        pass


def _delete_route(monkeypatch, tmp_path, project):
    import api.routes as routes
    from api import work_hub

    store = {"projects": [project]}
    registry = tmp_path / "WORKSPACES.yaml"
    project["registry_key"] = project_starter.register_in_lifecycle_registry(project["name"], Path(project["workspace_path"]),
                                                                            registry_file=registry)
    real_unregister = project_starter.unregister_from_lifecycle_registry
    monkeypatch.setattr(project_starter, "unregister_from_lifecycle_registry",
                        lambda key, path, registry_file=None: real_unregister(key, path, registry_file=registry))
    monkeypatch.setattr(routes, "load_projects", lambda **_kw: [dict(p) for p in store["projects"]])
    monkeypatch.setattr(routes, "save_projects", lambda rows: store.update(projects=list(rows)))
    monkeypatch.setattr(routes, "_reassign_project_sessions", lambda ids, new: 0)
    monkeypatch.setattr(routes, "_arm_project_lifecycle_for_mutation", lambda: None)
    monkeypatch.setattr(work_hub, "deletable_project_ids", lambda rows: {p["project_id"] for p in rows})
    monkeypatch.setattr(work_hub, "delete_project_contents", lambda pid: None)
    handler = _Handler()
    routes._route_post_api_projects_delete(handler, None, {"project_id": project["project_id"], "delete_folder": True}, None)
    return handler, store, registry


def test_deleting_a_wizard_project_stops_its_work_and_removes_its_folder_and_entry(tmp_path, monkeypatch, procs):
    folder = tmp_path / "shop"
    (folder / "src").mkdir(parents=True)
    (folder / "AGENTS.md").write_text("x", encoding="utf-8")
    procs.append(_sleeper(folder / "src"))
    time.sleep(0.3)
    project = {"project_id": "p1", "name": "Shop", "workspace_path": str(folder), "created_folder": True}
    handler, store, registry = _delete_route(monkeypatch, tmp_path, project)
    assert handler.status == 200, handler.wfile.getvalue()
    assert json.loads(handler.wfile.getvalue())["folder_deleted"] is True
    assert not folder.exists() and _gone(procs[0])
    assert store["projects"] == [] and "Shop" not in registry.read_text(encoding="utf-8")


def test_deleting_an_adopted_project_keeps_its_folder(tmp_path, monkeypatch):
    folder = tmp_path / "mine"
    folder.mkdir()
    (folder / "notes.md").write_text("mine", encoding="utf-8")
    project = {"project_id": "p2", "name": "Mine", "workspace_path": str(folder)}
    handler, store, registry = _delete_route(monkeypatch, tmp_path, project)
    assert handler.status == 200
    assert json.loads(handler.wfile.getvalue())["folder_deleted"] is False
    assert (folder / "notes.md").read_text(encoding="utf-8") == "mine"
    assert store["projects"] == [] and "Mine" in registry.read_text(encoding="utf-8")


def test_deleting_the_folder_on_the_files_page_stops_its_work_and_drops_the_project(tmp_path, monkeypatch, procs):
    import api.models
    import api.routes as routes
    from api import file_manager, work_hub

    folder = tmp_path / "shop"
    folder.mkdir()
    procs.append(_sleeper(folder))
    time.sleep(0.3)
    store = {"projects": [{"project_id": "p1", "name": "Shop", "workspace_path": str(folder), "created_folder": True},
                          {"project_id": "p3", "name": "Kept", "workspace_path": str(tmp_path / "kept")}]}
    monkeypatch.setattr(api.models, "load_projects", lambda **_kw: [dict(p) for p in store["projects"]])
    monkeypatch.setattr(api.models, "save_projects", lambda rows: store.update(projects=list(rows)))
    monkeypatch.setattr(routes, "_reassign_project_sessions", lambda ids, new: 0)
    monkeypatch.setattr(work_hub, "deletable_project_ids", lambda rows: {p["project_id"] for p in rows})
    monkeypatch.setattr(work_hub, "delete_project_contents", lambda pid: None)
    monkeypatch.setattr(file_manager, "resolve_file_manager_workspace", lambda wid: {"root": str(tmp_path)})
    monkeypatch.setattr(file_manager, "_local_context", lambda ctx: Path(ctx["root"]))
    monkeypatch.setattr(file_manager, "_local_target", lambda ctx, path: (Path(ctx["root"]) / path, path))
    assert file_manager.delete_path("w", "shop", recursive=True)["ok"]
    assert not folder.exists() and _gone(procs[0])
    assert [p["project_id"] for p in store["projects"]] == ["p3"]
