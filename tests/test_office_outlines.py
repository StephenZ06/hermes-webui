"""Progress outlines and connector lines.

A platform whose subagents are working traces a marching dashed outline; one
whose work has finished goes still. A thin solid line joins each pod to the
conductor.

three.js imports cleanly under node and these builders touch no DOM, so this
drives the real geometry rather than asserting on source text. The mechanics
are worth pinning because they are not obvious: three's LineDashedMaterial has
no dash offset, so the movement comes from rewriting the line-distance
attribute, and that only works if the base distances are kept and the shift
wraps.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
BUILDERS = REPO / "static" / "office" / "builders.js"
THREE = REPO / "static" / "vendor" / "three" / "0.185.1" / "three.module.min.js"
SCENE_SRC = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

_DRIVER = r"""
const { makeSlabOutline, marchOutline, setOutlineActive, advanceDashFade,
  isDashActive, makeConnector } = await import(process.argv[2]);

const palette = {
  outlineIdle: '#111111', outlineActive: '#00ff00', connector: '#222222',
};
const input = JSON.parse(process.argv[3] || '{}');
const out = {};

const line = makeSlabOutline(input.width || 10, input.depth || 6, palette);
const attr = line.geometry.getAttribute('lineDistance');
out.pointCount = line.geometry.getAttribute('position').count;
out.corners = Array.from(line.geometry.getAttribute('position').array);
out.baseDistances = Array.from(line.userData.dashed.base);
out.period = line.userData.dashed.period;

// BufferAttribute.needsUpdate is set-only in three — reading it gives
// undefined — so the observable proof that an upload was requested is the
// version counter its setter bumps.
out.versionBeforeMarch = attr.version;
for (const offset of (input.marchOffsets || [])) {
  marchOutline(line, offset);
  out['march_' + offset] = Array.from(attr.array);
}
out.versionAfterMarch = attr.version;

// Colour/brightness follow the active flag.
out.idleColor = line.material.color.getHexString();
out.idleOpacity = line.material.opacity;

// Switching on starts an eased transition rather than assigning outright.
setOutlineActive(line, true);
out.colorImmediatelyAfterSwitch = line.material.color.getHexString();
out.activeFlag = line.userData.dashed.active;
advanceDashFade(line, 100);
out.midFadeColor = line.material.color.getHexString();
out.midFadeOpacity = line.material.opacity;
out.stillFading = advanceDashFade(line, 100);
advanceDashFade(line, 5000);
out.activeColor = line.material.color.getHexString();
out.activeOpacity = line.material.opacity;
out.fadeFinished = advanceDashFade(line, 100);

setOutlineActive(line, false);
advanceDashFade(line, 5000);
out.backToIdleColor = line.material.color.getHexString();

const connector = makeConnector(1, 2, 30, 40, palette);
out.connectorPoints = Array.from(connector.geometry.getAttribute('position').array);
out.connectorDashed = connector.material.type === 'LineDashedMaterial';
out.connectorType = connector.material.type;
out.connectorHasDistances = !!connector.geometry.getAttribute('lineDistance');
out.connectorDashSize = connector.material.dashSize;
out.outlineDashSize = line.material.dashSize;
out.connectorActiveBefore = isDashActive(connector);
setOutlineActive(connector, true);
advanceDashFade(connector, 5000);
out.connectorActiveAfter = isDashActive(connector);
out.connectorLitColor = connector.material.color.getHexString();

process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    """Driver plus a resolvable `three`.

    builders.js imports the bare specifier `three`, which the browser resolves
    through the import map in static/index.html. node has no import map, so a
    minimal package re-exporting the vendored build stands in — the real
    builders and the real three, just reachable.
    """
    root = tmp_path_factory.mktemp("office-outline")
    three_pkg = root / "node_modules" / "three"
    three_pkg.mkdir(parents=True)
    (three_pkg / "package.json").write_text(
        json.dumps({"name": "three", "type": "module", "main": "index.mjs"}),
        encoding="utf-8",
    )
    (three_pkg / "index.mjs").write_text(
        f"export * from {json.dumps(THREE.as_uri())};\n", encoding="utf-8")

    # The modules under test are copied beside that package so node resolves
    # `three` from it. Same source, reachable location.
    for name in ("builders.js", "idle.js"):
        (root / name).write_text(
            (REPO / "static" / "office" / name).read_text(encoding="utf-8"),
            encoding="utf-8")

    path = root / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def result(driver):
    proc = subprocess.run(
        [NODE, str(driver), str(driver.parent / "builders.js"),
         json.dumps({"width": 10, "depth": 6, "marchOffsets": [0, 0.5, 1.6, 3.2]})],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


# ── the outline itself ───────────────────────────────────────────────────────

def test_the_outline_closes_the_rectangle(result):
    # Five points, not a LineLoop: computeLineDistances() only measures the
    # segments it is given, so a loop's closing edge would carry no dash
    # pattern at all.
    assert result["pointCount"] == 5
    corners = result["corners"]
    first = corners[0:3]
    last = corners[-3:]
    assert first == last, "the last point repeats the first, closing the loop"


def test_the_outline_traces_the_platform_edge(result):
    xs = {round(v, 4) for v in result["corners"][0::3]}
    zs = {round(v, 4) for v in result["corners"][2::3]}
    assert xs == {-5.0, 5.0}, "half of the 10-unit width"
    assert zs == {-3.0, 3.0}, "half of the 6-unit depth"


def test_line_distances_are_computed_for_every_segment(result):
    base = result["baseDistances"]
    assert base[0] == 0
    assert base == sorted(base), "cumulative distance along the outline"
    assert base[-1] == pytest.approx(32.0), "the full perimeter of a 10x6 rectangle"


# ── marching ─────────────────────────────────────────────────────────────────

def test_marching_shifts_the_whole_pattern(result):
    base = result["baseDistances"]
    shifted = result["march_0.5"]
    assert shifted == pytest.approx([b + 0.5 for b in base]), (
        "three's LineDashedMaterial has no dash offset, so the movement has to "
        "come from the line-distance attribute"
    )


def test_the_attribute_is_flagged_for_upload(result):
    # Rewriting the array without flagging it changes nothing on screen. three
    # exposes needsUpdate as a setter only, so the version its setter bumps is
    # what can actually be observed.
    assert result["versionAfterMarch"] > result["versionBeforeMarch"]


def test_the_shift_wraps_at_one_dash_and_gap(result):
    # Otherwise the offset grows without bound for as long as the panel is
    # open, and float precision decays with it.
    assert result["period"] == pytest.approx(1.6)
    assert result["march_1.6"] == pytest.approx(result["march_0"]), (
        "a full period looks identical to no shift"
    )
    assert result["march_3.2"] == pytest.approx(result["march_0"])


# ── active vs still ──────────────────────────────────────────────────────────

def test_active_and_idle_are_visibly_different(result):
    assert result["idleColor"] == "111111" and result["activeColor"] == "00ff00"
    assert result["activeOpacity"] > result["idleOpacity"]
    assert result["activeFlag"] is True


def test_an_idle_outline_is_still_clearly_there(result):
    # The cue is a *still* outline, not a missing one: a platform whose edge
    # vanishes when its work ends looks broken rather than finished.
    assert result["idleOpacity"] >= 0.5


def test_the_state_can_be_switched_back(result):
    assert result["backToIdleColor"] == "111111"


# ── coming up smoothly ───────────────────────────────────────────────────────

def test_switching_on_does_not_snap(result):
    # A line that jumps from grey to green the instant a subagent spawns reads
    # as a glitch; the same change eased over ~400ms reads as a current
    # arriving.
    assert result["colorImmediatelyAfterSwitch"] == "111111", (
        "the flag flips at once, the appearance does not"
    )


def test_the_transition_passes_through_the_middle(result):
    # Partway through it is neither colour and neither opacity.
    assert result["midFadeColor"] not in ("111111", "00ff00")
    assert result["idleOpacity"] < result["midFadeOpacity"] < result["activeOpacity"]
    assert result["stillFading"] is True


def test_the_transition_finishes_and_stops(result):
    assert result["activeColor"] == "00ff00"
    assert result["fadeFinished"] is False, (
        "a fade that never reports done would be advanced forever"
    )


# ── the connector ────────────────────────────────────────────────────────────

def test_the_connector_spans_the_two_points_it_was_given(result):
    pts = result["connectorPoints"]
    assert [pts[0], pts[2]] == [1, 2]
    assert [pts[3], pts[5]] == [30, 40]


def test_the_connector_carries_the_same_charge_as_the_platforms(result):
    # This reverses an earlier call. The connector was solid so that "these two
    # are connected" read differently from "work is happening here"; showing
    # the charge travelling along the bridge says both at once, and is what
    # was asked for.
    assert result["connectorDashed"] is True
    assert result["connectorType"] == "LineDashedMaterial"
    assert result["connectorHasDistances"], (
        "without line distances a dashed material renders solid"
    )


def test_the_bridge_dashes_are_finer_than_a_platform_edge(result):
    # Identical patterns made the two read as one continuous line where they
    # meet.
    assert result["connectorDashSize"] < result["outlineDashSize"]


def test_the_connector_lights_up_like_an_outline(result):
    assert result["connectorActiveBefore"] is False
    assert result["connectorActiveAfter"] is True
    assert result["connectorLitColor"] == "00ff00"


# ── wiring ───────────────────────────────────────────────────────────────────

def test_only_platforms_with_running_work_march():
    assert "if (record.active) marchOutline(record.outline, marchOffset)" in SCENE_SRC
    assert "worker.status !== 'running'" in SCENE_SRC


def test_the_bridge_lights_with_the_pod_it_feeds():
    assert "if (link) setOutlineActive(link, record.active)" in SCENE_SRC


def test_the_fade_runs_even_when_the_line_is_not_marching():
    # Cutting the transition short mid-way would leave a half-lit colour on
    # screen for as long as the panel stayed open.
    at = SCENE_SRC.index("const marchOffset = t * OUTLINE_SPEED;")
    window = SCENE_SRC[at:at + 900]
    assert window.index("advanceDashFade(record.outline") < window.index("if (record.active)")


def test_a_connector_is_not_rebuilt_unless_it_moves():
    # Recreating it every sync would reset its live state and restart its
    # fade, so a busy run would show a bridge perpetually switching on.
    assert "line.userData.spanKey === key" in SCENE_SRC


def test_the_connector_follows_the_same_span_as_the_walkway():
    # Two cues drawn between different points would visibly disagree.
    assert "ensureConnector(pod.cluster, pod, span)" in SCENE_SRC


def test_outlines_and_connectors_are_disposed():
    # Both kinds are the same object now, so one branch frees both: each owns
    # its geometry and material outright rather than sharing the caches.
    builders = BUILDERS.read_text(encoding="utf-8")
    at = builders.index("export function disposeTree")
    body = builders[at:at + 1200]
    assert "userData.dashed" in body
    assert "dashed.geometry.dispose()" in body and "dashed.material.dispose()" in body
