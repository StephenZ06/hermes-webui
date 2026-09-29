"""Visible live-work motion for the Personal Office.

Cross-profile delegation reliably reports lifecycle state, but may not emit
individual tool events. A worker that is still reported as running must keep a
working pose, and the conductor must have a distinct, readable motion while it
orchestrates that work.
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
const { shouldSleepWhileRunning } = await import(process.argv[2]);
const { makePerson, poseWorker, poseTargets } = await import(process.argv[3]);

const palette = { skin: '#d5a47a', hair: '#161313', conductor: '#7187be' };

function shoulderSweep(pose) {
  const person = makePerson(palette, palette.conductor);
  for (let i = 0; i < 8; i++) poseWorker(person, pose, 0, 0.1);
  const before = person.userData.joints.shoulderL.rotation.x;
  for (let i = 0; i < 8; i++) poseWorker(person, pose, 0.17, 0.1);
  return Math.abs(person.userData.joints.shoulderL.rotation.x - before);
}

const sleeping = typeof shouldSleepWhileRunning === 'function'
  ? shouldSleepWhileRunning
  : () => true;

process.stdout.write(JSON.stringify({
  untouchedRunningSleeps: sleeping({
    status: 'running', pose: 'work', lastToolAt: 0,
  }, 30_000),
  quietAfterToolSleeps: sleeping({
    status: 'running', pose: 'work', lastToolAt: 1,
  }, 12_000),
  workSweep: shoulderSweep('work'),
  orchestrateSweep: shoulderSweep('orchestrate'),
  orchestrateTarget: poseTargets('orchestrate'),
}));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    root = tmp_path_factory.mktemp("office-activity-animation")
    three_pkg = root / "node_modules" / "three"
    three_pkg.mkdir(parents=True)
    (three_pkg / "package.json").write_text(
        json.dumps({"name": "three", "type": "module", "main": "index.mjs"}),
        encoding="utf-8",
    )
    (three_pkg / "index.mjs").write_text(
        f"export * from {json.dumps(THREE.as_uri())};\n", encoding="utf-8"
    )
    for name in ("builders.js", "idle.js"):
        source = REPO / "static" / "office" / name
        target = root / name
        if source.exists():
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    path = root / "driver.mjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def result(driver):
    proc = subprocess.run(
        [NODE, str(driver), (driver.parent / "idle.js").as_uri(),
         (driver.parent / "builders.js").as_uri()],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"office activity-animation driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def test_running_worker_without_tool_events_keeps_the_work_pose(result):
    assert result["untouchedRunningSleeps"] is False
    assert result["quietAfterToolSleeps"] is True


def test_working_and_orchestrating_have_visible_motion(result):
    assert result["workSweep"] > 0.14
    assert result["orchestrateSweep"] > 0.14
    assert result["orchestrateTarget"] != pose_idle_target(result)


def pose_idle_target(_result):
    return {
        "shoulderX": -0.45, "shoulderZ": 0.00, "headX": 0.00,
        "torsoX": 0.00, "lift": 0,
    }
