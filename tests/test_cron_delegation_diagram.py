"""Scheduled jobs: per-run delegation diagram, reusing Agent Canvas's renderer.

Backend: ``list_cron_run_trees()`` reads a cron job's runs out of the agent's
``state.db`` and hangs each run's subagent descendants off it. Frontend: the
job detail page draws that with ``AgentCanvas.renderStaticTree``.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.agent_sessions import cron_session_id_prefix, list_cron_run_trees  # noqa: E402


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def _make_db(tmp_path, rows):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE sessions(
            id TEXT PRIMARY KEY, source TEXT, parent_session_id TEXT, title TEXT,
            started_at REAL, ended_at REAL, model TEXT, input_tokens INTEGER,
            output_tokens INTEGER, reasoning_tokens INTEGER, api_call_count INTEGER,
            tool_call_count INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL)"""
    )
    for row in rows:
        conn.execute(
            "INSERT INTO sessions(id, source, parent_session_id, title, started_at, ended_at,"
            " model, tool_call_count, actual_cost_usd) VALUES(?,?,?,?,?,?,?,?,?)",
            row,
        )
    conn.commit()
    conn.close()
    return db


def test_cron_session_id_prefix_matches_scheduler_naming():
    assert cron_session_id_prefix("abc123") == "cron_abc123_"


def test_runs_are_newest_first_with_nested_children(tmp_path):
    job = "45e62a5bc3ae"
    old = f"cron_{job}_20260101_090000"
    new = f"cron_{job}_20260102_090000"
    db = _make_db(
        tmp_path,
        [
            (old, "cron", None, "Scheduled run", 100.0, 200.0, "m", 2, 0.1),
            (new, "cron", None, "Scheduled run", 300.0, 400.0, "m", 4, 0.2),
            ("child-a", "subagent", new, "Subagent: research", 310.0, 350.0, "m", 3, 0.05),
            ("grandchild", "subagent", "child-a", "Subagent: verify", 320.0, 340.0, "m", 1, 0.01),
            ("child-b", "subagent", old, "Subagent: summarize", 110.0, 150.0, "m", 2, 0.02),
        ],
    )

    runs = list_cron_run_trees(db, job)

    assert [r["session_id"] for r in runs] == [new, old]
    newest = runs[0]
    assert [c["session_id"] for c in newest["children"]] == ["child-a", "grandchild"]
    # The grandchild keeps its real parent so the frontend can nest it under
    # its own card instead of flattening it onto the run.
    assert newest["children"][1]["parent_session_id"] == "child-a"
    assert newest["tool_call_count"] == 4
    assert runs[1]["children"][0]["session_id"] == "child-b"


def test_descendant_sharing_the_run_id_prefix_is_not_listed_as_a_run(tmp_path):
    """A child id built from its parent's id must stay a child, not a run."""
    job = "45e62a5bc3ae"
    run = f"cron_{job}_20260102_090000"
    db = _make_db(
        tmp_path,
        [
            (run, "cron", None, "Scheduled run", 300.0, 400.0, "m", 4, 0.2),
            (f"{run}_sub0", "subagent", run, "Subagent: research", 310.0, 350.0, "m", 3, 0.05),
        ],
    )

    runs = list_cron_run_trees(db, job)

    assert [r["session_id"] for r in runs] == [run]
    assert [c["session_id"] for c in runs[0]["children"]] == [f"{run}_sub0"]


def test_other_jobs_and_unrelated_chats_are_excluded(tmp_path):
    job = "45e62a5bc3ae"
    run = f"cron_{job}_20260102_090000"
    db = _make_db(
        tmp_path,
        [
            (run, "cron", None, "Scheduled run", 300.0, 400.0, "m", 4, 0.2),
            ("cron_otherjob_20260102_090000", "cron", None, "Other job", 305.0, 405.0, "m", 1, 0.1),
            ("chat-1", "webui", None, "A chat", 10.0, 20.0, "m", 0, 0.0),
            ("chat-kid", "subagent", "chat-1", "Subagent: unrelated", 12.0, 18.0, "m", 1, 0.01),
        ],
    )

    runs = list_cron_run_trees(db, job)

    assert [r["session_id"] for r in runs] == [run]
    assert runs[0]["children"] == []


def test_running_run_has_no_end_and_is_reported_running(tmp_path):
    job = "45e62a5bc3ae"
    run = f"cron_{job}_20260102_090000"
    db = _make_db(
        tmp_path,
        [(run, "cron", None, "Scheduled run", 300.0, None, "m", 1, None)],
    )

    runs = list_cron_run_trees(db, job)

    assert runs[0]["status"] == "running"
    assert runs[0]["ended_at"] is None


def test_missing_database_returns_no_runs(tmp_path):
    assert list_cron_run_trees(tmp_path / "nope.db", "45e62a5bc3ae") == []


def test_scan_window_reaches_past_childless_runs(tmp_path):
    """An hourly job's newest runs are usually childless — the older run that
    did delegate must still be found, not fall off the end of the window."""
    job = "45e62a5bc3ae"
    delegating = f"cron_{job}_20260101_000000"
    rows = [(delegating, "cron", None, "Scheduled run", 1.0, 2.0, "m", 1, 0.1),
            ("kid", "subagent", delegating, "Subagent: work", 1.5, 1.9, "m", 1, 0.01)]
    # 30 newer runs that delegated to nothing sit in front of it.
    rows += [
        (f"cron_{job}_2026010{i // 10}_{i:04d}00", "cron", None, "Scheduled run",
         100.0 + i, 101.0 + i, "m", 0, 0.0)
        for i in range(30)
    ]
    db = _make_db(tmp_path, rows)

    scanned = list_cron_run_trees(db, job, scan_limit=100)

    assert len(scanned) == 31
    delegating_runs = [r for r in scanned if r["children"]]
    assert [r["session_id"] for r in delegating_runs] == [delegating]


def test_scan_limit_bounds_how_many_runs_are_read(tmp_path):
    job = "45e62a5bc3ae"
    rows = [
        (f"cron_{job}_20260101_{i:04d}00", "cron", None, "Scheduled run",
         100.0 + i, 101.0 + i, "m", 0, 0.0)
        for i in range(10)
    ]
    db = _make_db(tmp_path, rows)

    assert len(list_cron_run_trees(db, job, scan_limit=3)) == 3


def test_delegation_route_is_registered_and_validates_job_id():
    src = read("api/routes.py")
    assert 'if parsed.path == "/api/crons/delegation":' in src
    assert "def _handle_cron_delegation(handler, parsed):" in src
    assert 'return j(handler, {"error": "invalid job_id"}, status=400)' in src
    assert "scan_limit = min(500, max(100, limit * 10))" in src
    assert "list_cron_run_trees(resolve_agent_state_db_paths(), job_id, scan_limit)" in src
    # Only runs that actually delegated are shipped; run_count still lets the
    # page distinguish "never run" from "ran, never delegated".
    assert 'delegating = [run for run in scanned if run.get("children")][:limit]' in src
    assert '"run_count": len(scanned),' in src


def test_job_detail_draws_the_tree_with_the_agent_canvas_renderer():
    panels = read("static/panels.js")
    canvas = read("static/agent-canvas.js")
    assert "async function _loadCronDelegation(jobId, detailKey)" in panels
    assert "/api/crons/delegation?job_id=" in panels
    assert "runCount = Number(data && data.run_count) || 0;" in panels
    assert "const hint = _cronDelegationRunCount" in panels
    assert "window.AgentCanvas.renderStaticTree(treeEl, {" in panels
    # Script-mode jobs never run an agent, so they get no delegation card.
    assert "const showDelegation = !isNoAgent && !isReadOnly;" in panels
    assert "function renderStaticTree(container, opts)" in canvas
    assert "renderStaticTree };" in canvas


def test_static_tree_shares_the_live_canvas_builders():
    canvas = read("static/agent-canvas.js")
    # One node-map-aware set of builders, not a second copy of the tree code.
    assert "function childrenOf(id, nodes){" in canvas
    assert "function buildCard(node, staggerIndex, baseDelayMs, ctx){" in canvas
    assert "function buildBranch(node, staggerIndex, baseDelayMs, ctx){" in canvas
    assert "function buildTreeNodes(parentSessionId, children, rootPatch){" in canvas
    # An embedded diagram is read-only: no selection, no click handlers.
    assert "const interactive = !ctx || ctx.interactive !== false;" in canvas
    assert "interactive: false" in canvas


def test_delegation_card_strings_and_styles_exist():
    i18n = read("static/i18n.js")
    css = read("static/style.css")
    assert "cron_delegation_title: 'Delegation'," in i18n
    assert "cron_delegation_root_sub: 'Scheduled run'," in i18n
    assert "cron_delegation_none: \"None of this job's recent runs delegated" in i18n
    assert "cron_delegation_no_runs:" in i18n
    # Bounded height, or a deeply nested tree stretches the card past the
    # run-output card below it instead of scrolling inside its own box.
    assert ".cron-delegation-canvas{overflow:auto;max-height:min(60vh,520px);" in css
    assert ".cron-delegation-run.active{" in css
    assert ".agent-canvas-card.is-static{cursor:default;}" in css


def test_titlebar_profile_switcher_is_spaced_from_the_chat_title():
    css = read("static/style.css")
    line = next(
        ln for ln in css.splitlines() if ln.strip().startswith(".app-titlebar-profile{")
    )
    assert "margin-inline-end:14px" in line
