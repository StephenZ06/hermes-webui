"""The record of cross-profile delegations, and its way into the Office history.

`delegate_task` children are subagent rows inside hermes-agent's own state.db,
which is how the Office history sidebar finds "chats that delegated". A
`delegate_to_profile` child is not that: the tool creates it through
`POST /api/session/new`, so it lands in the TARGET profile's state.db as an
ordinary `source='webui'` row with `parent_session_id` NULL. Nothing anywhere
records that one chat caused it, so a cross-profile run could be watched live
and then vanished from history the moment it finished.

This ledger is that missing record. It is deliberately not a state.db column:
the parent lives in a different profile's database, and
`list_parents_with_subagent_children` is built on each database being a
separate universe.
"""
from __future__ import annotations

import json
import types

import pytest


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    from api import cross_profile_ledger

    monkeypatch.setattr(cross_profile_ledger, "_ledger_dir", lambda: tmp_path / "xp")
    return cross_profile_ledger


def start(ledger, child="child-1", parent="chat-1", **fields):
    kwargs = {
        "profile": "docs-gits",
        "goal": "Summarise the last 5 commits",
        "model": "gpt-5.6-luna",
        "started_at": 1000.0,
    }
    kwargs.update(fields)
    ledger.record_start(parent, child, **kwargs)


# ── recording ────────────────────────────────────────────────────────────────

def test_a_started_delegation_is_readable_immediately(ledger):
    # It has to be: the run may be interrupted, and a delegation that was
    # started and never finished is exactly what the history should show.
    start(ledger)

    children = ledger.children_for_parent("chat-1")

    assert len(children) == 1
    row = children[0]
    assert row["session_id"] == "child-1"
    assert row["parent_session_id"] == "chat-1"
    assert row["title"] == "Summarise the last 5 commits"
    assert row["model"] == "gpt-5.6-luna"
    assert row["started_at"] == 1000.0
    assert row["ended_at"] is None
    assert row["status"] == "running"


def test_the_cluster_names_the_target_profile(ledger):
    # The live floor seats a cross-profile child under `profile:<name>`; the
    # replay reads this field to rebuild the same pod.
    start(ledger)

    assert ledger.children_for_parent("chat-1")[0]["cluster"] == "profile:docs-gits"


def test_finishing_fills_in_the_outcome(ledger):
    start(ledger)

    ledger.record_finish(
        "chat-1", "child-1", status="completed", ended_at=1042.5,
        input_tokens=104079, output_tokens=1014, cost_usd=0.42, api_call_count=3,
        tool_call_count=8,
    )

    row = ledger.children_for_parent("chat-1")[0]
    assert row["status"] == "completed"
    assert row["ended_at"] == 1042.5
    assert row["input_tokens"] == 104079
    assert row["output_tokens"] == 1014
    assert row["cost_usd"] == 0.42
    assert row["api_call_count"] == 3
    assert row["tool_call_count"] == 8
    # The facts recorded at the start survive the update.
    assert row["title"] == "Summarise the last 5 commits"
    assert row["started_at"] == 1000.0


def test_finishing_a_delegation_nobody_started_is_ignored(ledger):
    ledger.record_finish("chat-1", "ghost", status="completed", ended_at=1.0)

    assert ledger.children_for_parent("chat-1") == []


def test_siblings_never_overwrite_each_other(ledger):
    # Three profiles now run at once. One file per child rather than one per
    # parent, so concurrent writers never read-modify-write the same file.
    start(ledger, child="a", profile="docs-gits", started_at=1000.0)
    start(ledger, child="b", profile="frontend", started_at=1000.1)
    start(ledger, child="c", profile="backend", started_at=1000.2)
    ledger.record_finish("chat-1", "b", status="completed", ended_at=1080.0)

    rows = {r["session_id"]: r for r in ledger.children_for_parent("chat-1")}

    assert set(rows) == {"a", "b", "c"}
    assert rows["b"]["status"] == "completed"
    assert rows["a"]["status"] == "running" and rows["c"]["status"] == "running"


def test_children_come_back_in_the_order_they_started(ledger):
    start(ledger, child="late", started_at=2000.0)
    start(ledger, child="early", started_at=1000.0)

    assert [r["session_id"] for r in ledger.children_for_parent("chat-1")] == ["early", "late"]


def test_parents_are_listed_newest_run_first(ledger):
    start(ledger, child="a", parent="old-chat", started_at=1000.0)
    start(ledger, child="b", parent="new-chat", started_at=5000.0)

    parents = ledger.parents_with_delegations()

    assert [p["parent_session_id"] for p in parents] == ["new-chat", "old-chat"]
    assert parents[0]["latest_at"] == 5000.0
    assert [c["session_id"] for c in parents[0]["children"]] == ["b"]


def test_an_empty_ledger_is_not_an_error(ledger):
    assert ledger.parents_with_delegations() == []
    assert ledger.children_for_parent("chat-1") == []


# ── it must never break the caller ───────────────────────────────────────────

def test_a_corrupt_record_is_skipped_not_raised(ledger, tmp_path):
    start(ledger)
    bad = tmp_path / "xp" / "chat-1" / "broken.json"
    bad.write_text("{not json", encoding="utf-8")

    assert [r["session_id"] for r in ledger.children_for_parent("chat-1")] == ["child-1"]


def test_recording_never_raises_into_the_delegating_turn(ledger, monkeypatch):
    # This runs inside the tool, mid-delegation. A failed write must cost the
    # history entry, never the delegation itself.
    monkeypatch.setattr(ledger, "_write_record", _boom)

    ledger.record_start("chat-1", "child-1", profile="docs-gits", goal="g",
                        model="m", started_at=1.0)
    ledger.record_finish("chat-1", "child-1", status="completed", ended_at=2.0)


def _boom(*args, **kwargs):
    raise OSError("disk full")


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", ".", "..", "a\x00b"])
def test_a_session_id_that_is_not_a_session_id_is_refused(ledger, bad):
    # Both ids become path segments. Nothing that could leave the ledger
    # directory may be written or read.
    ledger.record_start(bad, "child-1", profile="p", goal="g", model="m", started_at=1.0)
    ledger.record_start("chat-1", bad, profile="p", goal="g", model="m", started_at=1.0)

    assert ledger.parents_with_delegations() == []


# ── the endpoint that the Office sidebar reads ───────────────────────────────

def test_cross_profile_runs_reach_the_history_sidebar(ledger, monkeypatch):
    """The bug this whole module exists for.

    /api/agent-canvas/sessions answered only from state.db, so a chat whose
    only delegations were cross-profile did not appear in the sidebar at all.
    """
    from api import routes

    start(ledger, child="child-1", parent="chat-1")
    monkeypatch.setattr(routes, "_agent_canvas_state_db_parents", lambda: [])

    parents = routes._agent_canvas_parents()

    assert [p["parent_session_id"] for p in parents] == ["chat-1"]
    assert [c["session_id"] for c in parents[0]["children"]] == ["child-1"]


def test_a_chat_that_delegated_both_ways_shows_one_entry(ledger, monkeypatch):
    from api import routes

    start(ledger, child="xp-child", parent="chat-1", started_at=2000.0)
    monkeypatch.setattr(routes, "_agent_canvas_state_db_parents", lambda: [
        {"parent_session_id": "chat-1", "latest_at": 1000.0, "children": [
            {"session_id": "task-child", "parent_session_id": "chat-1", "started_at": 1000.0},
        ]},
    ])

    parents = routes._agent_canvas_parents()

    assert len(parents) == 1
    assert [c["session_id"] for c in parents[0]["children"]] == ["task-child", "xp-child"]
    assert parents[0]["latest_at"] == 2000.0, "the newer of the two runs dates the entry"


def test_a_child_recorded_in_both_places_is_not_drawn_twice(ledger, monkeypatch):
    from api import routes

    start(ledger, child="child-1", parent="chat-1")
    monkeypatch.setattr(routes, "_agent_canvas_state_db_parents", lambda: [
        {"parent_session_id": "chat-1", "latest_at": 1000.0, "children": [
            {"session_id": "child-1", "parent_session_id": "chat-1", "started_at": 1000.0},
        ]},
    ])

    parents = routes._agent_canvas_parents()

    assert [c["session_id"] for c in parents[0]["children"]] == ["child-1"]


def test_a_broken_ledger_does_not_take_the_sidebar_down(ledger, monkeypatch):
    from api import routes

    monkeypatch.setattr(ledger, "parents_with_delegations", _boom)
    monkeypatch.setattr(routes, "_agent_canvas_state_db_parents", lambda: [
        {"parent_session_id": "chat-1", "latest_at": 1000.0, "children": []},
    ])

    assert [p["parent_session_id"] for p in routes._agent_canvas_parents()] == ["chat-1"]
