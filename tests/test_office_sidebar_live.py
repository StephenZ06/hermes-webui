"""The office sidebar shows the run happening now, named after the work.

Three things this pins, all reported from real use:

* A delegation has to appear the moment it starts. The stored listing
  (`GET /api/agent-canvas/sessions`) cannot supply that — those rows land in
  state.db as children are created, and the listing is refetched on a timer —
  so the row for the current run is built from live adapter state and replaced
  by the stored one once it catches up.
* The row is named after the *work*, not the chat. A chat's title describes the
  conversation, so two different fan-outs from one chat are indistinguishable
  under it; the subagents' goals are what name the row.
* A live marker, because these listings mix profiles. `/api/agent-canvas/
  sessions` returns base-database parents (filtered to the active profile) plus
  profile-scoped ones, so rows from other profiles genuinely do appear, and
  "which of these is running now" is not otherwise answerable from the row.
"""
import json
import pathlib
import shutil
import subprocess
import time

import pytest

REPO = pathlib.Path(__file__).parent.parent
OFFICE_INDEX = REPO / "static" / "office" / "index.js"
OFFICE_SRC = OFFICE_INDEX.read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

# index.js owns the panel and needs a DOM. The two decisions worth testing are
# pure, so they are lifted out and run on their own — the same approach
# tests/test_async_delegation_message_collapse.py uses for ui.js.
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

const liveWindow = src.match(/const LIVE_WINDOW_SECONDS = (\d+);/)[1];
const body = `const LIVE_WINDOW_SECONDS = ${liveWindow};\n`
  + 'const _liveSummaries = new Map(Object.entries(REMEMBERED));\n'
  + lift('delegationSummary') + '\n' + lift('looksLive') + '\n' + lift('storedTitle');

const api = new Function('REMEMBERED',
  body + '\nreturn { delegationSummary, looksLive, storedTitle };')(
    (JSON.parse(process.argv[3] || '{}').remembered) || {});
const input = JSON.parse(process.argv[3] || '{}');
process.stdout.write(JSON.stringify({
  summary: input.goals !== undefined
    ? api.delegationSummary(input.goals, input.fallback) : null,
  live: input.parent !== undefined ? api.looksLive(input.parent) : null,
  storedTitle: input.stored !== undefined ? api.storedTitle(input.stored) : null,
  liveWindow: Number(liveWindow),
}));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("office-sidebar") / "driver.cjs"
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


# ── naming the row after the work ────────────────────────────────────────────

def test_a_single_task_names_the_row(driver):
    out = run(driver, goals=["read README.md and list its sections"], fallback="Some chat")
    assert out["summary"] == "read README.md and list its sections"


def test_a_fan_out_names_the_first_task_and_counts_the_rest(driver):
    out = run(driver, goals=["read README.md", "list directories", "count tests"],
              fallback="Some chat")
    assert out["summary"] == "read README.md +2 more"


def test_the_subagent_prefix_is_stripped(driver):
    # Stored child rows are titled "Subagent: <goal>"; the prefix is noise in a
    # list where every row is a delegation.
    out = run(driver, goals=["Subagent: audit the routes"], fallback="Some chat")
    assert out["summary"] == "audit the routes"


def test_a_long_goal_is_truncated(driver):
    out = run(driver, goals=["x" * 80], fallback="Some chat")
    assert len(out["summary"]) == 44 and out["summary"].endswith("…")


def test_the_chat_title_is_the_fallback(driver):
    # A run with nothing readable still needs a name.
    out = run(driver, goals=[], fallback="Refactor the parser")
    assert out["summary"] == "Refactor the parser"
    assert run(driver, goals=["", "   "], fallback="Refactor the parser")["summary"] \
        == "Refactor the parser"


def test_an_unnameable_row_does_not_render_blank(driver):
    out = run(driver, goals=[], fallback=None)
    assert out["summary"] == "Untitled chat"


# ── the live marker ──────────────────────────────────────────────────────────

def now():
    return time.time()


def test_a_run_with_unfinished_children_and_recent_activity_is_live(driver):
    out = run(driver, parent={"latest_at": now(),
                              "children": [{"ended_at": None}, {"ended_at": 123}]})
    assert out["live"] is True


def test_a_finished_run_is_not_live(driver):
    out = run(driver, parent={"latest_at": now(),
                              "children": [{"ended_at": 1}, {"ended_at": 2}]})
    assert out["live"] is False


def test_a_long_dead_run_is_not_called_live(driver):
    # A child that never recorded an end is either running or was cut off. Only
    # recency separates them, and claiming a dead run is live is the worse
    # error — it would put a pulsing dot next to something that stopped days
    # ago.
    out = run(driver, parent={"latest_at": now() - 86_400,
                              "children": [{"ended_at": None}]})
    assert out["live"] is False


def test_a_run_with_no_timestamp_is_not_called_live(driver):
    out = run(driver, parent={"children": [{"ended_at": None}]})
    assert out["live"] is False


def test_an_empty_run_is_not_live(driver):
    assert run(driver, parent={"latest_at": now(), "children": []})["live"] is False


# ── wiring ───────────────────────────────────────────────────────────────────

def test_a_spawn_repaints_the_sidebar_immediately():
    # Waiting for the next poll would mean a delegation you just started is
    # missing from the list that is supposed to show it.
    at = OFFICE_SRC.index("_unsubscribe = _adapter.subscribe(")
    window = OFFICE_SRC[at:at + 600]
    assert "worker.spawn" in window and "renderSessionList()" in window


def test_the_live_row_is_built_from_adapter_state_not_the_listing():
    assert "function liveEntry()" in OFFICE_SRC
    assert "_adapter.getState()" in OFFICE_SRC[OFFICE_SRC.index("function liveEntry()"):]


def test_the_live_row_does_not_duplicate_its_stored_row():
    # Once the listing catches up, the same conversation must not appear twice.
    at = OFFICE_SRC.index("function sidebarEntries()")
    window = OFFICE_SRC[at:at + 900]
    assert "findIndex" in window and "parent_session_id === live.parent_session_id" in window


def test_clicking_the_live_row_returns_to_the_live_view():
    # There is no stored run to replay yet; replaying nothing would blank the
    # floor the user is watching.
    assert "row.dataset.liveEntry" in OFFICE_SRC
    at = OFFICE_SRC.index("row.dataset.liveEntry")
    assert "returnToLive()" in OFFICE_SRC[at:at + 200]


def test_the_listing_is_refreshed_while_the_panel_is_open():
    assert "SIDEBAR_REFRESH_MS" in OFFICE_SRC
    teardown_at = OFFICE_SRC.index("function teardownObservers()")
    body = OFFICE_SRC[teardown_at:OFFICE_SRC.index("\n}\n", teardown_at)]
    assert "clearInterval(_sidebarTimer)" in body, (
        "a timer left running keeps refetching for a panel nobody is looking at"
    )


def test_the_dot_is_rendered_and_styled():
    assert "office-session-live" in OFFICE_SRC
    assert 'aria-label="live"' in OFFICE_SRC
    assert ".office-session-live{" in CSS


# ── the name has to survive the run finishing ────────────────────────────────

def test_a_stored_row_is_named_from_its_children_not_the_chat(driver):
    # The bug this fixes: a row read "read README.md +2 more" while running and
    # reverted to "Untitled chat" once its live workers were swept, because
    # only the live row was ever named from goals.
    out = run(driver, stored={
        "parent_session_id": "chat-1",
        "title": "Untitled chat",
        "children": [
            {"title": "Subagent: read README.md"},
            {"title": "Subagent: count the tests"},
        ],
    })
    assert out["storedTitle"] == "read README.md +1 more"


def test_a_remembered_name_covers_the_gap_before_the_listing_catches_up(driver):
    # For a few seconds after a run ends there may be neither live workers nor
    # a stored row carrying the children yet.
    out = run(driver,
              stored={"parent_session_id": "chat-1", "title": "Untitled chat",
                      "children": []},
              remembered={"chat-1": "read README.md +2 more"})
    assert out["storedTitle"] == "read README.md +2 more"


def test_a_real_chat_title_is_still_used_when_there_is_nothing_better(driver):
    out = run(driver, stored={"parent_session_id": "chat-1",
                              "title": "Refactor the parser", "children": []})
    assert out["storedTitle"] == "Refactor the parser"


# ── switching runs resets the camera ─────────────────────────────────────────

def test_opening_another_run_resets_the_camera():
    # Carrying a zoomed-in camera across would leave it pointed at a worker
    # that does not exist on the floor being opened.
    at = OFFICE_SRC.index("function showHistory(")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}\n", at)]
    assert "_scene.resetView()" in body


def test_returning_to_live_resets_the_camera():
    at = OFFICE_SRC.index("function returnToLive()")
    body = OFFICE_SRC[at:OFFICE_SRC.index("\n}\n", at)]
    assert "_scene.resetView()" in body
