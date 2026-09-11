"""A Business department's floor colour (builders.js's makePod tint).

Reported: the reference product (github.com/ajsahni/agents-office, visual
reference only per docs/rfcs/office-visualization.md's Licensing section —
this repo is MIT, that one is PolyForm Noncommercial, so this is hand-written
against the same idea, not copied code) gives each department floor its own
colour. `roster.js`'s DEPARTMENTS now carry one; this pins that `makePod`
actually blends it into the palette's own pod colours rather than either
ignoring it or painting a flat, theme-unaware colour over the floor.

three.js imports cleanly under node and touches no DOM, so this drives the
real geometry the same way tests/test_office_outlines.py does.
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
const { makePod } = await import(process.argv[2]);

const palette = { podTop: '#ffffff', podSide: '#e4dfd4' };
const input = JSON.parse(process.argv[3] || '{}');

const pod = makePod(10, 6, palette, input.tint || null);
const [slab, skirt] = pod.children;
process.stdout.write(JSON.stringify({
  slabColor: '#' + slab.material.color.getHexString(),
  skirtColor: '#' + skirt.material.color.getHexString(),
}));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    """Driver plus a resolvable `three` -- same fixture shape as
    tests/test_office_outlines.py: builders.js imports the bare specifier
    `three`, which the browser resolves through index.html's import map;
    node has no import map, so a minimal package re-exporting the vendored
    build stands in, reachable from a copy of builders.js placed beside it."""
    root = tmp_path_factory.mktemp("office-pod-color")
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


def run(driver, **payload):
    proc = subprocess.run(
        [NODE, str(driver), (driver.parent / "builders.js").as_uri(), json.dumps(payload)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office pod-color driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def test_no_tint_keeps_the_plain_palette_colour(driver):
    out = run(driver)
    assert out["slabColor"] == "#ffffff"
    assert out["skirtColor"] == "#e4dfd4"


def test_a_tint_is_blended_not_painted_flat(driver):
    out = run(driver, tint="#c9758a")
    # Changed from the untinted palette colour...
    assert out["slabColor"] != "#ffffff"
    assert out["skirtColor"] != "#e4dfd4"
    # ...but not simply replaced by the raw tint either -- a flat swap would
    # make every department's floor the same brand-colour slab regardless of
    # the active theme, instead of a tinted version of that theme's own pod
    # material.
    assert out["slabColor"] != "#c9758a"
    assert out["skirtColor"] != "#c9758a"


def test_two_departments_get_two_different_floor_colours(driver):
    marketing = run(driver, tint="#c9758a")["slabColor"]
    finance = run(driver, tint="#6f7a89")["slabColor"]
    assert marketing != finance
