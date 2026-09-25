import json
import io
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import api.routes as routes


class _Handler:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.wfile = self
        self.body = bytearray()

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    def write(self, data):
        self.body.extend(data)


def _write_ledger(home, rows):
    cron = home / "cron"
    cron.mkdir(parents=True)
    (cron / "runtime-jobs.json").write_text(json.dumps({
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "jobs": rows,
    }), encoding="utf-8")


def test_scheduled_task_reader_keeps_only_valid_rows_for_profile(tmp_path):
    from api.scheduled_tasks import load_scheduled_tasks

    _write_ledger(tmp_path, [
        {"job_id": "script-1", "name": "Backup", "mode": "script", "started_at": "2026-09-20T00:00:00+00:00", "profile": "business"},
        {"job_id": "foreign", "name": "Foreign", "mode": "agent", "started_at": "2026-09-20T00:00:00+00:00", "profile": "other"},
        {"job_id": "bad", "name": "Bad", "mode": "unknown", "started_at": "2026-09-20T00:00:00+00:00", "profile": "business"},
    ])

    assert load_scheduled_tasks(tmp_path, "business") == [{
        "job_id": "script-1", "name": "Backup", "mode": "script",
        "started_at": "2026-09-20T00:00:00+00:00", "profile": "business", "status": "running",
    }]


def test_scheduled_task_reader_fails_closed_for_malformed_ledger(tmp_path):
    from api.scheduled_tasks import load_scheduled_tasks

    cron = tmp_path / "cron"
    cron.mkdir()
    (cron / "runtime-jobs.json").write_text("not-json", encoding="utf-8")

    assert load_scheduled_tasks(tmp_path, "business") == []


def test_scheduled_task_reader_preserves_recent_completed_task_status(tmp_path):
    from api.scheduled_tasks import validate_scheduled_tasks

    rows = validate_scheduled_tasks([
        {"job_id": "brief-1", "name": "Daily brief", "mode": "agent",
         "started_at": "2026-09-20T00:00:00+00:00", "completed_at": "2026-09-20T00:01:00+00:00",
         "status": "completed", "profile": "business"},
    ], "business")

    assert rows[0]["status"] == "completed"
    assert rows[0]["completed_at"] == "2026-09-20T00:01:00+00:00"


def test_office_projection_uses_the_terminal_scheduled_task_status():
    source = (Path(__file__).parents[1] / "static" / "office" / "index.js").read_text(encoding="utf-8")
    assert "status: task.status || 'running'" in source


def test_office_scheduled_tasks_route_uses_active_profile(monkeypatch):
    import api.profiles as profiles
    import api.gateway_chat as gateway_chat

    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "business")
    monkeypatch.setattr(gateway_chat, "gateway_subagents_request", lambda *_args: {"tasks": [
        {"job_id": "script-1", "name": "Backup", "mode": "script",
         "started_at": "2026-09-20T00:00:00+00:00", "profile": "business"}
    ]})
    handler = _Handler()

    routes.handle_get(handler, urlparse("http://example.com/api/office/scheduled-tasks"))

    assert handler.status == 200
    assert json.loads(handler.body)["tasks"][0]["job_id"] == "script-1"


def test_office_scheduled_tasks_route_reads_the_authenticated_gateway(monkeypatch):
    import api.gateway_chat as gateway_chat
    import api.profiles as profiles

    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "business")
    monkeypatch.setattr(gateway_chat, "gateway_subagents_request", lambda method, path: {
        "tasks": [{"job_id": "agent-1", "name": "Brief", "mode": "agent",
                   "started_at": "2026-09-20T00:00:00+00:00", "profile": "business"}]
    })
    handler = _Handler()

    routes.handle_get(handler, urlparse("http://example.com/api/office/scheduled-tasks"))

    assert handler.status == 200
    assert json.loads(handler.body)["tasks"][0]["job_id"] == "agent-1"


def test_office_scheduled_tasks_route_reads_manual_run_activity_from_profile_home(monkeypatch, tmp_path):
    import api.gateway_chat as gateway_chat
    import api.profiles as profiles
    from api.scheduled_tasks import publish_scheduled_task_finished, publish_scheduled_task_started

    job = {"id": "manual-1", "name": "Manual report", "no_agent": True, "profile": "business"}
    publish_scheduled_task_started(tmp_path, job)
    publish_scheduled_task_finished(tmp_path, "manual-1", success=True)
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "business")
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(gateway_chat, "gateway_subagents_request", lambda *_args: {"tasks": []})
    handler = _Handler()

    routes.handle_get(handler, urlparse("http://example.com/api/office/scheduled-tasks"))

    assert handler.status == 200
    tasks = json.loads(handler.body)["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["job_id"] == "manual-1"
    assert tasks[0]["name"] == "Manual report"
    assert tasks[0]["mode"] == "script"
    assert tasks[0]["profile"] == "business"
    assert tasks[0]["status"] == "completed"
