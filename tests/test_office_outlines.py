"""Progress outlines and connector lines.

A dashed line joins each pod to the conductor and marches while the pod is
working, going still once it finishes. `makeSlabOutline` -- a matching dashed
line traced around a pod's own edge -- is the same underlying machinery and
is pinned here too, even though scene.js no longer draws one around a pod
(reported as visibly "sticking out" past the floor's corners; a working
pod's glow is the only "this is active" cue on the floor now, see
docs/rfcs/office-visualization.md).

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
const builders = await import(process.argv[2]);
const { makeSlabOutline, marchOutline, setOutlineActive, advanceDashFade,
  isDashActive, makeConnector, material } = builders;

const palette = {
  outlineIdle: '#111111', outlineActive: '#00ff00', connector: '#222222',
  bridgeDeck: '#090a0c', bridgeBeam: '#020304',
};
const input = JSON.parse(process.argv[3] || '{}');
const out = {};
out.unlitMaterialHasMetalness = Object.hasOwn(material('#111111', { unlit: true }), 'metalness');

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
out.connectorIdleOpacity = connector.material.opacity;
setOutlineActive(connector, true);
out.connectorOpacityImmediatelyAfterSwitch = connector.material.opacity;
advanceDashFade(connector, 120);
out.connectorOpacityMidFade = connector.material.opacity;
advanceDashFade(connector, 5000);
out.connectorActiveAfter = isDashActive(connector);
out.connectorLitColor = connector.material.color.getHexString();
out.connectorLitOpacity = connector.material.opacity;

const floorRoute = builders.makeRouteConnector ? builders.makeRouteConnector([
  { from: { x: 1, z: 2 }, to: { x: 5, z: 6 }, fromTopY: 0.46, toTopY: 0.18 },
  { from: { x: 5, z: 6 }, to: { x: 30, z: 40 }, fromTopY: 0.18, toTopY: 0.18 },
], palette) : { userData: { dashedLines: [] } };
out.floorRouteLineCount = floorRoute.userData.dashedLines.length;
out.floorRoutePoints = floorRoute.userData.dashedLines.map(line =>
  Array.from(line.geometry.getAttribute('position').array));

const bridge = builders.makeBridgeSegment(12, palette, {
  railTrimStart: 1,
  railTrimEnd: 1,
});
const bridgeDeck = bridge.children[0];
const bridgeBeam = bridge.children[1];
out.bridgeDeckColor = bridgeDeck.material.color.getHexString();
out.bridgeDeckMaterialType = bridgeDeck.material.type;
const bridgePoints = Array.from(bridgeDeck.geometry.getAttribute('position').array)
  .reduce((points, value, index, values) => {
    if (index % 3 === 0) points.push({ x: value, z: values[index + 2] });
    return points;
  }, []);
const zMin = Math.min(...bridgePoints.map(point => point.z));
const zMax = Math.max(...bridgePoints.map(point => point.z));
const capWidth = (z) => {
  const cap = bridgePoints.filter(point => Math.abs(point.z - z) < 0.001);
  return Math.max(...cap.map(point => point.x)) - Math.min(...cap.map(point => point.x));
};
out.bridgeEndWidths = [capWidth(zMin), capWidth(zMax)];
out.bridgeMaximumWidth = Math.max(...bridgePoints.map(point => point.x))
  - Math.min(...bridgePoints.map(point => point.x));
bridgeBeam.geometry.computeBoundingBox();
out.bridgeBeamWidth = bridgeBeam.geometry.boundingBox.max.x - bridgeBeam.geometry.boundingBox.min.x;
const bridgeRails = bridge.children.filter(child => child.userData && child.userData.bridgeRail);
out.bridgeRailCount = bridgeRails.length;
out.bridgeRailXs = bridgeRails.map(rail => rail.position.x).sort((a, b) => a - b);
out.bridgeRailColors = bridgeRails.map(rail => rail.material.color.getHexString()).sort();
out.bridgeRailMaterialTypes = bridgeRails.map(rail => rail.material.type);
out.bridgeRailLengths = bridgeRails.map(rail => {
  rail.geometry.computeBoundingBox();
  return rail.geometry.boundingBox.max.z - rail.geometry.boundingBox.min.z;
});
out.bridgeRailTops = bridgeRails.map(rail => {
  rail.geometry.computeBoundingBox();
  return rail.position.y + rail.geometry.boundingBox.max.y;
});
const asymmetricalBridge = builders.makeBridgeSegment(12, palette, {
  railTrimStart: 1,
  railTrimEnd: 0,
});
out.asymmetricalRailCenters = asymmetricalBridge.children
  .filter(child => child.userData && child.userData.bridgeRail)
  .map(rail => rail.position.z);
const trimmedBridge = builders.makeBridgeSegment(12, palette, {
  railColor: '#ff00ff', railTrimStart: 0.6, railTrimEnd: 0.6,
});
const trimmedRails = trimmedBridge.children
  .filter(child => child.material && child.material.color
    && child.material.color.getHexString() === 'ff00ff');
out.trimmedRailLengths = trimmedRails.map(rail => {
  rail.geometry.computeBoundingBox();
  return rail.geometry.boundingBox.max.z - rail.geometry.boundingBox.min.z;
});
out.trimmedRailCenters = trimmedRails.map(rail => rail.position.z);
const fullLengthBridge = builders.makeBridgeSegment(12, palette, {
  railColor: '#00ffff',
});
const fullLengthRails = fullLengthBridge.children
  .filter(child => child.material && child.material.color
    && child.material.color.getHexString() === '00ffff');
out.fullLengthRailLengths = fullLengthRails.map(rail => {
  rail.geometry.computeBoundingBox();
  return rail.geometry.boundingBox.max.z - rail.geometry.boundingBox.min.z;
});
const cableGroup = bridge.children.find(child => child.userData && child.userData.activityChevrons);
const cableLines = cableGroup ? cableGroup.userData.activityChevrons : [];
out.activityCableCount = cableLines.length;
out.activityChevronZs = cableLines.map(line => line.position.z);
out.activityCableActiveBefore = cableLines.map(line => !!line.userData.active);
cableLines.forEach(line => { line.userData.active = true; });
out.activityCableActiveAfter = cableLines.map(line => !!line.userData.active);
const bridgeSegments = bridge.children.filter(child => child.userData && child.userData.bridgeSegment);
out.bridgeSegmentCount = bridgeSegments.length;
out.bridgeSegmentZs = bridgeSegments.map(segment => segment.position.z);
out.bridgeSegmentColors = bridgeSegments.map(segment => segment.material.color.getHexString());
out.bridgeSegmentTops = bridgeSegments.map(segment => {
  segment.geometry.computeBoundingBox();
  return segment.position.y + segment.geometry.boundingBox.max.y;
});
out.bridgePanelZs = bridge.children
  .filter(child => child.userData && child.userData.bridgePanel)
  .map(panel => panel.position.z);
const walkway = builders.makeWalkway(12, palette);
const walkwayDeck = walkway.children[0];
walkwayDeck.geometry.computeBoundingBox();
out.walkwayDeckTop = walkwayDeck.position.y + walkwayDeck.geometry.boundingBox.max.y;
const pod = builders.makePod(10, 6, palette);
out.platformSlabMaterialType = pod.children[0].material.type;
out.platformLayerMaterialTypes = pod.children
  .filter(child => child.userData && child.userData.platformLayer)
  .map(child => child.material.type);

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


def test_a_standard_bridge_charge_sits_above_the_shared_platform_surface(result):
    # The current sits visibly above the 0.6-high platform surface, rather
    # than being lost in the dark bridge deck from the isometric camera.
    points = result["connectorPoints"]
    assert points[1] == pytest.approx(0.66)
    assert points[4] == pytest.approx(0.66)


def test_the_connector_lights_up_like_an_outline(result):
    assert result["connectorActiveBefore"] is False
    assert result["connectorActiveAfter"] is True
    assert result["connectorLitColor"] == "00ff00"
    assert result["connectorLitOpacity"] == pytest.approx(1.0)


def test_an_idle_bridge_is_invisible_and_fades_in(result):
    # Unlike a platform edge (which stays faintly drawn when still), an unlit
    # bridge is not drawn at all — so a delegation starting reads as the charge
    # arriving, easing up from nothing rather than a green line snapping on.
    assert result["connectorIdleOpacity"] == 0
    assert result["connectorOpacityImmediatelyAfterSwitch"] == 0, "eases, not snaps"
    assert 0 < result["connectorOpacityMidFade"] < result["connectorLitOpacity"]


def test_a_floor_charge_follows_each_ramp_and_deck_segment_in_3d(result):
    assert result["floorRouteLineCount"] == 2
    ramp, deck = result["floorRoutePoints"]
    # The charge sits just above the deck surface: the first segment slopes
    # down, then the second keeps that lower elevation all the way to Floor.
    assert ramp[1] > ramp[4]
    assert deck[1] == pytest.approx(deck[4])
    assert ramp[4] == pytest.approx(deck[1])


def test_a_bridge_keeps_a_rectangular_full_width_deck(result):
    # The user wants the original straight-edged bridge silhouette. Its hidden
    # under-rim placement, rather than a tapered cap, is what prevents visible
    # clipping at the platform connection.
    # Square end caps are required: a rounded cap leaves a visibly incomplete
    # connection where the bridge meets the conductor platform.
    assert result["bridgeEndWidths"] == pytest.approx([3.6, 3.6])
    assert result["bridgeMaximumWidth"] == pytest.approx(3.6)
    assert result["bridgeBeamWidth"] == pytest.approx(3.12)


def test_bridge_reverts_to_the_clean_unadorned_deck(result):
    # Revert the coloured outer rails and transverse decoration entirely. The
    # bridge remains a dimensional structural deck, with no visual line layer
    # that can clash with a rounded platform edge.
    assert result["bridgeRailCount"] == 0
    assert result["bridgeSegmentCount"] == 0


def test_bridge_activity_chevrons_are_hidden_until_work_starts_then_march(result):
    assert result["activityCableCount"] >= 3
    assert result["activityChevronZs"] == pytest.approx([-4.5, -2, 0, 2, 4.5])
    assert not any(result["activityCableActiveBefore"])
    assert all(result["activityCableActiveAfter"])


def test_only_the_two_platform_bases_use_unlit_materials(result):
    assert result["platformSlabMaterialType"] != "MeshBasicMaterial"
    assert result["platformLayerMaterialTypes"] == [
        "MeshPhysicalMaterial", "MeshStandardMaterial",
        "MeshPhysicalMaterial", "MeshStandardMaterial",
    ]


def test_unlit_materials_do_not_receive_standard_material_properties(result):
    assert result["unlitMaterialHasMetalness"] is False


def test_bridge_restores_the_first_interior_divider_without_drawing_on_platforms(result):
    # The first interior divider closes the initial deck rectangle at the
    # conductor side; the terminal divider stays omitted at the far platform.
    assert result["bridgePanelZs"] == pytest.approx([-3, -1, 1, 3])


def test_colored_rails_are_trimmed_clear_of_the_platform_rims(result):
    """The deck can continue beneath a platform, but its rails cannot."""
    # Each 0.6-unit rim trim leaves a 10.8-unit visible rail, centred on the
    # full 12-unit deck.
    assert result["trimmedRailLengths"] == pytest.approx([10.8, 10.8])
    assert result["trimmedRailCenters"] == pytest.approx([0, 0])


def test_colored_rails_cover_the_full_untrimmed_bridge_edge(result):
    assert result["fullLengthRailLengths"] == pytest.approx([12, 12])


def test_the_bridge_top_keeps_a_lit_dimensional_charcoal_finish(result):
    # A basic material ignores office lighting and reads as a flat black cutout.
    # Bridge decks should retain the same dark charcoal tone, but respond to
    # light so their top and structural beam remain visually distinguishable.
    assert result["bridgeDeckMaterialType"] == "MeshPhysicalMaterial"
    assert result["bridgeDeckColor"] == "090a0c"


def test_a_walkway_deck_sits_just_below_the_platform_surface(result):
    # Raised platforms finish at y=0.82. The deck top at 0.8 reaches the
    # visible rim while remaining below the platform's top face.
    assert result["walkwayDeckTop"] == pytest.approx(0.8)


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_bridge_lights_with_the_pod_it_feeds():
    assert "const bridge = walkways.get(cluster)" in SCENE_SRC
    assert "if (bridge) setBridgeActive(bridge, record.active)" in SCENE_SRC


# The dashed outline around a pod's own edge was reported as visibly
# "sticking out" past the floor's corners and was removed from scene.js
# entirely (makeSlabOutline itself, and its marching/fade wiring on
# record.outline/conductor.userData.outlineLine, are gone -- a working pod's
# glow, see builders.js's makePodGlow, is the only "this is active" cue on
# the floor now). makeSlabOutline stays defined and tested above as a
# correct, reusable piece of the same dashed-line machinery the connector
# bridges still use; it's simply unused by scene.js today.


def test_bridge_lighting_is_not_a_separate_center_connector():
    # Rails are mounted on the same bridge group as the deck; a separate
    # connector can drift out of alignment when a Floor segment is pitched.
    assert "let connectors = new Map()" not in SCENE_SRC
    assert "ensureConnector(" not in SCENE_SRC


def test_outlines_and_connectors_are_disposed():
    # Both kinds are the same object now, so one branch frees both: each owns
    # its geometry and material outright rather than sharing the caches.
    builders = BUILDERS.read_text(encoding="utf-8")
    at = builders.index("export function disposeTree")
    body = builders[at:at + 1200]
    assert "userData.dashed" in body
    assert "dashed.geometry.dispose()" in body and "dashed.material.dispose()" in body
