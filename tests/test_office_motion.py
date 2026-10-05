"""Figures on their feet: the conductor pacing, and subagents walking in.

Two kinds of movement, and the distinction carries the honesty rule the whole
office is built on:

* **Wandering** is what a figure does when it has nothing to do — the
  conductor between delegations. A walking figure reads as activity, so this
  must never be driven by a worker that is running.
* **Arrival** is a subagent walking to its desk when it spawns. That is a real
  event the office is entitled to show, and it ends the moment it sits down.

`static/office/motion.js` is free of three.js and the DOM so node drives the
real thing with an injected clock and an injected random.
"""
import json
import math
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
MOTION = REPO / "static" / "office" / "motion.js"
MOTION_SRC = MOTION.read_text(encoding="utf-8")
SCENE_SRC = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")
BUILDERS_SRC = (REPO / "static" / "office" / "builders.js").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

_DRIVER = r"""
const { createWanderer, createArrival, advanceArrival, arrivalSettle } =
  await import(process.argv[2]);
const input = JSON.parse(process.argv[3] || '{}');

const seq = input.random || [0.5];
let i = 0;
const rand = () => seq[i++ % seq.length];
const out = {};

if (input.wander) {
  const w = createWanderer(Object.assign({ rand }, input.wander.options || {}));
  const track = [];
  for (const step of input.wander.steps) {
    if (step.moveTo) out.arrivedAtCentre = w.moveTo(step.moveTo[0], step.moveTo[1], step.ms);
    else w.update(step.ms);
    track.push({
      x: w.state.x, z: w.state.z, moving: w.state.moving,
      heading: w.state.heading, phase: w.state.phase,
    });
  }
  out.track = track;
}

if (input.arrival) {
  const a = createArrival(input.arrival.distance, input.arrival.speed,
                          input.arrival.lateral);
  const track = [];
  for (const ms of input.arrival.steps) {
    advanceArrival(a, ms);
    track.push({ offset: a.offset, done: a.done, phase: a.phase,
                 lateral: a.lateral, settle: arrivalSettle(a) });
  }
  out.arrival = track;
}

process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-motion") / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def run(driver, **payload):
    proc = subprocess.run(
        [NODE, str(driver), MOTION.as_uri(), json.dumps(payload)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def wander(driver, steps, random=None, **options):
    return run(driver, wander={"steps": steps, "options": options},
               random=random)["track"]


# ── pacing ───────────────────────────────────────────────────────────────────

def test_a_wanderer_starts_still(driver):
    track = wander(driver, [{"ms": 100}], pauseMinMs=1000)
    assert track[0]["moving"] is False
    assert (track[0]["x"], track[0]["z"]) == (0, 0)


def test_it_starts_walking_once_the_pause_elapses(driver):
    track = wander(driver, [{"ms": 500}, {"ms": 700}, {"ms": 200}],
                   random=[0.5], pauseMinMs=1000, pauseMaxMs=1000)
    assert track[0]["moving"] is False, "still pausing"
    assert track[2]["moving"] is True, "walking after the pause"
    assert (track[2]["x"], track[2]["z"]) != (0, 0)


def test_it_stays_inside_its_circle(driver):
    # The conductor paces its own plinth; wandering off it would look like it
    # had left the building.
    steps = [{"ms": 120} for _ in range(400)]
    track = wander(driver, steps, random=[0.05, 0.9, 0.4, 0.77, 0.2, 0.6],
                   radius=4.0, pauseMinMs=200, pauseMaxMs=400)
    worst = max(math.hypot(p["x"], p["z"]) for p in track)
    assert worst <= 4.0 + 1e-6, f"walked {worst:.3f} from the centre of a 4.0 circle"


def test_it_faces_where_it_is_going(driver):
    track = wander(driver, [{"ms": 1100}, {"ms": 300}],
                   random=[0.125, 0.9], pauseMinMs=1000, pauseMaxMs=1000)
    moving = track[-1]
    # heading is atan2(dx, dz), so this is the direction of travel.
    assert moving["moving"] is True
    assert math.isclose(math.atan2(moving["x"], moving["z"]), moving["heading"],
                        abs_tol=1e-6)


def test_the_stride_advances_with_distance_not_time(driver):
    # Phase drives the gait; tying it to elapsed time would change the walk
    # whenever the frame rate did.
    track = wander(driver, [{"ms": 1100}, {"ms": 200}, {"ms": 200}],
                   random=[0.5], pauseMinMs=1000, pauseMaxMs=1000, speed=2.0)
    walked = math.hypot(track[2]["x"] - track[1]["x"], track[2]["z"] - track[1]["z"])
    assert math.isclose(track[2]["phase"] - track[1]["phase"], walked, abs_tol=1e-6)


def test_it_pauses_again_on_arrival(driver):
    track = wander(driver, [{"ms": 1100}] + [{"ms": 400} for _ in range(30)],
                   random=[0.5, 0.5], pauseMinMs=1000, pauseMaxMs=1000)
    assert any(p["moving"] is False for p in track[2:]), (
        "a figure that never stops is jogging, not pacing"
    )


def test_walking_to_a_fixed_point_reports_arrival(driver):
    out = run(driver, wander={
        "steps": [{"moveTo": [0, 0], "ms": 50}],
        "options": {"speed": 2.0},
    })
    assert out["arrivedAtCentre"] is True, "already at the centre"


# ── arriving at a desk ───────────────────────────────────────────────────────

def test_a_subagent_walks_in_and_sits_down(driver):
    out = run(driver, arrival={"distance": 9, "speed": 6.5,
                               "steps": [200] * 12})["arrival"]
    assert out[0]["offset"] < 9, "it moves"
    assert out[0]["done"] is False
    assert out[-1]["done"] is True and out[-1]["offset"] == 0, (
        "and ends seated exactly, not somewhere near the chair"
    )


def test_the_walk_settles_rather_than_stopping_mid_stride(driver):
    out = run(driver, arrival={"distance": 9, "speed": 6.5,
                               "steps": [100] * 20})["arrival"]
    settles = [p["settle"] for p in out if not p["done"]]
    assert settles[0] == 1.0, "full stride while still crossing the floor"
    assert settles[-1] < 1.0, "eased out as the chair approaches"
    assert out[-1]["settle"] == 0, "and nothing left once seated"


def test_the_walk_in_comes_from_the_aisle_and_merges_to_the_chair(driver):
    # Straight-behind arrivals walked through the monitor and chair of the row
    # behind. Now the figure starts out to one side and only crosses back onto
    # the desk's centre line for the last stretch.
    out = run(driver, arrival={"distance": 12, "speed": 6.5, "lateral": 5,
                               "steps": [80] * 24})["arrival"]
    assert out[0]["lateral"] == pytest.approx(5), "starts out in the aisle"
    assert out[-1]["done"] is True
    assert out[-1]["lateral"] == pytest.approx(0), "ends on the centre line, in the chair"
    # Monotonic taper toward 0 as the chair approaches.
    laterals = [abs(p["lateral"]) for p in out]
    assert laterals == sorted(laterals, reverse=True)


def test_a_straight_walk_in_still_has_no_lateral(driver):
    out = run(driver, arrival={"distance": 9, "speed": 6.5, "steps": [200] * 8})["arrival"]
    assert all(p["lateral"] == 0 for p in out)


def test_an_arrival_that_is_done_stays_done(driver):
    out = run(driver, arrival={"distance": 1, "speed": 6.5,
                               "steps": [500, 500, 500]})["arrival"]
    assert [p["done"] for p in out] == [True, True, True]
    assert out[-1]["offset"] == 0


# ── the honesty rule ─────────────────────────────────────────────────────────

def test_only_an_idle_conductor_wanders():
    # A walking figure reads as activity. The conductor walks when it has
    # nothing to do, and walks back to the middle when it does.
    at = SCENE_SRC.index("const orchestrating = conductor.userData.status")
    body = SCENE_SRC[at:at + 1400]
    assert "if (orchestrating)" in body
    assert "wanderer.moveTo(0, 0, dtMs)" in body, "returns to the middle to work"
    assert "wanderer.update(dtMs)" in body, "and paces only in the other branch"


def test_a_seated_worker_never_shows_legs():
    # poseWorker covers every desk-bound state and hides legs unless the caller
    # says the figure is standing (only the deskless conductor does). The
    # behaviour itself is checked in tests/test_office_conductor_legs.py.
    at = BUILDERS_SRC.index("export function poseWorker(")
    body = BUILDERS_SRC[at:at + 600]
    assert "const standing = !!(opts && opts.standing);" in body
    assert "joints.legs.visible = standing" in body


def test_arrival_is_driven_before_the_working_pose():
    # While walking in, the figure's posture is the walk — not whatever Hermes
    # says the subagent is doing, which it has not started yet.
    at = SCENE_SRC.index("if (seat.arrival && !seat.arrival.done)")
    body = SCENE_SRC[at:at + 900]
    assert "poseWalking(seat.person" in body
    assert body.index("return;") < body.index("poseWorker") if "poseWorker" in body else True


def test_walk_in_start_positions_are_kept_inside_their_own_pod():
    # A fixed nine-unit spawn offset was outside a one-row pod, so workers
    # visibly floated over the main floor before reaching their desk. Arrival
    # setup must use each seat's actual pod bounds before it starts walking.
    assert "function configureSeatArrival(" in SCENE_SRC
    assert "maxDistanceInsidePod(" in SCENE_SRC
    assert "layout.pods" in SCENE_SRC


def test_motion_stays_free_of_the_renderer():
    for forbidden in ("document.", "window.", "fetch(", "from 'three'"):
        assert forbidden not in MOTION_SRC, (
            f"motion.js must stay testable under node — found {forbidden!r}"
        )
