"""A working platform's band brightens without blooming into a halo.

Live work, the pointer and each packet landing all brighten a platform's
neon band. The delivery flare used to be a flat +1.45 on top of a 1.35x
active boost, which pushed every working platform past the bloom threshold
at each arrival. This drives the real makePod and bandGlowIntensity under
node, the way tests/test_office_pod_color.py does.
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
  const at = (state) => bandGlowIntensity(idle, state) * luminance;
  out[tint] = {
    idle: at({}),
    active: at({ active: 1 }),
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


def test_no_platform_blooms_however_much_is_happening_on_it(glow):
    for tint, band in glow.items():
        assert band["everything"] < BLOOM_THRESHOLD * .96, (tint, band)


def test_work_and_arrivals_still_show_on_the_band(glow):
    for tint, band in glow.items():
        if band["idle"] < .3:
            continue  # a deep colour whose band is barely lit at idle
        assert band["active"] > band["idle"] * 1.05, (tint, band)
        assert band["arrival"] > band["active"] * 1.05, (tint, band)


def test_every_colour_brightens_by_the_same_share(glow):
    shares = {tint: band["arrival"] / band["idle"] for tint, band in glow.items() if band["idle"]}
    assert max(shares.values()) - min(shares.values()) < .01, shares
