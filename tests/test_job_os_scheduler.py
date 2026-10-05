"""Scout schedule: off by default, runs the most overdue enabled search."""

from __future__ import annotations

import pytest

from api import profiles
from api.job_os import scheduler, scout
from api.job_os.db import connect_job_os
from api.job_os.settings import save_settings


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)


def _set_last_run(search_id, when):
    conn = connect_job_os()
    conn.execute("UPDATE searches SET last_run_at=? WHERE id=?", (when, search_id))
    conn.commit()
    conn.close()


def test_nothing_runs_while_the_schedule_is_off(store):
    scout.create_search({"keywords": "backend"})
    assert scheduler.tick(start=lambda *a, **k: pytest.fail("must not start")) is None


def test_the_most_overdue_enabled_search_runs_and_only_one_per_tick(store):
    save_settings({"scout": {"enabled": True, "schedule_hours": 6}}, expected_revision=0)
    fresh = scout.create_search({"keywords": "fresh"})
    old = scout.create_search({"keywords": "old"})
    older = scout.create_search({"keywords": "older"})
    off = scout.create_search({"keywords": "off", "enabled": False})
    now = 1_000_000
    _set_last_run(fresh["id"], now - 3600)
    _set_last_run(old["id"], now - 7 * 3600)
    _set_last_run(older["id"], now - 9 * 3600)
    _set_last_run(off["id"], now - 99 * 3600)
    started = []
    assert scheduler.tick(now=now, start=lambda sid, trigger: started.append((sid, trigger))) == older["id"]
    assert started == [(older["id"], "schedule")]


def test_next_run_time_follows_the_interval(store):
    settings = {"scout": {"enabled": True, "schedule_hours": 4}}
    assert scheduler.next_run_at({"enabled": True, "last_run_at": 100}, settings) == 100 + 4 * 3600
    assert scheduler.next_run_at({"enabled": False, "last_run_at": 100}, settings) is None
    assert scheduler.next_run_at({"enabled": True, "last_run_at": 100}, {"scout": {"enabled": False}}) is None
