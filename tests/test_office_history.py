"""Behavioural tests for the office's history replay (phase 4).

`GET /api/agent-canvas/sessions` returns the chats that ever delegated, each
with the subagent rows recorded in hermes-agent's state.db. The office rebuilds
a finished run by replaying those rows through an ordinary adapter rather than
teaching the adapter a second, frozen mode — so `static/office/history.js` is
pure translation, and node can run it together with the real adapter.

The corrections it makes are the interesting part: a row with no `ended_at`
reads as 'running' from the raw query, but in a *finished* session that can
only mean it was cut off.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
HISTORY = REPO / "static" / "office" / "history.js"
ADAPTER = REPO / "static" / "office" / "adapter.js"
HISTORY_SRC = HISTORY.read_text(encoding="utf-8")
OFFICE_INDEX_SRC = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
INDEX_HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")
PANELS_JS = (REPO / "static" / "panels.js").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the office history replay"
)

_DRIVER = r"""
const { historyEventsFromParent, applyHistory } = await import(process.argv[2]);
const { createOfficeAdapter } = await import(process.argv[3]);
const parent = JSON.parse(process.argv[4] || '{}');

const events = historyEventsFromParent(parent);
const adapter = createOfficeAdapter({ maxDesks: 400, now: () => 1000000 });
applyHistory(adapter, parent);

process.stdout.write(JSON.stringify({ events, state: adapter.getState() }));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-history") / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def replay(driver, parent):
    proc = subprocess.run(
        [NODE, str(driver), HISTORY.as_uri(), ADAPTER.as_uri(), json.dumps(parent)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office history driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def parent_entry(*children, parent_session_id="chat-1"):
    return {"parent_session_id": parent_session_id, "children": list(children)}


def child(session_id, **fields):
    row = {
        "session_id": session_id,
        "parent_session_id": "chat-1",
        "title": f"Subagent: {session_id}",
        "started_at": 1000.0,
        "ended_at": 1012.5,
        "status": "completed",
    }
    row.update(fields)
    return row


def worker(state, sid):
    return next(w for w in state["workers"] if w["id"] == sid)


# ── translation ──────────────────────────────────────────────────────────────

def test_direct_children_hang_off_the_conductor(driver):
    out = replay(driver, parent_entry(child("a"), child("b")))
    assert [s["parent_id"] for s in out["events"]["spawns"]] == [None, None]


def test_nested_children_keep_their_real_parent(driver):
    # Nested delegation is a real Hermes feature; a grandchild must rebuild
    # under its own parent, not flattened onto the conductor.
    out = replay(driver, parent_entry(
        child("a"),
        child("b", parent_session_id="a"),
    ))
    spawns = {s["subagent_id"]: s["parent_id"] for s in out["events"]["spawns"]}
    assert spawns == {"a": None, "b": "a"}
    # And the adapter seats the grandchild in its parent's cluster.
    desks = {d["id"]: d for d in out["state"]["desks"]}
    b_desk = desks[worker(out["state"], "b")["deskId"]]
    assert b_desk["cluster"] == "a"


def test_the_subagent_title_prefix_is_stripped(driver):
    out = replay(driver, parent_entry(child("a", title="Subagent: audit the routes")))
    assert worker(out["state"], "a")["goal"] == "audit the routes"


def test_a_missing_title_still_names_the_worker(driver):
    out = replay(driver, parent_entry(child("a", title="")))
    assert worker(out["state"], "a")["goal"] == "Subagent"


def test_rows_without_a_session_id_are_skipped(driver):
    out = replay(driver, parent_entry(child("a"), {"title": "orphan row"}))
    assert len(out["state"]["workers"]) == 1


# ── corrections ──────────────────────────────────────────────────────────────

def test_a_row_that_never_ended_reads_as_interrupted(driver):
    # The raw query calls a row with no ended_at 'running'. This is a finished
    # historical session, so that can only mean it was cut off — showing it as
    # running would claim a subagent is live when nothing is.
    out = replay(driver, parent_entry(child("a", ended_at=None, status="running")))
    w = worker(out["state"], "a")
    assert w["status"] == "interrupted" and w["pose"] == "stopped"


def test_a_completed_row_stays_completed(driver):
    out = replay(driver, parent_entry(child("a")))
    w = worker(out["state"], "a")
    assert w["status"] == "completed" and w["pose"] == "done"


def test_duration_comes_from_the_recorded_timestamps(driver):
    out = replay(driver, parent_entry(child("a", started_at=100.0, ended_at=142.5)))
    assert worker(out["state"], "a")["durationSeconds"] == 42.5


def test_duration_is_absent_rather_than_wrong_when_a_timestamp_is_missing(driver):
    out = replay(driver, parent_entry(child("a", started_at=0, ended_at=None)))
    assert worker(out["state"], "a")["durationSeconds"] is None


def test_recorded_stats_survive_the_replay(driver):
    # state.db carries the same numbers the live completion event does, so a
    # replayed office is not degraded to bare status dots.
    out = replay(driver, parent_entry(child(
        "a", input_tokens=9000, output_tokens=800, reasoning_tokens=120,
        cost_usd=0.0042, api_call_count=6,
    )))
    w = worker(out["state"], "a")
    assert w["inputTokens"] == 9000 and w["outputTokens"] == 800
    assert w["reasoningTokens"] == 120
    assert w["costUsd"] == 0.0042 and w["apiCalls"] == 6


def test_a_replayed_office_is_finished(driver):
    out = replay(driver, parent_entry(child("a"), child("b")))
    assert out["state"]["conductor"]["status"] == "idle", (
        "every worker in a historical run is terminal, so nothing is orchestrating"
    )


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_office_polls_the_same_endpoints_agent_canvas_uses():
    for path in ("/api/subagents/active", "/api/subagents/interrupt",
                 "/api/subagents/pause", "/api/agent-canvas/sessions"):
        assert path in OFFICE_INDEX_SRC, (
            f"{path} is the existing REST surface; the office must not open a "
            "second transport of its own"
        )


def test_reconcile_polling_stops_when_the_panel_is_left():
    # A timer left running after unmount keeps hitting the API forever for a
    # panel nobody is looking at.
    teardown_at = OFFICE_INDEX_SRC.index("function teardownObservers()")
    body = OFFICE_INDEX_SRC[teardown_at:OFFICE_INDEX_SRC.index("\n}\n", teardown_at)]
    assert "clearInterval(_pollTimer)" in body


def test_history_uses_its_own_adapter_so_the_live_one_keeps_running():
    assert "_historyAdapter = createOfficeAdapter(" in OFFICE_INDEX_SRC
    assert "maxDesks: 400" in OFFICE_INDEX_SRC, (
        "a finished run can exceed the live desk cap, and nothing should be "
        "reclaimed in a record of what already happened"
    )


def test_interrupt_is_offered_only_on_a_live_running_worker():
    assert "_viewMode === 'live' && !TERMINAL.has(worker.status)" in OFFICE_INDEX_SRC


def test_the_sidebar_history_list_is_wired_to_the_panel():
    assert 'id="officeSessionList"' in INDEX_HTML
    assert "window.HermesOffice.renderSidebar()" in PANELS_JS
    assert "window.officeReturnToLive = returnToLive;" in OFFICE_INDEX_SRC, (
        "the sidebar card uses a plain onclick attribute; a function declared "
        "inside a module is not a global"
    )


def test_history_translation_stays_pure():
    for forbidden in ("document.", "window.", "fetch(", "from 'three'"):
        assert forbidden not in HISTORY_SRC, (
            f"history.js must stay pure — found {forbidden!r}"
        )
