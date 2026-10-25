"""Regression: the chat page's /api/crons/recent poll must not wait on the cron env lock.

The in-process gateway ticker holds ``_cron_env_lock`` for the whole run of a due
job (``cron_tick(sync=True)``), which can take minutes. The poll used
``cron_profile_context()``, which takes the same lock, so every poll during a job
run hung past the client's 30s timeout and the chat page showed
"Request timed out. Please try again." with nothing in the console.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace


class _JSONHandler:
    def __init__(self):
        self.status = None
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        pass

    def end_headers(self):
        pass


def _stub_cron(monkeypatch, *, with_store_override):
    cron_pkg = types.ModuleType("cron")
    cron_pkg.__path__ = []
    cron_jobs = types.ModuleType("cron.jobs")
    cron_jobs.list_jobs = lambda include_disabled=True: [
        {"id": "job1", "name": "graphify-refresh", "last_run_at": 200.0, "last_status": "ok"}
    ]
    stores = []
    if with_store_override:
        @contextlib.contextmanager
        def use_cron_store(home):
            stores.append(Path(home))
            yield

        cron_jobs.use_cron_store = use_cron_store
    monkeypatch.setitem(sys.modules, "cron", cron_pkg)
    monkeypatch.setitem(sys.modules, "cron.jobs", cron_jobs)
    return stores


def _run_route(timeout):
    import api.routes as routes

    handler = _JSONHandler()
    done = threading.Event()

    def call():
        routes._route_get_api_crons_recent(handler, SimpleNamespace(query="since=100"))
        done.set()

    threading.Thread(target=call, daemon=True).start()
    return handler, done.wait(timeout)


def test_recent_poll_answers_while_ticker_holds_the_cron_lock(monkeypatch):
    import api.profiles as profiles
    import api.routes as routes

    monkeypatch.setattr(routes, "_ensure_agent_cron_import_path", lambda: None)
    stores = _stub_cron(monkeypatch, with_store_override=True)

    # Simulate the ticker mid-way through a long due-job run.
    profiles._cron_env_lock.acquire()
    try:
        handler, finished = _run_route(timeout=3)
    finally:
        profiles._cron_env_lock.release()

    assert finished, "poll blocked on _cron_env_lock while a cron job was running"
    assert handler.status == 200
    body = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert [c["job_id"] for c in body["completions"]] == ["job1"]
    # The store is pinned to the request's profile home, not left to process globals.
    assert stores == [Path(profiles.get_active_hermes_home())]


def test_recent_poll_falls_back_to_the_locked_context_on_older_agents(monkeypatch):
    import api.profiles as profiles
    import api.routes as routes

    monkeypatch.setattr(routes, "_ensure_agent_cron_import_path", lambda: None)
    _stub_cron(monkeypatch, with_store_override=False)

    profiles._cron_env_lock.acquire()
    try:
        _, finished_while_locked = _run_route(timeout=0.5)
    finally:
        profiles._cron_env_lock.release()

    # Without use_cron_store the only safe way to pin the store is the lock.
    assert not finished_while_locked
