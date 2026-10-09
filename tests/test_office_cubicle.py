"""Each subagent desk sits in a framed office cubicle.

Real three.js under node, same fixture shape as tests/test_office_visual_extras.py.
The cubicle encloses desk and chair on all four sides at one height (solid
lower panels, frosted glass above, a frame), with an opening in the front
wall over the path a subagent walks in on. Its only platform colour is a thin
top rail that brightens while the desk's subagent works -- never enough to
bloom -- and a rug in a darker shade of the platform. It is merged into a few
shared geometries so a busy floor does not cost dozens of draw calls a desk.
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
  makeCubicle, setCubicleActive, CUBICLE_ACCENT_IDLE, CUBICLE_ACCENT_ACTIVE,
} = await import(process.argv[2]);

const palette = {
  cubiclePanel: '#8e97a6', cubicleFrame: '#4b5363', cubicleGlass: '#dbe4f0',
  podTop: '#0d172b', cubicleRugShade: '#000000', cubicleRugMix: 0.35,
};
const accent = '#3f7fd4';

// Triangles as axis-aligned boxes, so a wall spanning the doorway is caught
// even though its vertices sit outside it.
function triangleBoxes(mesh) {
  mesh.updateMatrixWorld(true);
  const pos = mesh.geometry.getAttribute('position');
  const idx = mesh.geometry.index;
  const count = idx ? idx.count : pos.count;
  const v = [0, 0, 0].map(() => ({ x: 0, y: 0, z: 0 }));
  const out = [];
  const read = i => {
    const k = idx ? idx.getX(i) : i;
    const p = { x: pos.getX(k), y: pos.getY(k), z: pos.getZ(k) };
    const e = mesh.matrixWorld.elements;
    return {
      x: e[0] * p.x + e[4] * p.y + e[8] * p.z + e[12],
      y: e[1] * p.x + e[5] * p.y + e[9] * p.z + e[13],
      z: e[2] * p.x + e[6] * p.y + e[10] * p.z + e[14],
    };
  };
  for (let i = 0; i < count; i += 3) {
    const a = read(i), b = read(i + 1), c = read(i + 2);
    out.push({
      min: [Math.min(a.x, b.x, c.x), Math.min(a.y, b.y, c.y), Math.min(a.z, b.z, c.z)],
      max: [Math.max(a.x, b.x, c.x), Math.max(a.y, b.y, c.y), Math.max(a.z, b.z, c.z)],
    });
  }
  return out;
}

function describe(group) {
  const meshes = [];
  group.traverse(o => {
    if (!o.isMesh) return;
    group.updateMatrixWorld(true);
    const b = new THREE.Box3().setFromObject(o);
    meshes.push({
      uuid: o.geometry.uuid,
      color: o.material.color.getHexString(),
      emissive: o.material.emissive ? o.material.emissive.getHexString() : '000000',
      ei: o.material.emissiveIntensity ?? 0,
      transparent: !!o.material.transparent,
      min: [b.min.x, b.min.y, b.min.z], max: [b.max.x, b.max.y, b.max.z],
      tris: triangleBoxes(o),
    });
  });
  return meshes;
}

const one = makeCubicle(palette, accent);
const two = makeCubicle(palette, '#9b59d0');
const idle = describe(one);
setCubicleActive(one, true);
const active = describe(one);
setCubicleActive(one, false);
const idleAgain = describe(one);

process.stdout.write(JSON.stringify({
  floor: new THREE.Color('#0d172b').lerp(new THREE.Color(accent), 0.62).getHexString(),
  idle, active, idleAgain, other: describe(two),
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


def _strip(meshes):
    return [m for m in meshes if m["emissive"] != "000000"]


def _walls(meshes):
    """Everything standing up: panels and posts (not the flat rug)."""
    return [m for m in meshes if m["emissive"] == "000000" and m["max"][1] > 0.5]


def _luminance(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_encloses_the_desk_on_all_four_sides_at_one_height(result):
    walls = _walls(result["idle"])
    assert walls, result["idle"]
    height = max(m["max"][1] for m in walls)
    # Low partitions (the reference look): every side reaches the same low
    # height -- back, left, right and both sides of the opening.
    full = [t for m in walls for t in m["tris"] if t["max"][1] > height - 0.1]
    assert height < 1.1, "low enough that the desk and its worker show over the near walls"
    assert any(t["max"][2] < -1.5 for t in full), "back wall"
    assert any(t["min"][0] < -2.9 for t in full) and any(t["max"][0] > 2.9 for t in full), "side walls"
    assert any(t["min"][2] > 2.8 and t["max"][0] < -1.7 for t in full), "front wall, left of the opening"
    assert any(t["min"][2] > 2.8 and t["min"][0] > 1.7 for t in full), "front wall, right of the opening"
    xs = [m["min"][0] for m in walls] + [m["max"][0] for m in walls]
    zs = [m["min"][2] for m in walls] + [m["max"][2] for m in walls]
    # Desk is 4.4 x 2.4 at the origin, chair at z = 1.9: all inside.
    assert min(xs) < -2.3 and max(xs) > 2.3
    assert min(zs) < -1.3 and max(zs) > 2.6


def test_front_wall_leaves_an_opening_over_the_walk_in_path(result):
    # A subagent walks in over |x| <= 1.4 from z ~5 down to the chair at 1.9.
    for mesh in _walls(result["idle"]) + _strip(result["idle"]):
        for tri in mesh["tris"]:
            overlaps = (tri["max"][0] > -1.5 and tri["min"][0] < 1.5
                        and tri["max"][2] > 1.0 and tri["min"][2] < 5.0
                        and tri["max"][1] > 0.1)
            assert not overlaps, f"a cubicle part stands in the walk-in path: {tri}"


def test_nothing_is_black_and_the_walls_are_low_partitions(result):
    walls = _walls(result["idle"])
    for mesh in walls:
        assert _luminance(mesh["color"]) > 0.015, f"#{mesh['color']} is black"
    assert all(m["max"][1] < 1.1 for m in walls), "no tall glass panels: a low partition"


def test_platform_colour_is_the_rail_and_a_darker_rug(result):
    strips = _strip(result["idle"])
    assert len(strips) == 1 and strips[0]["color"] == "3f7fd4"
    rug = [m for m in result["idle"] if m["max"][1] < 0.1]
    assert len(rug) == 1
    # makePod paints the platform top as podTop blended 62% toward the tint.
    floor = result["floor"]
    assert _luminance(rug[0]["color"]) < _luminance(floor) * 0.85, (
        f"the rug must read as a darker carpet on the platform floor (#{floor}), got #{rug[0]['color']}"
    )


def test_rail_brightens_only_while_working_and_never_blooms(result):
    idle = {round(s["ei"], 3) for s in _strip(result["idle"])}
    active = {round(s["ei"], 3) for s in _strip(result["active"])}
    again = {round(s["ei"], 3) for s in _strip(result["idleAgain"])}
    assert idle == again == {round(result["thresholds"]["idle"], 3)}
    assert active == {round(result["thresholds"]["active"], 3)}
    # Bloom threshold is 1.0; brightest channel x intensity stays well under it.
    assert 0xd4 / 255 * max(active) < 0.8


def test_cubicles_are_a_few_shared_meshes(result):
    assert len(result["idle"]) <= 4, "panels, posts, rail and rug -- not one mesh per part"
    shared = {m["uuid"] for m in _walls(result["idle"])} & {m["uuid"] for m in _walls(result["other"])}
    assert len(shared) == 2, "two desks reuse the same wall geometry"
