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
    # Desk reclaim only comes up while something is still running: once every
    # worker is terminal the floor is cleared for the next run instead (see
    # test_a_new_run_starts_on_a_clean_floor). So `live` holds the office open.
    #
    # c1 (parent p1) finishes first, so by age alone its desk would be the one
    # reclaimed. c3 belongs to p2's cluster, and keeping siblings together
    # wins: it takes c2's desk instead.
    out = run(driver, [
        spawn("live"),
        spawn("c1", parent_id="p1"),
        spawn("c2", parent_id="p2"),
        complete("c1"),
        {"op": "advance", "ms": 5000},
        complete("c2"),
        {"op": "advance", "ms": 10},
        spawn("c3", parent_id="p2"),
    ], options={"maxDesks": 3})
    desks = {d["id"]: d for d in out["state"]["desks"]}
    assert desks["desk-2"]["workerId"] == "c3", (
        "desk-2 was p2's cluster; c3 is p2's child and should sit there"
    )
    assert worker(out["state"], "c1")["deskId"] == "desk-1", "c1 keeps its seat"


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
    # b is still running, so this is cap pressure rather than a new run.
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
    # `live` keeps the office from being cleared wholesale, so the cap is what
    # decides who loses a desk.
    out = run(driver, [
        spawn("live"), spawn("a"), spawn("b"),
        complete("a"),
        {"op": "advance", "ms": 5000},
        complete("b"),
        {"op": "advance", "ms": 10},
        spawn("c"),
    ], options={"maxDesks": 3})
    assert worker(out["state"], "c")["deskId"] == "desk-1"
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


def test_snapshot_still_applies_without_a_gateway_process(driver):
    # `gateway_enabled: false` does NOT mean "no data". The single-container
    # deployment answers /api/subagents/active from tools.delegate_tool's own
    # in-process registry and reports a fully populated `active` list next to
    # that flag (api/routes.py, 2026-08-26). Skipping on it made reconcile a
    # permanent no-op for exactly the deployment that needs it most: with no
    # gateway process, a fire-and-forget subagent that finishes after its
    # parent's stream closed has no other way to be noticed.
    out = run(driver, [{"op": "snapshot", "payload": {
        "gateway_enabled": False, "spawn_paused": False,
        "active": [{"subagent_id": "a", "goal": "in-process child", "status": "running"}],
    }}])
    assert [w["id"] for w in out["state"]["workers"]] == ["a"]


def test_a_failing_snapshot_does_not_report_spawning_as_unpaused(driver):
    # A 502 from the gateway returns an empty `active` with spawn_paused:false.
    # That is an error, not a fact about pausing, and taking it at face value
    # would silently flip the pause control back on a failed poll.
    out = run(driver, [
        {"op": "snapshot", "payload": {"gateway_enabled": True, "spawn_paused": True, "active": []}},
        {"op": "snapshot", "payload": {
            "gateway_enabled": True, "spawn_paused": False, "active": [],
            "error": "gateway unreachable",
        }},
    ])
    assert out["state"]["spawnPaused"] is True


# ── retiring a subagent that vanished from the registry ──────────────────────

def snapshot(*ids, **fields):
    payload = {
        "gateway_enabled": True,
        "active": [{"subagent_id": i, "goal": f"goal for {i}", "status": "running"}
                   for i in ids],
    }
    payload.update(fields)
    return {"op": "snapshot", "payload": payload}


def test_a_subagent_that_leaves_the_registry_is_retired(driver):
    # delegate_tool's _unregister_subagent removes a child from the live
    # registry the moment it finishes, so a completed subagent does not appear
    # in /api/subagents/active with a terminal status — it just disappears.
    # Absence is therefore the only completion signal the snapshot carries, and
    # without acting on it a fire-and-forget child whose completion event never
    # arrived sits at "running" forever. That was a real, user-reported bug.
    out = run(driver, [snapshot("a", "b"), snapshot("a"), snapshot("a")])
    assert worker(out["state"], "b")["status"] == "ended"
    assert worker(out["state"], "b")["pose"] == "done"
    assert worker(out["state"], "a")["status"] == "running"


def test_retirement_says_ended_not_completed(driver):
    # We know it stopped. We never saw how it went. Calling it 'completed'
    # would invent a result nobody reported.
    out = run(driver, [snapshot("a"), snapshot(), snapshot()])
    w = worker(out["state"], "a")
    assert w["status"] == "ended"
    assert w["summary"] == "" and w["durationSeconds"] is None


def test_one_missing_snapshot_is_not_enough_to_retire(driver):
    # A single partial or racing snapshot must not retire a live worker.
    out = run(driver, [snapshot("a"), snapshot()])
    assert worker(out["state"], "a")["status"] == "running"


def test_a_worker_that_reappears_is_not_retired(driver):
    out = run(driver, [snapshot("a"), snapshot(), snapshot("a"), snapshot()])
    assert worker(out["state"], "a")["status"] == "running"


def test_a_failing_snapshot_never_retires_anyone(driver):
    # A 502 returns an empty `active`. Treating that as "everyone finished"
    # would wipe the whole office on one bad poll.
    out = run(driver, [
        snapshot("a"),
        snapshot(error="gateway unreachable"),
        snapshot(error="gateway unreachable"),
        snapshot(error="gateway unreachable"),
    ])
    assert worker(out["state"], "a")["status"] == "running"


def test_a_worker_known_only_from_the_stream_is_never_retired(driver):
    # Snapshots may not cover everything the SSE stream reports. Absence from
    # a list that never claimed to include this worker says nothing.
    out = run(driver, [spawn("sse-only"), snapshot(), snapshot(), snapshot()])
    assert worker(out["state"], "sse-only")["status"] == "running"


def test_a_real_completion_still_wins_over_retirement(driver):
    # The completion event carries the actual result; retirement is only the
    # fallback for when it never arrives.
    out = run(driver, [
        snapshot("a"),
        complete("a", status="ok", summary="did the thing", duration_seconds=4),
        snapshot(), snapshot(),
    ])
    w = worker(out["state"], "a")
    assert w["status"] == "completed" and w["summary"] == "did the thing"


# ── finished workers leaving ─────────────────────────────────────────────────

def test_a_finished_worker_leaves_after_its_linger(driver):
    # Reported from real use: finished subagents kept their desks, so a second
    # delegation stacked on top of the first and the floor only ever grew.
    out = run(driver, [
        spawn("a"), complete("a"),
        {"op": "advance", "ms": 26_000},
        {"op": "tick"},
    ], options={"completedLingerMs": 25_000})
    assert out["state"]["workers"] == []
    assert out["state"]["desks"] == [], "the desk goes with the worker"
    assert "worker.remove" in types(out)


def test_it_stays_long_enough_to_be_read(driver):
    # Removing on completion would mean never seeing the result, or even the
    # tick that says it finished.
    out = run(driver, [
        spawn("a"), complete("a", summary="found it"),
        {"op": "advance", "ms": 5_000},
        {"op": "tick"},
    ], options={"completedLingerMs": 25_000})
    w = worker(out["state"], "a")
    assert w["status"] == "completed" and w["summary"] == "found it"


def test_a_running_worker_is_never_swept(driver):
    out = run(driver, [
        spawn("a"), spawn("b"), complete("b"),
        {"op": "advance", "ms": 60_000},
        {"op": "tick"},
    ], options={"completedLingerMs": 25_000})
    assert [w["id"] for w in out["state"]["workers"]] == ["a"]


def test_a_new_run_starts_on_a_clean_floor(driver):
    # The linger alone is not enough: delegate again inside it and the two
    # runs would share the floor.
    out = run(driver, [
        spawn("a"), spawn("b"), complete("a"), complete("b"),
        {"op": "advance", "ms": 1_000},
        spawn("c"),
    ], options={"completedLingerMs": 25_000})
    assert [w["id"] for w in out["state"]["workers"]] == ["c"]
    assert len(out["state"]["desks"]) == 1


def test_a_spawn_mid_run_clears_nothing(driver):
    # A sibling in the same batch, or a nested child, arrives while others are
    # still working. Clearing then would erase live work.
    out = run(driver, [
        spawn("a"), spawn("b"), complete("b"),
        spawn("c"),
    ], options={"completedLingerMs": 25_000})
    assert {w["id"] for w in out["state"]["workers"]} == {"a", "b", "c"}


def test_by_default_a_finished_run_stays_until_the_next_one(driver):
    # The default is no timed sweep at all. One was tried and was wrong: it
    # deleted the desks, the goals on their nameplates and the completion
    # summaries while the user was still reading them. Stacking is handled by
    # clearing on the next run, which is the moment the old one stops being
    # what you are looking at.
    out = run(driver, [
        spawn("a"), complete("a", summary="found it"),
        {"op": "advance", "ms": 10_000_000},
        {"op": "tick"},
    ])
    w = worker(out["state"], "a")
    assert w["status"] == "completed" and w["summary"] == "found it"
    assert w["goal"], "the goal is what the nameplate reads"
    assert len(out["state"]["desks"]) == 1, "and it keeps its desk"


def test_a_zero_linger_keeps_everyone(driver):
    # Also what the historical replay asks for explicitly.
    out = run(driver, [
        spawn("a"), complete("a"),
        {"op": "advance", "ms": 10_000_000},
        {"op": "tick"},
    ], options={"completedLingerMs": 0})
    assert len(out["state"]["workers"]) == 1


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
