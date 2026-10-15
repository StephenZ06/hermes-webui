"""The Office's dynamic-resolution governor (static/office/quality.js), driven under node."""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
QUALITY = REPO / "static" / "office" / "quality.js"
SCENE_SRC = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required to drive quality.js")

_DRIVER = r"""
const { createQualityGovernor } = await import(process.argv[1]);
const s = JSON.parse(process.argv[2]);
const g = createQualityGovernor({ base: s.base, min: s.min });
let now = 0;
g.reset(now);
const changes = [];
for (const [count, dt] of s.frames) {
  for (let i = 0; i < count; i++) {
    now += dt;
    const next = g.sample(dt, now);
    if (next !== null) changes.push([Math.round(now), next]);
  }
}
console.log(JSON.stringify({ changes, ratio: g.ratio }));
"""


def _drive(frames, base=2, min_ratio=1):
    out = subprocess.run([NODE, "--input-type=module", "-e", _DRIVER, QUALITY.as_uri(),
                          json.dumps({"base": base, "min": min_ratio, "frames": frames})],
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def test_a_fast_gpu_keeps_full_resolution():
    assert _drive([(2000, 16.7)]) == {"changes": [], "ratio": 2}


def test_a_slow_gpu_steps_down_to_1x_and_no_further():
    result = _drive([(1500, 33.3)])
    assert [ratio for _, ratio in result["changes"]] == [1.75, 1.5, 1.25, 1]
    assert result["ratio"] == 1


def test_isolated_spikes_cost_nothing():
    # A GC pause or a tab switch every few seconds, otherwise 60fps.
    frames = [(40, 16.7), (1, 120), (3, 40)] * 40
    assert _drive(frames)["changes"] == []


def test_it_raises_again_only_after_sustained_headroom():
    slow_then_fast = [(300, 33.3), (200, 13)]
    first = _drive(slow_then_fast)
    assert first["ratio"] < 2  # dropped while slow, not yet raised back
    recovered = _drive([(300, 33.3), (3000, 13)])
    assert recovered["ratio"] == 2
    ratios = [ratio for _, ratio in recovered["changes"]]
    drops = ratios[: ratios.index(min(ratios)) + 1]
    assert drops == sorted(drops, reverse=True)  # all the way down first, then up: no flapping


def test_the_scene_uses_the_governor_and_caps_msaa():
    # a desktop panel may step down to 1x; a touch screen never below 1.5x (see the comment at the call)
    assert "createQualityGovernor({ base: preferredPixelRatio, min: touchScreen ? Math.min(preferredPixelRatio, 1.5) : 1 })" in SCENE_SRC
    assert "quality.sample(frameMs, now || 0)" in SCENE_SRC
    assert "samples: Math.min(4," in SCENE_SRC
    assert "SCREEN_REDRAW_S" in SCENE_SRC


def test_a_very_slow_gpu_still_steps_down():
    # Software rendering: about a second per frame.
    assert _drive([(300, 1000)])["ratio"] == 1


def test_a_gpu_on_the_edge_stops_bouncing_between_ratios():
    # Slow at 2x, fast at 1.75x: it would drop, raise after ~4.5 s, drop
    # again... each bounce a hitch. After the first bounce raises wait longer.
    frames = [(300, 33.3), (400, 13), (300, 33.3), (400, 13), (300, 33.3), (400, 13)]
    changes = _drive(frames)["changes"]
    ups = [i for i in range(1, len(changes)) if changes[i][1] > changes[i - 1][1]]
    assert len(ups) <= 1, changes
