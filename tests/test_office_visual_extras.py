"""The visual-polish builders: a pod's working glow and a whiteboard prop.

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
// (mesh/sprite type, blending, dispose tags), never actual pixels, so a
// no-op stub canvas is enough to let the drawing code run without throwing --
// the same reasoning as test_office_pod_color.py's `three` stub.
function fakeCanvas() {
  const noop = () => {};
  return {
    width: 256, height: 160,
    getContext: () => ({
      strokeStyle: '', globalAlpha: 1, lineWidth: 1, fillStyle: '', font: '',
      textAlign: '', textBaseline: '', lineJoin: '',
      beginPath: noop, moveTo: noop, lineTo: noop, stroke: noop, fill: noop,
      closePath: noop, quadraticCurveTo: noop, arc: noop,
      fillText: noop, strokeText: noop, clearRect: noop, fillRect: noop,
      measureText: () => ({ width: 8 }),
    }),
  };
}
globalThis.document = { createElement: () => fakeCanvas() };

const {
  makePodGlow, makeWhiteboard, makeFloorTitle, makeDesk, makeChatBubble,
  drawChatBubble, drawActiveScreen, disposeTree,
} = await import(process.argv[2]);

const palette = {
  board: '#fbfaf6', deskLeg: '#8b8b93', deskTop: '#c9a227',
  screenBezel: '#2c2c34', screenBg: '#14141c', screenActiveBg: '#f7f7fb',
  screenText: '#8fb9a8', screenTextBright: '#d8f0e4',
  mousePad: '#1a1a24', keyboard: '#24242e', keyboardKey: '#9a9aa8', mouse: '#c9c9d6',
  bubbleBg: 'rgba(20,20,30,0.88)', bubbleStroke: 'rgba(180,180,200,0.55)', bubbleText: '#f2f2f7',
  floorTitle: '#8d8d95', floorTitleStroke: 'rgba(0,0,0,0.5)',
};

const glow = makePodGlow(10, 6, '#3f7fd4');
const board = makeWhiteboard(palette);
const title = makeFloorTitle('Sales', 20, palette);
const desk = makeDesk(palette);
const bubble = makeChatBubble(palette);
drawChatBubble(bubble, palette, 'Zzz');
const screen = desk.userData.screen;
let activeScreenOk = false;
try {
  drawActiveScreen(screen, palette, 1.5, 42);
  activeScreenOk = true;
} catch (_err) {
  activeScreenOk = false;
}

const out = {
  glow: {
    isMesh: !!glow.isMesh,
    opacity: glow.material.opacity,
    blending: glow.material.blending,
    // The glow colour is pushed past normal 0-1 range so the bloom pass'
    // high-pass filter actually catches it -- see builders.js's own comment.
    colorMax: Math.max(glow.material.color.r, glow.material.color.g, glow.material.color.b),
    hasDisposeTag: !!glow.userData.podGlow,
    bounds: (() => {
      glow.geometry.computeBoundingBox();
      const box = glow.geometry.boundingBox;
      return { width: box.max.x - box.min.x, depth: box.max.y - box.min.y };
    })(),
  },
  board: {
    isGroup: !!board.isGroup,
    childCount: board.children.length,
    allShadowless: board.children.every(c => c.castShadow === false),
  },
  title: {
    hasMap: !!title.material.map,
    hasDisposeTag: !!title.userData.floorTitle,
  },
  desk: {
    isGroup: !!desk.isGroup,
    hasScreen: !!desk.userData.screen,
    childCount: desk.children.length,
  },
  bubble: {
    isSprite: !!bubble.isSprite,
    hasDisposeTag: !!bubble.userData.bubble,
    icon: bubble.userData.bubble.icon,
  },
  activeScreen: {
    ok: activeScreenOk,
  },
};

disposeTree(glow);
disposeTree(board);
disposeTree(title);
disposeTree(desk);

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


def test_pod_glow_stays_inside_the_platform_footprint(driver):
    glow = run(driver)["glow"]
    assert glow["bounds"]["width"] < 10
    assert glow["bounds"]["depth"] < 6


def test_whiteboard_is_a_small_group_of_shadowless_parts(driver):
    out = run(driver)["board"]
    assert out["isGroup"]
    assert out["childCount"] >= 3, "a board face, a frame, and at least one leg"
    assert out["allShadowless"], (
        "a prop this small isn't worth a shadow-pass render of four more "
        "objects per pod, every frame"
    )


def test_floor_title_still_builds_a_disposable_textured_plane(driver):
    out = run(driver)["title"]
    assert out["hasMap"]
    assert out["hasDisposeTag"]


def test_desk_has_a_screen_and_peripherals(driver):
    out = run(driver)["desk"]
    assert out["isGroup"]
    assert out["hasScreen"]
    assert out["childCount"] >= 7, (
        "desk should include top, legs, screen, stand, keyboard, mouse pad and mouse"
    )


def test_chat_bubble_is_a_sprite_with_a_disposable_tag(driver):
    out = run(driver)["bubble"]
    assert out["isSprite"]
    assert out["hasDisposeTag"]
    assert out["icon"] == 'Zzz'


def test_active_screen_draws_without_throwing(driver):
    out = run(driver)["activeScreen"]
    assert out["ok"]
