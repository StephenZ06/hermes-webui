"""Each subagent desk sits in a small cubicle.

Real three.js under node, same fixture shape as tests/test_office_visual_extras.py.
The cubicle is two neutral partition walls with a thin accent strip in the
platform's colour that brightens while the desk's subagent works. It must
never hide the desk from the camera, never stand across the path a subagent
walks in on, and its accent must stay below the bloom threshold so it reads
as a line rather than a halo.
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
const THREE = await import('three');
const {
  makeCubicle, cubicleWallPlan, setCubicleActive,
  CUBICLE_ACCENT_IDLE, CUBICLE_ACCENT_ACTIVE,
} = await import(process.argv[2]);

const palette = { cubicle: '#1b2130' };
const accent = '#3f7fd4';

function boxes(group) {
  group.updateMatrixWorld(true);
  const out = [];
  group.traverse(o => {
    if (!o.isMesh) return;
    o.geometry.computeBoundingBox();
    const b = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld);
    out.push({ min: [b.min.x, b.min.y, b.min.z], max: [b.max.x, b.max.y, b.max.z],
               emissive: o.material.emissive ? o.material.emissive.getHexString() : null,
               ei: o.material.emissiveIntensity ?? 0,
               color: o.material.color.getHexString() });
  });
  return out;
}

// Camera in front-right of the desk, and behind-left of it.
const frontPlan = cubicleWallPlan({ x: 0.7, z: 0.7 });
const behindPlan = cubicleWallPlan({ x: -0.7, z: -0.7 });
const front = makeCubicle(palette, accent, frontPlan);
const behind = makeCubicle(palette, accent, behindPlan);
const idle = boxes(front);
setCubicleActive(front, true);
const active = boxes(front);
setCubicleActive(front, false);
const idleAgain = boxes(front);

process.stdout.write(JSON.stringify({
  frontPlan, behindPlan, idle, active, idleAgain,
  behind: boxes(behind),
  thresholds: { idle: CUBICLE_ACCENT_IDLE, active: CUBICLE_ACCENT_ACTIVE },
}));
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    root = tmp_path_factory.mktemp("office-cubicle")
    three_pkg = root / "node_modules" / "three"
    three_pkg.mkdir(parents=True)
    (three_pkg / "package.json").write_text(
        json.dumps({"name": "three", "type": "module", "main": "index.mjs"}), encoding="utf-8")
    (three_pkg / "index.mjs").write_text(
        f"export * from {json.dumps(THREE.as_uri())};\n", encoding="utf-8")
    for name in ("builders.js", "idle.js"):
        (root / name).write_text((REPO / "static" / "office" / name).read_text(encoding="utf-8"),
                                 encoding="utf-8")
    driver = root / "driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    proc = subprocess.run([NODE, str(driver), (root / "builders.js").as_uri()],
                          capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"cubicle driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def _strips(meshes):
    return [m for m in meshes if m["emissive"] not in (None, "000000")]


def _walls(meshes):
    return [m for m in meshes if m not in _strips(meshes)]


def test_walls_go_on_the_sides_away_from_the_camera(result):
    assert result["frontPlan"]["sideX"] < 0, "camera on the +x side: the side wall goes at -x"
    assert result["behindPlan"]["sideX"] > 0, "camera on the -x side: the side wall goes at +x"
    assert result["frontPlan"]["backHeight"] > result["behindPlan"]["backHeight"], (
        "a back wall the camera looks across must be low so it does not hide the monitor"
    )
    assert result["behindPlan"]["backHeight"] < 1.5 + 0.6, "the low back wall stays under the desk's monitor"


def test_nothing_stands_in_the_walk_in_path_or_in_front_of_the_desk(result):
    # A subagent walks in over |x| <= 1.4, z in [1.9, 5.0]; the chair is at z = 1.9.
    for meshes in (result["idle"], result["behind"]):
        for m in meshes:
            assert m["max"][2] <= 1.0, f"a cubicle part reaches in front of the desk: {m}"


def test_panels_are_neutral_and_strips_carry_the_platform_colour(result):
    walls = _walls(result["idle"])
    strips = _strips(result["idle"])
    assert len(walls) == 2 and len(strips) == 2
    for wall in walls:
        r, g, b = (int(wall["color"][i:i + 2], 16) for i in (0, 2, 4))
        assert max(r, g, b) - min(r, g, b) < 40, f"panel should be a neutral grey, got #{wall['color']}"
    for strip in strips:
        assert strip["color"] == "3f7fd4" and strip["emissive"] == "3f7fd4"


def test_accent_brightens_only_while_working_and_never_blooms(result):
    idle = {round(s["ei"], 3) for s in _strips(result["idle"])}
    active = {round(s["ei"], 3) for s in _strips(result["active"])}
    again = {round(s["ei"], 3) for s in _strips(result["idleAgain"])}
    assert idle == again == {round(result["thresholds"]["idle"], 3)}
    assert active == {round(result["thresholds"]["active"], 3)}
    assert max(active) > max(idle)
    # Bloom threshold is 1.0; the accent colour's brightest channel times its
    # intensity stays well under it, so it is a line, not a halo.
    assert 0xd4 / 255 * max(active) < 0.8
