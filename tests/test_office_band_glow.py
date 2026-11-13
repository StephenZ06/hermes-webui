"""A working platform's light bar brightens and holds steady; nothing blooms.

At rest a band stays well under the bloom threshold, whatever the pointer or a
landing packet does. While work is under way its light rises to the same level
for every colour and stops pulsing, with room left under the threshold for the
scene's lights on its faces. It used to sit just under the threshold with a
pulse, so the lights pushed some faces past it on some frames: the halo
flickered and differed between platforms. Before that, a flat +1.45 delivery
flare bloomed every working platform into a halo at each arrival. This drives the
real makePod and bandGlowIntensity under node, the way
tests/test_office_pod_color.py does.
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

# Every platform colour the floor uses: roster.js's departments and project
# clusters, and layout.js's project palette.
COLOURS = ["#ec4899", "#10b981", "#f59e0b", "#8b5cf6", "#06b6d4", "#3b82f6", "#94a3b8", "#14b8a6",
           "#e0527d", "#4fae5e", "#e0a934", "#9457c7", "#2f9e8f", "#3f7fd4", "#d97a3f", "#3fb0a8"]
BLOOM_THRESHOLD = 1.0  # scene.js

_DRIVER = r"""
const { makePod, bandGlowIntensity } = await import(process.argv[2]);
const out = {};
for (const tint of JSON.parse(process.argv[3])) {
  const pod = makePod(10, 6, { podTop: '#0d172b', podSide: '#0a101e' }, tint);
  const band = pod.userData.deliveryLayer;
  const c = band.material.emissive;
  const luminance = 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
  const idle = band.material.emissiveIntensity;
  const lum = band.userData.bandLuminance;
  const at = (state) => bandGlowIntensity(idle, { luminance: lum, ...state }) * luminance;
  out[tint] = {
    idle: at({}),
    idleBusy: at({ hover: 1, delivery: 1 }),
    active: at({ active: 1 }),
    activeLow: at({ active: 1, pulse: 0.7 }),
    arrival: at({ active: 1, delivery: 1 }),
    everything: at({ pulse: 1, active: 1, hover: 1, delivery: 1 }),
  };
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def glow(tmp_path_factory):
    root = tmp_path_factory.mktemp("office-band-glow")
    three_pkg = root / "node_modules" / "three"
    three_pkg.mkdir(parents=True)
    (three_pkg / "package.json").write_text(json.dumps({"name": "three", "type": "module", "main": "index.mjs"}), encoding="utf-8")
    (three_pkg / "index.mjs").write_text(f"export * from {json.dumps(THREE.as_uri())};\n", encoding="utf-8")
    for name in ("builders.js", "idle.js"):
        (root / name).write_text((REPO / "static" / "office" / name).read_text(encoding="utf-8"), encoding="utf-8")
    driver = root / "driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    proc = subprocess.run([NODE, str(driver), (root / "builders.js").as_uri(), json.dumps(COLOURS)],
                          capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr.strip()
    return json.loads(proc.stdout)


def test_an_idle_platform_never_blooms(glow):
    for tint, band in glow.items():
        assert band["idleBusy"] < BLOOM_THRESHOLD * .9, (tint, band)


def test_a_working_platform_holds_a_steady_light_under_the_threshold(glow):
    for tint, band in glow.items():
        if band["idle"] < .6:
            continue  # a deep colour whose band is barely lit at idle
        # Brighter than at rest, the same at every point of the pulse, and far
        # enough under the threshold that the scene's lights never carry it past.
        assert band["idle"] < band["active"] <= BLOOM_THRESHOLD * .9, (tint, band)
        assert abs(band["activeLow"] - band["active"]) < 1e-9, (tint, band)
        assert band["active"] < band["arrival"] <= band["everything"] <= BLOOM_THRESHOLD * .92, (tint, band)


def test_every_working_colour_glows_by_the_same_amount(glow):
    levels = {tint: band["active"] for tint, band in glow.items() if band["idle"] >= .6}
    assert len(levels) >= 12, levels
    assert max(levels.values()) - min(levels.values()) < .01, levels
