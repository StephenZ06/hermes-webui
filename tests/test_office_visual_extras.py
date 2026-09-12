"""The visual-polish builders: a pod's working glow, a whiteboard prop, and
a department's icon painted inline on its own floor sign.

Real three.js under node, same fixture shape as tests/test_office_pod_color.py
and tests/test_office_outlines.py: builders.js imports the bare specifier
"three", which the browser resolves through index.html's import map; node has
no import map, so a minimal package re-exporting the vendored build stands in.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
THREE = REPO / "static" / "vendor" / "three" / "0.185.1" / "three.module.min.js"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

_DRIVER = r"""
// makeFloorTitle draws to a 2D canvas -- something node has no native
// concept of. This test only checks the resulting THREE objects' structure
// (mesh/sprite type, blending, dispose tags, geometry aspect ratio), never
// actual pixels, so a no-op stub canvas is enough to let the drawing code
// run without throwing -- the same reasoning as test_office_pod_color.py's
// `three` stub. measureText answers a fixed width per call so the icon-vs-
// text width math the driver checks stays predictable.
function fakeCanvas() {
  const noop = () => {};
  return {
    width: 0, height: 0,
    getContext: () => ({
      strokeStyle: '', globalAlpha: 1, lineWidth: 1, fillStyle: '', font: '',
      textAlign: '', textBaseline: '', lineJoin: '',
      beginPath: noop, moveTo: noop, lineTo: noop, stroke: noop,
      fillText: noop, strokeText: noop,
      measureText: () => ({ width: 8 }),
    }),
  };
}
globalThis.document = { createElement: () => fakeCanvas() };

const {
  makePodGlow, makeWhiteboard, makeFloorTitle, disposeTree,
} = await import(process.argv[2]);

const palette = {
  board: '#fbfaf6', deskLeg: '#8b8b93',
  floorTitle: '#8d8d95', floorTitleStroke: 'rgba(0,0,0,0.5)',
};

const glow = makePodGlow(10, 6, '#3f7fd4');
const board = makeWhiteboard(palette);
const plain = makeFloorTitle('Sales', 20, palette);
const iconed = makeFloorTitle('Sales', 20, palette, { icon: '\u{1F4B0}' });

const out = {
  glow: {
    isMesh: !!glow.isMesh,
    opacity: glow.material.opacity,
    blending: glow.material.blending,
    // The glow colour is pushed past normal 0-1 range so the bloom pass'
    // high-pass filter actually catches it -- see builders.js's own comment.
    colorMax: Math.max(glow.material.color.r, glow.material.color.g, glow.material.color.b),
    hasDisposeTag: !!glow.userData.podGlow,
  },
  board: {
    isGroup: !!board.isGroup,
    childCount: board.children.length,
    allShadowless: board.children.every(c => c.castShadow === false),
  },
  title: {
    plainHasMap: !!plain.material.map,
    hasDisposeTag: !!plain.userData.floorTitle,
    iconedHasDisposeTag: !!iconed.userData.floorTitle,
    // An icon adds width to the same single-line sign rather than height --
    // no separate band, no separate floating object.
    sameHeight: iconed.geometry.parameters.height === plain.geometry.parameters.height,
  },
};

disposeTree(glow);
disposeTree(board);
disposeTree(plain);
disposeTree(iconed);

process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    """Driver plus a resolvable `three`, mirroring test_office_pod_color.py."""
    root = tmp_path_factory.mktemp("office-visual-extras")
    three_pkg = root / "node_modules" / "three"
    three_pkg.mkdir(parents=True)
    (three_pkg / "package.json").write_text(
        json.dumps({"name": "three", "type": "module", "main": "index.mjs"}),
        encoding="utf-8",
    )
    (three_pkg / "index.mjs").write_text(
        f"export * from {json.dumps(THREE.as_uri())};\n", encoding="utf-8")

    for name in ("builders.js", "idle.js"):
        (root / name).write_text(
            (REPO / "static" / "office" / name).read_text(encoding="utf-8"),
            encoding="utf-8")

    path = root / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def run(driver):
    proc = subprocess.run(
        [NODE, str(driver), (driver.parent / "builders.js").as_uri()],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office visual-extras driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def test_pod_glow_starts_invisible_and_additive_and_hdr(driver):
    out = run(driver)["glow"]
    assert out["isMesh"]
    assert out["opacity"] == 0, "a pod that isn't working starts with no glow at all"
    assert out["blending"] == 2, "THREE.AdditiveBlending, so overlapping glows add light rather than occlude"
    assert out["colorMax"] > 1, "pushed past normal range so the bloom pass' threshold actually catches it"
    assert out["hasDisposeTag"]


def test_whiteboard_is_a_small_group_of_shadowless_parts(driver):
    out = run(driver)["board"]
    assert out["isGroup"]
    assert out["childCount"] >= 3, "a board face, a frame, and at least one leg"
    assert out["allShadowless"], (
        "a prop this small isn't worth a shadow-pass render of four more "
        "objects per pod, every frame"
    )


def test_floor_title_accepts_an_icon_without_growing_into_a_separate_band(driver):
    out = run(driver)["title"]
    assert out["plainHasMap"]
    assert out["hasDisposeTag"]
    assert out["iconedHasDisposeTag"]
    assert out["sameHeight"], "the icon must not grow the sign into a taller plane"
