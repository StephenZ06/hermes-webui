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
    scout.create_search({"keywords": "backend", "country": "my"})
    assert scheduler.tick(start=lambda *a, **k: pytest.fail("must not start")) is None


def test_the_most_overdue_enabled_search_runs_and_only_one_per_tick(store):
    save_settings({"scout": {"enabled": True, "schedule_mode": "interval", "schedule_hours": 6}}, expected_revision=0)
    fresh = scout.create_search({"keywords": "fresh", "country": "my"})
    old = scout.create_search({"keywords": "old", "country": "my"})
    older = scout.create_search({"keywords": "older", "country": "my"})
    off = scout.create_search({"keywords": "off", "country": "my", "enabled": False})
    now = 1_000_000
    _set_last_run(fresh["id"], now - 3600)
    _set_last_run(old["id"], now - 7 * 3600)
    _set_last_run(older["id"], now - 9 * 3600)
    _set_last_run(off["id"], now - 99 * 3600)
    started = []
    assert scheduler.tick(now=now, start=lambda sid, trigger: started.append((sid, trigger))) == older["id"]
    assert started == [(older["id"], "schedule")]


def test_next_run_time_follows_the_interval(store):
    settings = {"scout": {"enabled": True, "schedule_mode": "interval", "schedule_hours": 4}}
    assert scheduler.next_run_at({"enabled": True, "last_run_at": 100}, settings) == 100 + 4 * 3600
    assert scheduler.next_run_at({"enabled": False, "last_run_at": 100}, settings) is None
    assert scheduler.next_run_at({"enabled": True, "last_run_at": 100}, {"scout": {"enabled": False}}) is None


def _myt(text):
    """Epoch seconds for a Malaysia-time wall clock ("2026-10-07 09:00", a Wednesday)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kuala_Lumpur")).timestamp())


TIMES = {"scout": {"enabled": True, "schedule_mode": "times", "run_times": ["12:30", "18:30"], "weekend": "saturday",
                   "quiet_skip": True, "timezone": "Asia/Kuala_Lumpur"}}


def test_runs_follow_the_set_times_in_the_schedules_time_zone(store):
    nxt = lambda last, new=5: scheduler.next_run_at({"enabled": True, "last_run_at": last, "last_new": new}, TIMES)
    assert nxt(_myt("2026-10-07 09:00")) == _myt("2026-10-07 12:30")
    assert nxt(_myt("2026-10-07 12:31")) == _myt("2026-10-07 18:30")
    assert nxt(_myt("2026-10-07 18:31")) == _myt("2026-10-08 12:30")
    # Friday evening -> Saturday's single run -> Monday midday (Sunday is off).
    assert nxt(_myt("2026-10-09 18:31")) == _myt("2026-10-10 12:30")
    assert nxt(_myt("2026-10-10 12:31")) == _myt("2026-10-12 12:30")
    # A quiet run skips the rest of that day.
    assert nxt(_myt("2026-10-07 12:31"), new=1) == _myt("2026-10-08 12:30")
    assert nxt(_myt("2026-10-07 12:31"), new=None) == _myt("2026-10-07 18:30"), "no finished run yet is not quiet"
    never = scheduler.next_run_at({"enabled": True, "last_run_at": None}, TIMES, now=_myt("2026-10-07 13:00"))
    assert never == _myt("2026-10-07 18:30")
    same = {"scout": {**TIMES["scout"], "weekend": "same"}}
    assert scheduler.next_run_at({"enabled": True, "last_run_at": _myt("2026-10-10 12:31")}, same) == _myt("2026-10-10 18:30")


def test_a_due_set_time_starts_the_search(store):
    save_settings({"scout": {"enabled": True}}, expected_revision=0)  # the default is set times
    search = scout.create_search({"keywords": "x", "country": "my"})
    _set_last_run(search["id"], _myt("2026-10-07 09:00"))
    started = []
    assert scheduler.tick(now=_myt("2026-10-07 12:29"), start=lambda sid, trigger: started.append(sid)) is None
    assert scheduler.tick(now=_myt("2026-10-07 12:30"), start=lambda sid, trigger: started.append(sid)) == search["id"]


def _local(text, zone):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(zone)).timestamp())


def test_each_search_follows_its_countrys_clock_and_working_week(store):
    qa = lambda text: _local(text, "Asia/Qatar")
    nxt = lambda last: scheduler.next_run_at({"enabled": True, "last_run_at": last, "last_new": 5, "country": "qa"}, TIMES)
    # 12:30 and 18:30 Doha time (UTC+3), not Kuala Lumpur's.
    assert nxt(qa("2026-10-07 09:00")) == qa("2026-10-07 12:30")
    # Thursday evening -> Friday off -> Saturday's one run -> Sunday is a working day.
    assert nxt(qa("2026-10-08 18:31")) == qa("2026-10-10 12:30")
    assert nxt(qa("2026-10-10 12:31")) == qa("2026-10-11 12:30")
    assert nxt(qa("2026-10-11 12:31")) == qa("2026-10-11 18:30")
    my = scheduler.next_run_at({"enabled": True, "last_run_at": _myt("2026-10-10 12:31"), "last_new": 5, "country": "my"}, TIMES)
    assert my == _myt("2026-10-12 12:30"), "Malaysia rests on Sunday"
