"""Resuming a recurring cron job that still has no next run time is an error.

"Resume and recalculate" on a job in "needs attention" used to answer ok even
when the scheduler could not compute a next run (croniter missing from the
WebUI's Python, or a schedule it cannot read): the job stayed stuck and the
button looked dead. The resume route now reports why instead.
"""
from __future__ import annotations

import io
import json
import sys
import types


class _JSONHandler:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.response_headers = []
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.response_headers.append((key, value))

    def end_headers(self):
        pass


def _payload(handler):
    return json.loads(handler.wfile.getvalue().decode("utf-8"))


def _install_cron(monkeypatch, resume_job):
    cron_pkg = types.ModuleType("cron")
    cron_pkg.__path__ = []
    cron_jobs = types.ModuleType("cron.jobs")
    cron_jobs.resume_job = resume_job
    monkeypatch.setitem(sys.modules, "cron", cron_pkg)
    monkeypatch.setitem(sys.modules, "cron.jobs", cron_jobs)


def test_resume_without_a_next_run_is_reported(monkeypatch):
    import api.routes as routes

    _install_cron(monkeypatch, lambda job_id: {"id": job_id, "enabled": True, "state": "scheduled",
                                               "schedule": {"kind": "cron", "expr": "0 0 * * *"}, "next_run_at": None})
    handler = _JSONHandler()
    routes._handle_cron_resume(handler, {"job_id": "stuck"})
    assert handler.status == 409
    assert "next run" in _payload(handler)["error"]


def test_resume_that_schedules_a_next_run_succeeds(monkeypatch):
    import api.routes as routes

    _install_cron(monkeypatch, lambda job_id: {"id": job_id, "enabled": True, "state": "scheduled",
                                               "schedule": {"kind": "interval", "minutes": 15},
                                               "next_run_at": "2026-10-30T18:00:00+00:00"})
    handler = _JSONHandler()
    routes._handle_cron_resume(handler, {"job_id": "fine"})
    assert handler.status == 200
    assert _payload(handler)["job"]["next_run_at"]


def test_resume_of_an_expired_one_shot_is_a_clear_error(monkeypatch):
    import api.routes as routes

    def refuse(job_id):
        raise ValueError("Cannot resume: one-shot time is in the past")

    _install_cron(monkeypatch, refuse)
    handler = _JSONHandler()
    routes._handle_cron_resume(handler, {"job_id": "once"})
    assert handler.status == 409
    assert "one-shot" in _payload(handler)["error"]
