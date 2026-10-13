"""Background shader warm-up for the Office floor.

three.js r185's ``renderer.compileAsync`` polls
``properties.get(material).currentProgram.isReady()`` inside a bare timer. A
material three.js skipped while compiling (or one disposed because the floor
was rebuilt during the warm-up) has no program, so that timer threw
"Cannot read properties of undefined (reading 'isReady')" into the console and
the warm-up never settled. ``static/office/warmup.js`` does the same work with
a poll that treats a missing program as done and can never throw.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
WARMUP = REPO / "static" / "office" / "warmup.js"
SCENE_SRC = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

_DRIVER = r"""
const { compileInBackground } = await import(process.argv[2]);
// Three materials: one compiles after two polls, one never gets a program
// (skipped / disposed), one has a program without isReady (no extension).
let polls = 0;
const ready = {}, noProgram = {}, plain = {};
const props = new Map([
  [ready, { get currentProgram() { return { isReady: () => polls >= 2 }; } }],
  [noProgram, {}],
  [plain, { currentProgram: {} }],
]);
const renderer = {
  compile: () => new Set([ready, noProgram, plain]),
  properties: { get: (m) => props.get(m) || {} },
};
const errors = [];
process.on('uncaughtException', (e) => errors.push(String(e)));
const done = await Promise.race([
  compileInBackground(renderer, {}, {}, { interval: 1, onPoll: () => { polls++; } }).then(() => 'settled'),
  new Promise((r) => setTimeout(() => r('timeout'), 500)),
]);
// A renderer whose compile throws still settles.
const broken = await compileInBackground({ compile() { throw new Error('x'); } }, {}, {}).then(() => 'settled');
console.log(JSON.stringify({ done, broken, errors, polls }));
"""


def test_warmup_settles_without_throwing_when_a_material_has_no_program(tmp_path):
    driver = tmp_path / "drive.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    out = subprocess.run([NODE, str(driver), WARMUP.as_uri()], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result == {"done": "settled", "broken": "settled", "errors": [], "polls": result["polls"]}
    assert result["polls"] >= 2, "it must wait for the program that is still compiling"


def test_the_scene_no_longer_uses_three_compile_async():
    assert "renderer.compileAsync(" not in SCENE_SRC
    assert "compileInBackground(renderer, scene, camera" in SCENE_SRC
