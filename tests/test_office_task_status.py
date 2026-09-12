"""The Office's aggregate Task Status panel (static/office/index.js).

A whole-office view of the real workers the adapter is tracking, independent
of which outlet (Projects/Business) is showing -- a subagent is the same
real subagent whichever floor plan draws it, so this reads the raw adapter
state directly rather than an outlet-specific desk view.

taskStatusBucket()/taskStatusCounts() are pure, so they are lifted out and
run on their own -- the same approach tests/test_office_sidebar_live.py uses.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
OFFICE_INDEX = REPO / "static" / "office" / "index.js"
OFFICE_SRC = OFFICE_INDEX.read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

_DRIVER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

function lift(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('missing function: ' + name);
  let i = src.indexOf('{', start), depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) { i++; break; } }
  }
  return src.slice(start, i);
}

const terminalMatch = src.match(/const _TERMINAL_STATUSES = new Set\(\[([^\]]*)\]\);/s);
const body = `const _TERMINAL_STATUSES = new Set([${terminalMatch[1]}]);\n`
  + lift('taskStatusBucket') + '\n' + lift('taskStatusCounts');

const api = new Function(body + '\nreturn { taskStatusBucket, taskStatusCounts };')();
const input = JSON.parse(process.argv[3] || '{}');
process.stdout.write(JSON.stringify({
  bucket: input.status !== undefined ? api.taskStatusBucket(input.status) : null,
  counts: input.workers !== undefined ? api.taskStatusCounts(input.workers) : null,
}));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-task-status") / "driver.cjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def run(driver, **payload):
    proc = subprocess.run(
        [NODE, str(driver), str(OFFICE_INDEX), json.dumps(payload)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def worker(wid, status, spawned=1000):
    return {"id": wid, "status": status, "spawnedAt": spawned, "goal": wid}


# ── bucketing ────────────────────────────────────────────────────────────────

def test_running_is_its_own_bucket(driver):
    assert run(driver, status="running")["bucket"] == "running"


def test_completed_is_done(driver):
    assert run(driver, status="completed")["bucket"] == "done"


@pytest.mark.parametrize("status", ["failed", "error", "timeout", "interrupted", "ended"])
def test_every_other_terminal_status_is_stopped(driver, status):
    assert run(driver, status=status)["bucket"] == "stopped"


def test_an_unknown_status_is_other_not_silently_dropped(driver):
    # Fails closed: an unrecognised status must not be miscounted into a
    # bucket that implies something specific happened.
    assert run(driver, status="something-new")["bucket"] == "other"


# ── aggregate counts ─────────────────────────────────────────────────────────

def test_counts_add_up_across_every_bucket(driver):
    out = run(driver, workers=[
        worker("w1", "running"),
        worker("w2", "running"),
        worker("w3", "completed"),
        worker("w4", "failed"),
        worker("w5", "interrupted"),
    ])
    counts = out["counts"]
    assert counts["all"] == 5
    assert counts["running"] == 2
    assert counts["done"] == 1
    assert counts["stopped"] == 2


def test_an_empty_office_counts_to_zero(driver):
    out = run(driver, workers=[])
    assert out["counts"] == {"all": 0, "running": 0, "done": 0, "stopped": 0, "other": 0}


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_panel_is_rendered_from_raw_adapter_state_not_the_outlet_view():
    # A subagent is the same real subagent whichever floor plan draws it --
    # this must not need businessView()'s desk transform to work.
    at = OFFICE_SRC.index("renderSummary(state);")
    window = OFFICE_SRC[at:at + 200]
    assert "renderTaskStatusPanel(state);" in window


def test_clicking_a_task_focuses_its_worker_on_the_floor():
    at = OFFICE_SRC.index("function renderTaskStatusList(")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\nfunction ", at + 10)]
    assert "_scene.focusOnWorker(row.dataset.workerId)" in body


def test_unmount_clears_the_panel_state():
    at = OFFICE_SRC.index("function unmount()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}\n", at)]
    assert "_tasksFiltersEl = null;" in body
    assert "_tasksListEl = null;" in body
    assert "_lastTaskStatusWorkers = [];" in body


def test_the_panel_sits_beside_the_stage_not_over_it():
    assert ".office-tasks{" in CSS
    assert ".office-body{" in CSS
    # Hidden rather than squeezed on a phone -- the isometric floor needs the
    # room, and a shrunken 3rd column would be unreadable either way.
    assert "@media (max-width:640px){.office-tasks{display:none;}}" in CSS


# ── collapsible ──────────────────────────────────────────────────────────────

def test_the_collapse_button_is_wired_in_mount_and_toggles_state():
    assert "_tasksCollapseBtnEl.onclick = toggleTasksCollapsed;" in OFFICE_SRC
    at = OFFICE_SRC.index("function toggleTasksCollapsed()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}", at)]
    assert "_tasksCollapsed = !_tasksCollapsed;" in body
    assert "writeTasksCollapsed(_tasksCollapsed);" in body


def test_the_collapsed_state_is_remembered_across_visits():
    # The same persistence pattern as the outlet choice (readOutlet/
    # writeOutlet) -- a reload should not silently re-expand a column the
    # user deliberately collapsed to get the canvas' width back.
    assert "TASKS_COLLAPSED_STORAGE_KEY" in OFFICE_SRC
    assert "localStorage.getItem(TASKS_COLLAPSED_STORAGE_KEY)" in OFFICE_SRC
    assert "localStorage.setItem(TASKS_COLLAPSED_STORAGE_KEY" in OFFICE_SRC


def test_filters_and_list_stay_in_the_dom_while_collapsed():
    # Collapsing must not tear down and rebuild the filter buttons/rows --
    # only their visibility (a CSS class on the column) changes, so a
    # re-expand shows exactly what was there before, with no re-render lag.
    at = OFFICE_SRC.index("function renderTasksCollapse()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}", at)]
    assert "classList.toggle('is-collapsed', _tasksCollapsed)" in body
    assert "office-tasks.is-collapsed .office-tasks-filters" in CSS
    assert "office-tasks.is-collapsed .office-tasks-list" in CSS


def test_unmount_clears_the_collapse_button_reference():
    at = OFFICE_SRC.index("function unmount()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}\n", at)]
    assert "_tasksEl = null;" in body
    assert "_tasksCollapseBtnEl = null;" in body
