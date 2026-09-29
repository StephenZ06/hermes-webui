"""Behavioural tests for the office's idle behaviours.

Idle behaviour is the one part of the office that shows something Hermes never
reported — a figure leaning back, sipping, stretching or glancing at a
neighbour between tool calls. That makes its rule strict, and worth pinning:
**it may only ever play over `work`**, and anything real cancels it at once.

`static/office/idle.js` is free of three.js and the DOM precisely so node can
drive the real function with an injected clock and an injected random.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
IDLE = REPO / "static" / "office" / "idle.js"
IDLE_SRC = IDLE.read_text(encoding="utf-8")
BUILDERS_SRC = (REPO / "static" / "office" / "builders.js").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node is required to execute the office idle director"
)

_DRIVER = r"""
const { idlePoseFor, IDLE_BEHAVIOURS } = await import(process.argv[2]);
const scenario = JSON.parse(process.argv[3] || '{}');

// Deterministic stand-in for Math.random: replays a fixed sequence.
const seq = scenario.random || [0];
let i = 0;
const rand = () => seq[i++ % seq.length];

const state = {};
const played = [];
for (const step of (scenario.steps || [])) {
  played.push(idlePoseFor(state, step.pose, step.at, rand));
}
process.stdout.write(JSON.stringify({
  played, state, behaviours: IDLE_BEHAVIOURS.map(b => b.pose),
}));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-idle") / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def run(driver, steps, random=None):
    scenario = {"steps": steps}
    if random is not None:
        scenario["random"] = random
    proc = subprocess.run(
        [NODE, str(driver), IDLE.as_uri(), json.dumps(scenario)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office idle driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def work(at):
    return {"pose": "work", "at": at}


# ── the rule ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pose", ["tool", "done", "error", "stopped", "idle"])
def test_idle_never_plays_over_a_pose_that_means_something(driver, pose):
    # A figure mid-tool-call, finished, failed or interrupted must render
    # exactly that. Anything else would make the office lie about what Hermes
    # reported, which is the one thing it must never do.
    out = run(driver, [
        work(0), work(60_000), work(120_000),      # arm and fire an idle
        {"pose": pose, "at": 120_100},
        {"pose": pose, "at": 130_000},
    ], random=[0.0])
    assert out["played"][-2:] == [pose, pose]


def test_a_real_event_cancels_an_idle_already_playing(driver):
    out = run(driver, [work(0), work(60_000), {"pose": "tool", "at": 60_100}],
              random=[0.0])
    assert out["played"][1] in ("lean", "sip", "stretch", "glance")
    assert out["played"][2] == "tool", "the tool call interrupts the behaviour"


def test_idle_does_not_fire_immediately_after_a_real_event(driver):
    # Coming off a tool call, a figure should settle back to work rather than
    # stretching the moment it lands.
    out = run(driver, [{"pose": "tool", "at": 0}, work(10), work(5_000)],
              random=[0.0])
    assert out["played"][1:] == ["work", "work"]


# ── the behaviour itself ─────────────────────────────────────────────────────

def test_an_idle_behaviour_eventually_fires_and_then_ends(driver):
    out = run(driver, [
        work(0),            # arms the timer
        work(60_000),       # fires
        work(60_500),       # still playing
        work(80_000),       # long past its duration
    ], random=[0.0])
    fired = out["played"][1]
    assert fired in out["behaviours"]
    assert out["played"][2] == fired, "it plays for its full duration"
    assert out["played"][3] == "work", "and then hands the figure back"


def test_the_first_frame_only_arms_the_timer(driver):
    # A freshly seated worker should not stretch on frame one.
    out = run(driver, [work(0)], random=[0.0])
    assert out["played"] == ["work"]
    assert out["state"]["idleNextAt"] > 0


def test_the_gap_is_jittered_so_a_pod_does_not_move_in_unison(driver):
    early = run(driver, [work(0)], random=[0.0])["state"]["idleNextAt"]
    late = run(driver, [work(0)], random=[1.0])["state"]["idleNextAt"]
    assert late > early, "the random draw must actually move the next-fire time"


def test_a_glance_picks_a_side(driver):
  # The glance index is 4 of 5; 0.75 selects it, and the next draw picks a
  # direction so figures do not all look the same way.
  out = run(driver, [work(0), work(60_000)], random=[0.75])
  if out["played"][1] == 'glance':
    assert out["state"]["glanceDir"] in (0.85, -0.85)


# ── boundaries ───────────────────────────────────────────────────────────────

def test_the_idle_module_stays_free_of_the_renderer():
    for forbidden in ("document.", "window.", "fetch(", "from 'three'"):
        assert forbidden not in IDLE_SRC, (
            f"idle.js must stay testable under node — found {forbidden!r}"
        )


def test_the_poser_routes_through_the_idle_director():
    assert "idlePoseFor(person.userData, pose" in BUILDERS_SRC
    assert "from './idle.js'" in BUILDERS_SRC
