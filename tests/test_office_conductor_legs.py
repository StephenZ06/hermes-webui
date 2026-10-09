"""The conductor keeps its legs when it stops walking.

The conductor has no desk or chair: it paces its plinth and stands to
orchestrate. Its pauses and its orchestrate pose went through the desk pose
driver, which hides legs (a seated figure's are behind furniture), so the
figure lost its legs every time it stopped. Real three.js under node, same
fixture shape as tests/test_office_cubicle.py.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
THREE = REPO / "static" / "vendor" / "three" / "0.185.1" / "three.module.min.js"
NODE = shutil.which("node")

_DRIVER = r"""
const { makePerson, poseWalking, poseWorker } = await import(process.argv[2]);
const palette = { skin: '#c68b59', hair: '#1a1a20', trousers: '#2b2d36', shirt: '#4f7ca8' };

function legs(p) {
  const j = p.userData.joints;
  return { visible: j.legs.visible, hipL: j.hipL.rotation.x, hipR: j.hipR.rotation.x };
}

const standing = makePerson(palette, '#e2e8f0');
poseWalking(standing, 0.7, 1);           // mid-stride
const midStride = legs(standing);
for (let i = 0; i < 90; i += 1) poseWorker(standing, 'idle', i / 60, 1 / 60, { standing: true });
const afterPause = legs(standing);
for (let i = 0; i < 90; i += 1) poseWorker(standing, 'orchestrate', i / 60, 1 / 60, { standing: true });
const orchestrating = legs(standing);

const seated = makePerson(palette, '#6b8fb5');
poseWalking(seated, 0.7, 1);
poseWorker(seated, 'work', 0, 1 / 60);
const atDesk = legs(seated);

process.stdout.write(JSON.stringify({ midStride, afterPause, orchestrating, atDesk }));
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is required")
    root = tmp_path_factory.mktemp("office-conductor-legs")
    pkg = root / "node_modules" / "three"
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text(json.dumps({"name": "three", "type": "module", "main": "index.mjs"}), encoding="utf-8")
    (pkg / "index.mjs").write_text(f"export * from {json.dumps(THREE.as_uri())};\n", encoding="utf-8")
    for name in ("builders.js", "idle.js"):
        (root / name).write_text((REPO / "static" / "office" / name).read_text(encoding="utf-8"), encoding="utf-8")
    driver = root / "driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    proc = subprocess.run([NODE, str(driver), (root / "builders.js").as_uri()],
                          capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip())
    return json.loads(proc.stdout)


def test_a_standing_figure_keeps_its_legs_when_it_pauses(result):
    assert result["midStride"]["visible"]
    assert abs(result["midStride"]["hipL"]) > 0.1, "precondition: the walk left the legs mid-swing"
    assert result["afterPause"]["visible"], "the conductor lost its legs when it stopped walking"
    assert abs(result["afterPause"]["hipL"]) < 0.02 and abs(result["afterPause"]["hipR"]) < 0.02, (
        "standing still, the legs ease back to straight instead of freezing mid-stride"
    )


def test_the_standing_orchestrate_pose_keeps_its_legs(result):
    assert result["orchestrating"]["visible"]


def test_a_desk_worker_still_tucks_its_legs_away(result):
    assert result["atDesk"]["visible"] is False


def test_every_conductor_pose_is_driven_as_standing():
    scene = (REPO / "static" / "office" / "scene.js").read_text(encoding="utf-8")
    start = scene.index("if (conductor) {\n      const person = conductor.userData.person;")
    block = scene[start:start + 4000]
    calls = re.findall(r"poseWorker\(person,[^;]*\);", block)
    assert calls, block
    # Standing everywhere, except sitting in one of the hub's chairs between
    # delegations (conductor-life.js), where the chair hides the legs.
    assert all("standing: true" in call or "standing: !now.seated" in call for call in calls), calls
