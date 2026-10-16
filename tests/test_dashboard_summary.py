"""Dashboard summaries: each tab gathers from the store that owns the data, and
one unreadable store yields an error section instead of breaking the page."""

import json

import pytest


@pytest.fixture()
def hub(monkeypatch, tmp_path):
    from api import work_hub

    monkeypatch.setattr(work_hub, "STATE_DIR", tmp_path)
    monkeypatch.setattr("api.models.load_projects", lambda **_: [{"project_id": "p1", "name": "SaaS app"}])
    return work_hub


def test_personal_counts_work_and_builds_project_health_and_quests(hub, monkeypatch):
    from api import dashboard

    hub.create_item({"title": "Ship pricing", "status": "in_progress", "project_id": "p1"}, None)
    hub.create_item({"title": "Fix bug", "status": "blocked", "project_id": "p1"}, None)
    hub.create_item({"title": "Done thing", "status": "done", "project_id": "p1"}, None)
    hub.create_item({"title": "Inbox idea", "status": "backlog"}, None)
    monkeypatch.setattr(dashboard, "_schedules", lambda: {"enabled": 0, "failing": [], "failing_count": 0, "upcoming": []})
    monkeypatch.setattr(dashboard, "_recent_notes", lambda: [])

    data = dashboard.summary("personal")

    totals = data["work_hub"]["totals"]
    assert (totals["open"], totals["in_progress"], totals["blocked"], totals["done_this_week"]) == (3, 1, 1, 1)
    saas = next(p for p in data["work_hub"]["projects"] if p["name"] == "SaaS app")
    assert (saas["open"], saas["done"], saas["blocked"], saas["progress"]) == (2, 1, 1, round(1 / 3, 3))
    assert [q["title"] for q in data["work_hub"]["quests"]][:2] == ["Ship pricing", "Fix bug"]
    assert data["work_hub"]["quests"][0]["project_id"] == "p1"


def test_failing_and_disabled_schedules(monkeypatch, tmp_path):
    from api import dashboard

    home = tmp_path / "home"
    (home / "cron").mkdir(parents=True)
    (home / "cron" / "jobs.json").write_text(json.dumps({"jobs": [
        {"id": "a", "name": "graphify-refresh", "enabled": True, "last_status": "error", "last_error": "Script not found"},
        {"id": "b", "name": "digest", "enabled": True, "last_status": "ok", "next_run_at": "2026-10-17T08:00:00"},
        {"id": "c", "name": "off", "enabled": False, "last_status": "error"},
    ]}))
    monkeypatch.setattr("api.gateway_ticker._iter_profile_homes", lambda: [home])

    data = dashboard._schedules()

    assert data["enabled"] == 2 and data["failing_count"] == 1
    assert data["failing"][0]["name"] == "graphify-refresh" and "Script not found" in data["failing"][0]["error"]
    assert [u["name"] for u in data["upcoming"]] == ["digest"]


def test_a_broken_store_is_an_error_section_not_a_crash(monkeypatch):
    from api import dashboard

    def boom():
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(dashboard, "_work_hub", lambda now: boom())
    monkeypatch.setattr(dashboard, "_schedules", lambda: {"enabled": 0, "failing": [], "failing_count": 0, "upcoming": []})
    monkeypatch.setattr(dashboard, "_recent_notes", lambda: [])

    data = dashboard.summary("personal")

    assert data["work_hub"] == {"error": "disk on fire"}
    assert data["schedules"]["enabled"] == 0


def test_career_this_week_sums_the_last_seven_days(monkeypatch):
    from api import dashboard

    activity = {"today": "2026-10-16", "days": {"2026-10-16": {"found": 3, "applied": 1}, "2026-10-10": {"found": 2},
                                                  "2026-10-09": {"found": 50}}}
    assert dashboard._week_activity(activity, 0) == {"found": 5, "tailored": 0, "applied": 1, "interview": 0, "rejected": 0}


def test_unknown_tab_falls_back_to_personal(monkeypatch):
    from api import dashboard

    monkeypatch.setattr(dashboard, "personal", lambda: {"marker": True})
    assert dashboard.summary("../../etc")["tab"] == "personal"
