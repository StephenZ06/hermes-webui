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
  + lift('taskStatusBucket') + '\n' + lift('taskStatusCounts') + '\n'
  + lift('taskStatusBadgeState');

const api = new Function(body + '\nreturn { taskStatusBucket, taskStatusCounts, taskStatusBadgeState };')();
const input = JSON.parse(process.argv[3] || '{}');
process.stdout.write(JSON.stringify({
  bucket: input.status !== undefined ? api.taskStatusBucket(input.status) : null,
  counts: input.workers !== undefined ? api.taskStatusCounts(input.workers) : null,
  badge: input.workers !== undefined ? api.taskStatusBadgeState(input.workers) : null,
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


def test_task_badge_is_neutral_without_active_or_completed_work(driver):
    assert run(driver, workers=[])["badge"] == {"total": 0, "tone": "neutral", "done": 0}


def test_task_badge_pulses_while_any_task_is_running(driver):
    assert run(driver, workers=[worker("active", "running"), worker("done", "completed")])["badge"] == {
        "total": 2, "tone": "running", "done": 1,
    }


def test_task_badge_is_green_when_every_tracked_task_is_done(driver):
    assert run(driver, workers=[worker("one", "completed"), worker("two", "completed")])["badge"] == {
        "total": 2, "tone": "complete", "done": 2,
    }


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_panel_uses_scheduled_state_before_the_business_view_transform():
    # Scheduled work is added to the raw state before the desk-only business
    # projection, so the panel sees it without depending on roster seating.
    at = OFFICE_SRC.index("renderSummary(scheduledState);")
    window = OFFICE_SRC[at:at + 200]
    assert "renderTaskStatusPanel(scheduledState);" in window


def test_clicking_a_task_focuses_its_worker_on_the_floor():
    at = OFFICE_SRC.index("function renderTaskStatusList(")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\nfunction ", at + 10)]
    assert "_scene.focusOnWorker(row.dataset.workerId)" in body


def test_selected_task_details_expand_inside_task_status_not_in_a_second_card():
    # A worker can be selected from either its floor label or its status row.
    # Its inspectable facts must stay with that row instead of opening another
    # right-edge card over the Task Status panel.
    assert "office-tasks-row-detail" in OFFICE_SRC
    assert "office-tasks-row-detail" in CSS
    assert '<div class="office-detail"' not in OFFICE_SRC
    assert ".office-detail{" not in CSS


def test_clicking_the_selected_task_row_toggles_its_inline_details_closed():
    at = OFFICE_SRC.index("function selectTask(")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\nfunction ", at + 10)]
    assert "if (_selectedId === id)" in body
    assert "_selectedId = null;" in body
    assert "scheduleSync();" in body


def test_expanded_task_details_use_compact_type_without_shrinking_task_rows():
    assert ".office-tasks-row-detail{min-height:0;overflow:hidden;font-size:11px;" in CSS
    assert ".office-tasks-row-detail .office-detail-title{font-size:12px;" in CSS
    assert ".office-tasks-row-goal{font-size:12px;" in CSS


def test_task_status_and_inline_details_keep_layout_boxes_for_smooth_transitions():
    assert "office-tasks-row-detail\"${selected ? '' : ' hidden'}" not in OFFICE_SRC
    assert ".office-tasks{position:absolute;z-index:4;top:14px;right:14px;height:auto;max-height:calc(100% - 28px);" in CSS
    assert ".office-tasks-body{display:grid;grid-template-rows:minmax(0,1fr);" in CSS


def test_task_selection_keeps_detail_dom_in_place_for_the_grid_transition():
    at = OFFICE_SRC.index("function renderTaskStatusList(")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\nfunction ", at + 10)]
    assert "${taskStatusDetailHtml(w, _lastTaskStatusWorkers)}" in body
    assert "function syncTaskStatusDisclosure()" in OFFICE_SRC
    assert "syncTaskStatusDisclosure();" in OFFICE_SRC
    assert "_taskStatusDisclosureAnimating" in OFFICE_SRC
    assert "renderTaskStatusPanel(scheduledState" in OFFICE_SRC


def test_scheduled_rows_identify_their_task_type_in_task_status():
    at = OFFICE_SRC.index("function renderTaskStatusList(")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\nfunction ", at + 10)]
    assert "w.scheduledTask ? 'Scheduled Task'" in body


def test_unmount_clears_the_panel_state():
    at = OFFICE_SRC.index("function unmount()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}\n", at)]
    assert "_tasksFiltersEl = null;" in body
    assert "_tasksListEl = null;" in body
    assert "_lastTaskStatusWorkers = [];" in body
    assert "if (_taskStatusDisclosureTimer) clearTimeout(_taskStatusDisclosureTimer);" in body


def test_the_panel_is_a_floating_stage_card_with_equal_expanded_insets():
    assert ".office-tasks{" in CSS
    assert ".office-body{" in CSS
    assert ".office-tasks{position:absolute;z-index:4;top:14px;right:14px;height:auto;max-height:calc(100% - 28px);" in CSS
    assert "<div class=\"office-stage\" data-slide-safe>" in OFFICE_SRC
    stage_at = OFFICE_SRC.index('<div class="office-stage" data-slide-safe>')
    tasks_at = OFFICE_SRC.index('<div class="office-tasks"')
    body_at = OFFICE_SRC.index('<div class="office-tasks-body"')
    body_end = OFFICE_SRC.index('</div>\n    </div>`;', stage_at)
    assert stage_at < tasks_at < body_at < body_end
    # On a phone it is neither squeezed beside the floor nor gone: a small pill in the stage's bottom-right
    # corner that opens in place (widening across the stage, growing upward) with the desktop's disclosure.
    assert "@media (max-width:640px){.office-tasks{display:none;}}" not in CSS
    assert ".office-tasks{top:auto;left:auto;right:10px;bottom:calc(10px + env(safe-area-inset-bottom,0px));width:calc(100% - 20px);" in CSS
    assert ".office-tasks.is-collapsed .office-tasks-title{max-width:0;opacity:0;}" in CSS


# ── collapsible ──────────────────────────────────────────────────────────────

def test_task_status_header_is_the_clickable_toggle_with_a_live_total_badge():
    assert "class=\"office-tasks-toggle\" id=\"officeTasksCollapseBtn\"" in OFFICE_SRC
    assert "id=\"officeTasksCount\"" in OFFICE_SRC
    assert ">TASK STATUS</span>" in OFFICE_SRC
    assert "class=\"office-tasks-title-group\"" in OFFICE_SRC
    assert "class=\"office-tasks-title-icon\"" in OFFICE_SRC
    assert "_tasksCollapseBtnEl.addEventListener('click', toggleTasksCollapsed);" in OFFICE_SRC
    assert "_tasksEl.onclick" not in OFFICE_SRC
    at = OFFICE_SRC.index("function toggleTasksCollapsed()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}", at)]
    assert "const collapsing = !_tasksCollapsed;" in body
    assert "_tasksCollapsed = collapsing;" in body
    assert "writeTasksCollapsed(_tasksCollapsed);" in body
    assert "renderTaskStatusBadge(workers);" in OFFICE_SRC
    assert "_tasksCollapseBtnEl.textContent" not in OFFICE_SRC


def test_task_status_refresh_lock_matches_the_full_unfold_transition():
    assert "const TASK_STATUS_TRANSITION_MS = 480;" in OFFICE_SRC
    at = OFFICE_SRC.index("function toggleTasksCollapsed()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}\n", at) + 2]
    assert "}, TASK_STATUS_TRANSITION_MS);" in body
    assert "scheduleSync();" in body


def test_task_status_uses_only_the_all_running_and_done_filters():
    at = OFFICE_SRC.index("const TASK_STATUS_FILTERS = [")
    body = OFFICE_SRC[at:OFFICE_SRC.index("];", at)]
    assert "{ key: 'all', label: 'All' }" in body
    assert "{ key: 'running', label: 'Running' }" in body
    assert "{ key: 'done', label: 'Done' }" in body
    assert "stopped" not in body


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
    assert ".office-tasks.is-collapsed .office-tasks-body" in CSS
    assert ".office-tasks-body{display:grid;grid-template-rows:minmax(0,1fr);" in CSS
    assert ".office-tasks.is-collapsed{top:14px;right:14px;height:40px;width:min(280px,calc(100% - 28px));" not in CSS


def test_task_status_keeps_its_full_width_and_uses_polished_live_badge_states():
    assert ".office-tasks.is-collapsed .office-tasks-body{pointer-events:none;}" in CSS
    assert ".office-tasks-toggle{position:relative;display:grid;" in CSS
    assert ".office-tasks-count.is-running" in CSS
    assert "animation:office-task-count-pulse" in CSS
    assert ".office-tasks-count.is-complete" in CSS


def test_task_status_collapse_has_a_css_geometry_fallback_for_all_browsers():
    assert ".office-tasks.is-collapsed .office-tasks-body{grid-template-rows:0fr;transition-duration:.26s;}" in CSS
    assert ".office-tasks-count.is-completion-flash" in CSS
    assert "window.WorkHubIcons('sparkles', 'Task completed')" in OFFICE_SRC
    assert "content:'✓'" not in CSS


def test_expanding_task_status_preserves_a_committed_grid_start_frame():
    collapse = OFFICE_SRC[OFFICE_SRC.index("function renderTasksCollapse()") : OFFICE_SRC.index("\nfunction ", OFFICE_SRC.index("function renderTasksCollapse()") + 10)]
    assert "void body.offsetHeight;" in collapse
    assert "window.requestAnimationFrame(() =>" in collapse


def test_expanded_task_status_header_keeps_equal_visual_space_above_and_below_its_title():
    assert ".office-tasks-head{flex:0 0 auto;padding:8px;" in CSS


def test_task_status_icon_and_title_are_centred_as_one_group():
    assert ".office-tasks-toggle{position:relative;display:grid;grid-template-columns:minmax(20px,1fr) auto minmax(20px,1fr);align-items:center;" in CSS
    assert ".office-tasks-title-group{grid-column:2;display:flex;align-items:center;justify-content:center;" in CSS
    assert ".office-tasks-count{grid-column:3;justify-self:end;" in CSS
    assert ".office-tasks-title-icon{width:14px;height:14px;" in CSS


def test_task_status_uses_a_coordinated_disclosure_and_content_fade():
    # The Task Status card should feel like a compact sibling of the Chat
    # project folders, rather than a separate static drawer.
    assert ".office-tasks{position:absolute;z-index:4;top:14px;right:14px;height:auto;max-height:calc(100% - 28px);min-height:36px;width:min(264px,calc(100% - 28px));" in CSS
    assert ".office-tasks-head{flex:0 0 auto;padding:8px;" in CSS
    assert ".office-tasks-toggle{position:relative;display:grid;grid-template-columns:minmax(20px,1fr) auto minmax(20px,1fr);align-items:center;width:100%;min-height:20px;" in CSS
    assert ".office-tasks-count{grid-column:3;justify-self:end;align-self:center;position:relative;" in CSS
    assert "transition:grid-template-rows .48s cubic-bezier(.2,.8,.2,1);" in CSS
    assert ".office-tasks-body-inner{min-height:0;display:flex;flex-direction:column;overflow:hidden;opacity:1;transition:opacity .34s cubic-bezier(.2,.8,.2,1) .1s;}" in CSS
    assert ".office-tasks.is-collapsed .office-tasks-body-inner{opacity:0;transition-delay:0s;}" in CSS
    collapse_at = OFFICE_SRC.index("function renderTasksCollapse()")
    collapse = OFFICE_SRC[collapse_at:OFFICE_SRC.index("\nfunction ", collapse_at + 10)]
    assert "void body.offsetHeight;" in collapse
    assert "window.requestAnimationFrame(() =>" in collapse
    assert "_tasksEl.classList.remove('is-collapsed');" in collapse


def test_task_status_disclosure_uses_one_stable_geometry_transition():
    """A disclosure must not retarget its geometry after it has begun opening."""
    assert "transition:grid-template-rows .48s cubic-bezier(.2,.8,.2,1);" in CSS
    assert "grid-template-rows 1s" not in CSS
    collapse_at = OFFICE_SRC.index("function renderTasksCollapse()")
    collapse = OFFICE_SRC[collapse_at:OFFICE_SRC.index("\nfunction ", collapse_at + 10)]
    assert "window.requestAnimationFrame(syncTaskStatusBodyHeight)" not in collapse


def test_task_status_collapse_finishes_faster_than_its_unfold():
    """Closing a compact status panel should acknowledge intent immediately."""
    assert ".office-tasks.is-collapsed .office-tasks-body{grid-template-rows:0fr;transition-duration:.26s;}" in CSS


def test_task_status_uses_the_chat_style_grid_disclosure_without_height_measurement():
    """A scrolling task list must not animate a measured height every frame."""
    assert ".office-tasks-body{display:grid;grid-template-rows:minmax(0,1fr);min-height:0;max-height:calc(100vh - 100px);transition:grid-template-rows .48s cubic-bezier(.2,.8,.2,1);cursor:auto;}" in CSS
    assert ".office-tasks.is-collapsed .office-tasks-body{grid-template-rows:0fr;transition-duration:.26s;}" in CSS
    assert "function syncTaskStatusBodyHeight()" not in OFFICE_SRC


def test_unmount_clears_the_collapse_button_reference():
    at = OFFICE_SRC.index("function unmount()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}\n", at)]
    assert "_tasksEl = null;" in body
    assert "_tasksCollapseBtnEl = null;" in body
