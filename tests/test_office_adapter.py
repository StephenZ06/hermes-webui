"""Behavioural tests for HermesOfficeAdapter (phase 2 of the office view).

Unlike the Agent Canvas suite, these do not assert on source text: the
adapter is a pure ES module — no DOM, no fetch, no three.js, no timers — so
node can import the real file and run it. A scenario is a list of steps
(spawn / tool / complete / snapshot / advance the clock / tick), and the
driver prints the emitted commands and the final state as JSON.

That purity is the reason the module is shaped the way it is, so one test
here guards it: the moment the adapter reaches for `document` or `fetch`,
this suite stops being able to test the real thing.

See docs/rfcs/office-visualization.md.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
ADAPTER = REPO / "static" / "office" / "adapter.js"
ADAPTER_SRC = ADAPTER.read_text(encoding="utf-8")
OFFICE_INDEX_SRC = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
MESSAGES_SRC = (REPO / "static" / "messages.js").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the office adapter"
)

# The driver is ESM (.mjs) so it can import the adapter regardless of where
# pytest drops it. The adapter itself is ESM because static/office/package.json
# declares `"type": "module"`.
_DRIVER = r"""
// The adapter path arrives as a file:// URL argument, so this has to be a
// dynamic import — an import statement takes a literal specifier.
const { createOfficeAdapter } = await import(process.argv[2]);

const scenario = JSON.parse(process.argv[3] || '{}');
let clock = 1000000;
const commands = [];

const adapter = createOfficeAdapter(Object.assign(
  { now: () => clock }, scenario.options || {},
));
adapter.subscribe(cmd => commands.push(cmd));
if (scenario.throwingSubscriber) {
  adapter.subscribe(() => { throw new Error('subscriber boom'); });
  adapter.subscribe(cmd => commands.push({ type: 'after-throw:' + cmd.type }));
}

for (const step of (scenario.steps || [])) {
  switch (step.op) {
    case 'spawn': adapter.onSpawn(step.payload); break;
    case 'tool': adapter.onToolActivity(step.payload); break;
    case 'complete': adapter.onComplete(step.payload); break;
    case 'snapshot': adapter.applySnapshot(step.payload); break;
    case 'advance': clock += step.ms; break;
    case 'tick': adapter.tick(); break;
    case 'reset': adapter.reset(); break;
    default: throw new Error('unknown op: ' + step.op);
  }
}

process.stdout.write(JSON.stringify({ commands, state: adapter.getState() }));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-adapter") / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def run(driver, steps, **options):
    scenario = {"steps": steps}
    scenario.update(options)
    proc = subprocess.run(
        [NODE, str(driver), ADAPTER.as_uri(), json.dumps(scenario)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office adapter driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def spawn(sid, **fields):
    payload = {"subagent_id": sid, "goal": f"goal for {sid}"}
    payload.update(fields)
    return {"op": "spawn", "payload": payload}


def tool(sid, name="Read", **fields):
    payload = {"subagent_id": sid, "tool": name}
    payload.update(fields)
    return {"op": "tool", "payload": payload}


def complete(sid, status="ok", **fields):
    payload = {"subagent_id": sid, "status": status}
    payload.update(fields)
    return {"op": "complete", "payload": payload}


def worker(state, sid):
    return next(w for w in state["workers"] if w["id"] == sid)


def types(result):
    return [c["type"] for c in result["commands"]]


# ── spawning and seating ─────────────────────────────────────────────────────

def test_spawn_seats_a_worker_and_starts_the_conductor(driver):
    out = run(driver, [spawn("a", model="opus", depth=1, task_index=0, task_count=3)])
    state = out["state"]

    assert types(out) == ["worker.spawn", "conductor"]
    assert state["conductor"]["status"] == "orchestrating"
    w = worker(state, "a")
    assert w["status"] == "running" and w["pose"] == "work"
    assert w["deskId"] == "desk-0"
    assert w["model"] == "opus" and w["depth"] == 1
    assert w["taskIndex"] == 0 and w["taskCount"] == 3
    assert state["desks"] == [
        {"id": "desk-0", "index": 0, "workerId": "a", "cluster": "__conductor__"}
    ]


def test_spawn_without_an_id_is_ignored(driver):
    out = run(driver, [{"op": "spawn", "payload": {"goal": "no id"}}])
    assert out["state"]["workers"] == []
    assert out["commands"] == []


def test_repeat_spawn_does_not_allocate_a_second_desk(driver):
    # The SSE stream and the /api/subagents/active reconcile both report the
    # same subagent; a second desk for one worker double-counts the office.
    out = run(driver, [spawn("a"), spawn("a")])
    assert len(out["state"]["desks"]) == 1
    assert types(out).count("worker.spawn") == 1


def test_long_goals_are_shortened_for_the_desk_label(driver):
    goal = "x" * 80
    out = run(driver, [spawn("a", goal=goal)])
    w = worker(out["state"], "a")
    assert w["goal"] == goal, "the full goal stays available for the detail view"
    assert len(w["label"]) == 42 and w["label"].endswith("…")


def test_siblings_are_reseated_in_their_own_cluster(driver):
    # c1 (parent p1) finishes first, so by age alone its desk would be the one
    # reclaimed. c3 belongs to p2's cluster, and keeping siblings together
    # wins: it takes c2's desk instead.
    out = run(driver, [
        spawn("c1", parent_id="p1"),
        spawn("c2", parent_id="p2"),
        complete("c1"),
        {"op": "advance", "ms": 5000},
        complete("c2"),
        {"op": "advance", "ms": 10},
        spawn("c3", parent_id="p2"),
    ], options={"maxDesks": 2})
    desks = {d["id"]: d for d in out["state"]["desks"]}
    assert desks["desk-1"]["workerId"] == "c3", (
        "desk-1 was p2's cluster; c3 is p2's child and should sit there"
    )
    assert worker(out["state"], "c1")["deskId"] == "desk-0", "c1 keeps its seat"


# ── tool activity ────────────────────────────────────────────────────────────

def test_tool_activity_poses_the_worker_and_settles_back(driver):
    out = run(driver, [
        spawn("a"),
        tool("a", "Bash", preview="ls -la", tool_count=4),
        {"op": "advance", "ms": 3000},
        {"op": "tick"},
    ], options={"toolPoseMs": 2600})

    assert types(out) == ["worker.spawn", "conductor", "worker.tool", "worker.pose"]
    w = worker(out["state"], "a")
    assert w["pose"] == "work", "the tool pose expires; it does not stick"
    assert w["tool"] == {"name": "Bash", "preview": "ls -la"}
    assert w["toolCount"] == 4


def test_tool_pose_holds_while_still_inside_the_window(driver):
    out = run(driver, [
        spawn("a"), tool("a"),
        {"op": "advance", "ms": 1000},
        {"op": "tick"},
    ], options={"toolPoseMs": 2600})
    assert worker(out["state"], "a")["pose"] == "tool"
    assert "worker.pose" not in types(out), "tick must not emit when nothing changed"


def test_tool_count_increments_when_the_event_omits_it(driver):
    out = run(driver, [spawn("a"), tool("a"), tool("a"), tool("a")])
    assert worker(out["state"], "a")["toolCount"] == 3


def test_events_for_an_unknown_subagent_are_counted_not_invented(driver):
    # A page attached mid-run sees tool/complete events for subagents that
    # spawned before the stream existed. That is not an error, but the office
    # must not conjure a worker out of a tool call either.
    out = run(driver, [tool("ghost"), complete("ghost")])
    assert out["state"]["workers"] == []
    assert out["state"]["orphanEvents"] == 2
    assert out["commands"] == []


# ── completion ───────────────────────────────────────────────────────────────

def test_completion_normalises_status_and_frees_the_conductor(driver):
    out = run(driver, [
        spawn("a"),
        complete("a", status="ok", duration_seconds=12.5, summary="done it",
                 input_tokens=100, output_tokens=20, cost_usd=0.004,
                 files_written=2, output_tail=["line one", "line two"]),
    ])
    w = worker(out["state"], "a")
    assert w["status"] == "completed", "delegate_tool reports 'ok'; the app speaks 'completed'"
    assert w["pose"] == "done"
    assert w["durationSeconds"] == 12.5 and w["summary"] == "done it"
    assert w["costUsd"] == 0.004 and w["filesWritten"] == 2
    assert w["outputTail"] == ["line one", "line two"]
    assert out["state"]["conductor"]["status"] == "idle"
    assert types(out)[-1] == "conductor"


@pytest.mark.parametrize("status,pose", [
    ("failed", "error"),
    ("error", "error"),
    ("timeout", "error"),
    ("interrupted", "stopped"),
    ("completed", "done"),
])
def test_terminal_statuses_map_to_poses(driver, status, pose):
    out = run(driver, [spawn("a"), complete("a", status=status)])
    w = worker(out["state"], "a")
    assert w["status"] == status and w["pose"] == pose


def test_an_unrecognised_terminal_status_still_ends_the_worker(driver):
    out = run(driver, [spawn("a"), complete("a", status="something-new")])
    w = worker(out["state"], "a")
    assert w["status"] == "completed", (
        "an unknown status must still be terminal — a worker left 'running' "
        "forever is the failure mode Agent Canvas already had"
    )


def test_terminal_is_sticky_against_late_events(driver):
    out = run(driver, [
        spawn("a"), complete("a"),
        tool("a", "Read"),
        complete("a", status="failed"),
    ])
    w = worker(out["state"], "a")
    assert w["status"] == "completed" and w["pose"] == "done"
    assert w["tool"] is None, "a late tool event must not resurrect a finished worker"
    assert types(out).count("worker.status") == 1


def test_the_conductor_stays_busy_until_every_worker_is_terminal(driver):
    out = run(driver, [spawn("a"), spawn("b"), complete("a")])
    assert out["state"]["conductor"]["status"] == "orchestrating"


# ── desk pressure ────────────────────────────────────────────────────────────

def test_a_finished_worker_gives_up_its_desk_under_pressure(driver):
    out = run(driver, [
        spawn("a"), spawn("b"),
        complete("a"),
        {"op": "advance", "ms": 10},
        spawn("c"),
    ], options={"maxDesks": 2})

    state = out["state"]
    assert len(state["desks"]) == 2, "the cap holds when a seat can be reclaimed"
    assert worker(state, "c")["deskId"] == "desk-0"
    assert worker(state, "a")["deskId"] is None
    reclaim = next(c for c in out["commands"] if c["type"] == "desk.reclaim")
    assert reclaim["previousWorkerId"] == "a"


def test_the_longest_finished_worker_is_evicted_first(driver):
    out = run(driver, [
        spawn("a"), spawn("b"),
        complete("a"),
        {"op": "advance", "ms": 5000},
        complete("b"),
        {"op": "advance", "ms": 10},
        spawn("c"),
    ], options={"maxDesks": 2})
    assert worker(out["state"], "c")["deskId"] == "desk-0"
    reclaim = next(c for c in out["commands"] if c["type"] == "desk.reclaim")
    assert reclaim["previousWorkerId"] == "a", "a finished first, so a loses its seat first"


def test_a_running_worker_is_never_evicted(driver):
    # Hermes genuinely running more subagents than the cap is not a reason to
    # reseat one of them; the office grows instead.
    out = run(driver, [spawn("a"), spawn("b"), spawn("c")], options={"maxDesks": 2})
    state = out["state"]
    assert len(state["desks"]) == 3
    assert all(w["deskId"] is not None for w in state["workers"])
    assert "desk.reclaim" not in types(out)


# ── reconcile snapshot ───────────────────────────────────────────────────────

def test_snapshot_adopts_subagents_the_stream_never_delivered(driver):
    out = run(driver, [{"op": "snapshot", "payload": {
        "spawn_paused": True,
        "active": [
            {"subagent_id": "a", "goal": "from snapshot", "status": "running",
             "tool_count": 7, "started_at": 1700},
        ],
    }}])
    state = out["state"]
    w = worker(state, "a")
    assert w["toolCount"] == 7
    assert w["spawnedAt"] == 1700 * 1000, "snapshot seconds become office milliseconds"
    assert state["spawnPaused"] is True


def test_snapshot_never_removes_a_worker_it_does_not_mention(driver):
    out = run(driver, [
        spawn("a"), spawn("b"),
        {"op": "snapshot", "payload": {"active": [{"subagent_id": "a", "status": "running"}]}},
    ])
    assert {w["id"] for w in out["state"]["workers"]} == {"a", "b"}


def test_snapshot_does_not_reopen_a_finished_worker(driver):
    out = run(driver, [
        spawn("a"), complete("a"),
        {"op": "snapshot", "payload": {"active": [{"subagent_id": "a", "status": "running"}]}},
    ])
    assert worker(out["state"], "a")["status"] == "completed"


def test_snapshot_is_a_noop_when_the_gateway_is_off(driver):
    out = run(driver, [{"op": "snapshot", "payload": {
        "gateway_enabled": False, "spawn_paused": True,
        "active": [{"subagent_id": "a"}],
    }}])
    assert out["state"]["workers"] == []
    assert out["state"]["spawnPaused"] is False


# ── housekeeping ─────────────────────────────────────────────────────────────

def test_reset_clears_the_office(driver):
    out = run(driver, [spawn("a"), tool("a"), {"op": "reset"}])
    state = out["state"]
    assert state["workers"] == [] and state["desks"] == []
    assert state["conductor"]["status"] == "idle"
    assert types(out)[-1] == "reset"


def test_a_throwing_subscriber_does_not_stop_the_others(driver):
    out = run(driver, [spawn("a")], throwingSubscriber=True)
    assert "after-throw:worker.spawn" in types(out)
    assert worker(out["state"], "a")["status"] == "running"


# ── purity and wiring ────────────────────────────────────────────────────────

def test_the_adapter_touches_no_browser_api():
    for forbidden in ("document.", "window.", "fetch(", "localStorage",
                      "setTimeout", "setInterval", "requestAnimationFrame",
                      "from 'three'"):
        assert forbidden not in ADAPTER_SRC, (
            f"adapter.js must stay pure — found {forbidden!r}. Its independence "
            "from the browser is what lets these tests run the real code."
        )


def test_the_office_exposes_the_event_intake_the_stream_calls():
    for name in ("onSpawn", "onToolActivity", "onComplete", "applySnapshot"):
        assert f"function {name}(" in OFFICE_INDEX_SRC


def test_live_sse_events_are_fanned_to_the_office():
    # Both views read the same Hermes truth; neither owns it. If this wiring
    # is dropped the office silently shows an empty floor during a real run.
    for name in ("onSpawn", "onToolActivity", "onComplete"):
        assert f"window.HermesOffice.{name}(d)" in MESSAGES_SRC


def test_office_state_survives_leaving_the_panel():
    assert "const _adapter = createOfficeAdapter();" in OFFICE_INDEX_SRC, (
        "the adapter must be module-level, not built in mount(): subagents "
        "keep running while the user is on Chat, and their events keep arriving"
    )
    unmount_at = OFFICE_INDEX_SRC.index("function unmount() {")
    body = OFFICE_INDEX_SRC[unmount_at:OFFICE_INDEX_SRC.index("\n}\n", unmount_at)]
    assert "_adapter" not in body, (
        "unmount() releases the scene, not the state: clearing office state on "
        "the way out would show an empty floor for a run still in flight"
    )
