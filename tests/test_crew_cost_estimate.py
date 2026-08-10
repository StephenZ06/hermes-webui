"""Crews Phase 3 cost estimate tests (labeled-approximation option, see
docs/HERMES_STUDIO_PARITY_PLAN.md, "Phase 3 -- Cost panel").

api.crews.estimate_crew_costs() is a pure function over task dicts + each
assignee profile's real state.db, so it's tested directly (unit-level,
monkeypatching api.models._get_profile_home to a tmp_path sqlite file)
rather than via HTTP -- mirrors the dispatch tests in test_crews_api.py,
which also avoid needing a real hermes_cli mount.
"""
import sqlite3
import time

import pytest

from api import crews as crews_mod
from api import models as models_mod

SESSIONS_SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    source TEXT,
    started_at REAL,
    ended_at REAL,
    estimated_cost_usd REAL
);
"""


def _make_state_db(tmp_path, profile: str, sessions: list[tuple]):
    """sessions: list of (id, source, started_at, ended_at, estimated_cost_usd)."""
    home = tmp_path / profile
    home.mkdir(parents=True, exist_ok=True)
    db_path = home / "state.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(SESSIONS_SCHEMA)
    conn.executemany(
        "INSERT INTO sessions (id, source, started_at, ended_at, estimated_cost_usd) VALUES (?,?,?,?,?)",
        sessions,
    )
    conn.commit()
    conn.close()
    return home


def _patch_profile_home(monkeypatch, tmp_path):
    def _fake_get_profile_home(profile):
        return tmp_path / str(profile)

    monkeypatch.setattr(models_mod, "_get_profile_home", _fake_get_profile_home)


def _task(id_, crew_id, assignee=None, started_at=None, completed_at=None):
    return {
        "id": id_,
        "workflow_template_id": crew_id,
        "assignee": assignee,
        "started_at": started_at,
        "completed_at": completed_at,
    }


def test_tasks_without_workflow_template_id_are_ignored():
    result = crews_mod.estimate_crew_costs([_task("t1", None, assignee="dev", started_at=100)])
    assert result == {}


def test_task_without_assignee_or_started_at_counted_but_not_priced():
    tasks = [_task("t1", "crewA"), _task("t2", "crewA", assignee="dev")]  # no started_at on either
    result = crews_mod.estimate_crew_costs(tasks)
    assert result["crewA"]["task_count"] == 2
    assert result["crewA"]["priced_task_count"] == 0
    assert result["crewA"]["approx_cost_usd"] == 0.0


def test_matches_session_within_window_and_sums_cost(monkeypatch, tmp_path):
    _patch_profile_home(monkeypatch, tmp_path)
    now = time.time()
    _make_state_db(tmp_path, "dev", [
        ("s1", "cli", now + 5, now + 10, 0.25),
        ("s2", "cli", now + 6, now + 9, 0.10),
    ])
    tasks = [_task("t1", "crewA", assignee="dev", started_at=now, completed_at=now + 20)]
    result = crews_mod.estimate_crew_costs(tasks)
    assert result["crewA"]["priced_task_count"] == 1
    assert result["crewA"]["approx_cost_usd"] == pytest.approx(0.35)


def test_session_outside_task_window_not_matched(monkeypatch, tmp_path):
    _patch_profile_home(monkeypatch, tmp_path)
    now = time.time()
    _make_state_db(tmp_path, "dev", [
        ("s1", "cli", now - 1000, now - 990, 5.00),  # long before the task ran
    ])
    tasks = [_task("t1", "crewA", assignee="dev", started_at=now, completed_at=now + 20)]
    result = crews_mod.estimate_crew_costs(tasks)
    assert result["crewA"]["priced_task_count"] == 0
    assert result["crewA"]["approx_cost_usd"] == 0.0


def test_webui_sourced_sessions_excluded(monkeypatch, tmp_path):
    _patch_profile_home(monkeypatch, tmp_path)
    now = time.time()
    _make_state_db(tmp_path, "dev", [
        ("s1", "webui", now + 1, now + 2, 9.99),
    ])
    tasks = [_task("t1", "crewA", assignee="dev", started_at=now, completed_at=now + 20)]
    result = crews_mod.estimate_crew_costs(tasks)
    assert result["crewA"]["priced_task_count"] == 0
    assert result["crewA"]["approx_cost_usd"] == 0.0


def test_multiple_tasks_same_crew_sum_across_assignees(monkeypatch, tmp_path):
    _patch_profile_home(monkeypatch, tmp_path)
    now = time.time()
    _make_state_db(tmp_path, "dev", [("s1", "cli", now + 1, now + 2, 1.0)])
    _make_state_db(tmp_path, "ops", [("s2", "cli", now + 1, now + 2, 2.0)])
    tasks = [
        _task("t1", "crewA", assignee="dev", started_at=now, completed_at=now + 20),
        _task("t2", "crewA", assignee="ops", started_at=now, completed_at=now + 20),
    ]
    result = crews_mod.estimate_crew_costs(tasks)
    assert result["crewA"]["task_count"] == 2
    assert result["crewA"]["priced_task_count"] == 2
    assert result["crewA"]["approx_cost_usd"] == pytest.approx(3.0)


def test_missing_state_db_returns_zero_without_raising(monkeypatch, tmp_path):
    _patch_profile_home(monkeypatch, tmp_path)  # profile dir never created
    tasks = [_task("t1", "crewA", assignee="ghost-profile", started_at=time.time())]
    result = crews_mod.estimate_crew_costs(tasks)
    assert result["crewA"]["priced_task_count"] == 0
    assert result["crewA"]["approx_cost_usd"] == 0.0


def test_distinct_crews_kept_separate(monkeypatch, tmp_path):
    _patch_profile_home(monkeypatch, tmp_path)
    now = time.time()
    _make_state_db(tmp_path, "dev", [("s1", "cli", now + 1, now + 2, 1.5)])
    tasks = [
        _task("t1", "crewA", assignee="dev", started_at=now, completed_at=now + 20),
        _task("t2", "crewB", assignee="dev", started_at=now - 500, completed_at=now - 480),
    ]
    result = crews_mod.estimate_crew_costs(tasks)
    assert result["crewA"]["approx_cost_usd"] == pytest.approx(1.5)
    assert result["crewB"]["approx_cost_usd"] == 0.0


def test_route_wiring_present_and_labeled_approximate():
    """Static guard: /api/crews/cost is wired in routes.py and always
    returns is_approximate=True, mirroring the "must be labeled as such in
    the UI" requirement from the plan doc -- checked at the source-string
    level since the endpoint needs a real/faked hermes_cli mount to invoke
    over HTTP, same constraint as the dispatch tests above."""
    with open("api/routes.py", encoding="utf-8") as f:
        src = f.read()
    assert '"/api/crews/cost"' in src
    idx = src.index('"/api/crews/cost"')
    # is_approximate: True must appear in both the success and the
    # exception-fallback branch of this handler.
    snippet = src[idx:idx + 900]
    assert snippet.count("is_approximate") >= 2
    assert 'estimate_crew_costs' in snippet
