"""Automations summary: what runs on its own, when it last ran and when it runs next."""

from __future__ import annotations

import time

import pytest

from api import mailer, profiles
from api.job_os import automations, notify, scout
from api.job_os.settings import load_settings, save_settings


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_resolve_base_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(profiles, "_is_isolated_profile_mode", lambda: False)
    return monkeypatch


def _by_key(**kw):
    return {a["key"]: a for a in automations.summary(**kw)}


def test_everything_off_says_why(store):
    store.setattr(mailer, "credentials", lambda: (None, None))
    items = _by_key()
    assert not any(a["on"] for a in items.values() if a["key"] != "analysis")
    assert items["scout"]["off_reason"] == "Turn on Run Scout automatically"
    assert items["digest"]["off_reason"].startswith("Connect Gmail")
    assert "auto_apply" not in items, "Auto-apply was removed"


def test_schedules_report_last_and_next(store):
    store.setattr(mailer, "credentials", lambda: ("a@gmail.com", "pw"))
    save_settings({"scout": {"enabled": True, "schedule_mode": "interval", "schedule_hours": 4},
                   "notifications": {"email_enabled": True, "to_address": "me@gmail.com", "digest_hour": 8}}, expected_revision=0)
    search = scout.create_search({"keywords": "backend", "country": "my"})
    from api.job_os.db import connect_job_os

    conn = connect_job_os()
    conn.execute("UPDATE searches SET last_run_at=? WHERE id=?", (1_000_000, search["id"]))
    conn.commit()
    conn.close()
    morning = time.mktime(time.strptime("2026-10-06 07:00", "%Y-%m-%d %H:%M"))
    items = _by_key(now=morning)
    assert items["scout"]["on"] and items["scout"]["last"] == 1_000_000 and items["scout"]["next"] == 1_000_000 + 4 * 3600
    assert items["digest"]["next"] == int(morning + 3600)
    notify._save_state(last_digest="2026-10-06", last_poll=int(morning) - 30)
    items = _by_key(now=morning + 2 * 3600)
    assert items["digest"]["next"] == int(morning + 3600 + 86400)
    assert items["replies"]["on"] and items["replies"]["next"] == int(morning) - 30 + notify.POLL_EVERY


def test_history_counts_each_automation_per_day(store):
    import time as _time

    from api.job_os import automations
    from api.job_os.db import connect_job_os

    now = _time.time()
    conn = connect_job_os()
    conn.execute("INSERT INTO discovery_runs (id, search_id, status, created_at, finished_at) VALUES ('r1', 's', 'completed', ?, ?)", (int(now) - 3600, int(now) - 3500))
    conn.execute("INSERT INTO discovery_runs (id, search_id, status, created_at, finished_at) VALUES ('r2', 's', 'failed', ?, ?)", (int(now) - 3000, int(now) - 2900))
    conn.execute("INSERT INTO email_log (id, kind, status, subject, detail, created_at) VALUES ('e1', 'digest', 'sent', '', '', ?)", (int(now) - 86400 * 2,))
    conn.commit()
    conn.close()
    past = automations.history(now=now)
    assert len(past["scout"]) == 14 and past["scout"][-1]["state"] == "mixed"
    assert past["scout"][-1]["ok"] == 1 and past["scout"][-1]["failed"] == 1
    assert past["digest"][-3]["state"] == "ok" and past["alerts"][-1]["state"] == "none"
    assert all("history" in item for item in automations.summary(now=now))


def test_scout_run_times_say_which_clocks_they_follow():
    july = 1783000000  # 2026-07-02, summer time in Europe
    assert [automations.zone_label(z, now=july) for z in ("Asia/Jakarta", "Asia/Makassar", "Asia/Qatar", "Asia/Kolkata",
                                                          "Europe/Berlin", "Nowhere/Zone")] == ["WIB", "WITA", "GMT+3", "IST", "CEST", ""]
    zones = automations.scout_zones([{"country": "my"}, {"country": "qa"}, {"country": "my"}, {"country": "id", "enabled": False}])
    assert zones == ["GMT+8", "GMT+3"]
    when = automations._scout_when({"schedule_mode": "times", "run_times": ["12:30", "18:30"], "weekend": "saturday"}, zones)
    assert when == "At 12:30 and 18:30 GMT+8 / GMT+3, Saturday once"
    assert automations._scout_when({"schedule_mode": "interval", "schedule_hours": 6}, zones) == "Every 6 h"
