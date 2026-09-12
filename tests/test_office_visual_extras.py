"""The visual-polish builders: floor tiles, a pod's working glow, a
whiteboard prop, and a department's floating icon badge.

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
// makeFloorTiles and makeDeptIcon draw to a 2D canvas -- something node has
// no native concept of. This test only checks the resulting THREE objects'
// structure (mesh/sprite type, blending, dispose tags), never actual pixels,
// so a no-op stub canvas is enough to let the drawing code run without
// throwing -- the same reasoning as test_office_pod_color.py's `three` stub.
function fakeCanvas() {
  const noop = () => {};
  return {
    width: 0, height: 0,
    getContext: () => ({
      strokeStyle: '', globalAlpha: 1, lineWidth: 1, fillStyle: '', font: '',
      textAlign: '', textBaseline: '',
      beginPath: noop, moveTo: noop, lineTo: noop, stroke: noop, fillText: noop,
      measureText: () => ({ width: 8 }),
    }),
  };
}
globalThis.document = { createElement: () => fakeCanvas() };

const {
  makeFloorTiles, makePodGlow, makeWhiteboard, makeDeptIcon, disposeTree,
} = await import(process.argv[2]);

const palette = {
  grid: '#d8d3c8', board: '#fbfaf6', deskLeg: '#8b8b93',
};

const tiles = makeFloorTiles(10, 6, palette);
const glow = makePodGlow(10, 6, '#3f7fd4');
const board = makeWhiteboard(palette);
const icon = makeDeptIcon('\u{1F4E6}');

const out = {
  tiles: {
    isMesh: !!tiles.isMesh,
    hasMap: !!tiles.material.map,
    opacity: tiles.material.opacity,
    hasDisposeTag: !!tiles.userData.floorTiles,
  },
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
  },
  icon: {
    isSprite: !!icon.isSprite,
    hasDisposeTag: !!icon.userData.plate,
  },
};

// disposeTree must not throw on any of these -- each carries GPU resources
// this test never explicitly frees otherwise.
disposeTree(tiles);
disposeTree(glow);
disposeTree(board);
disposeTree(icon);

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


def test_floor_tiles_are_a_faint_textured_overlay(driver):
    out = run(driver)["tiles"]
    assert out["isMesh"]
    assert out["hasMap"], "the grid pattern is a canvas texture, not a flat colour"
    assert 0 < out["opacity"] < 1, "a floor finish detail, not an opaque plate"
    assert out["hasDisposeTag"], "disposeTree must find and release its texture/geometry/material"


def test_pod_glow_starts_invisible_and_additive_and_hdr(driver):
    out = run(driver)["glow"]
    assert out["isMesh"]
    assert out["opacity"] == 0, "a pod that isn't working starts with no glow at all"
    assert out["blending"] == 2, "THREE.AdditiveBlending, so overlapping glows add light rather than occlude"
    assert out["colorMax"] > 1, "pushed past normal range so the bloom pass' threshold actually catches it"
    assert out["hasDisposeTag"]


def test_whiteboard_is_a_small_group_of_parts(driver):
    out = run(driver)["board"]
    assert out["isGroup"]
    assert out["childCount"] >= 3, "a board face, a frame, and at least one leg"


def test_dept_icon_is_a_billboarded_sprite(driver):
    out = run(driver)["icon"]
    assert out["isSprite"], "a sprite always faces the camera, unlike a flat floor plane"
    assert out["hasDisposeTag"]
