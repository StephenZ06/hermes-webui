"""The async-delegation results block must not read as a message the user sent.

When a background `delegate_task` fan-out finishes, hermes-agent injects its
consolidated results into the transcript as a **user-role** row. That text is
the model's evidence — per-task headers, statuses, api_call counts, transcript
paths — and every other client collapses it to a one-line event: the TUI via
`display_kind: 'async_delegation_complete'`, the CLI resume recap via
`_RESUME_EVENT_TEXT`. The WebUI was the outlier and rendered the whole wall in
a user bubble, so a six-subagent fan-out looked like the user had pasted a
wall of text into their own chat.

The runtime the WebUI uses runs the agent in-process, and that path does not
stamp `display_kind` (only the gateway and TUI delivery paths do — see
gateway/wake.py and tui_gateway/session_notifications.py), so the marker text
is the signal here. That string is already a contract on both sides: this
repo's tests/test_async_delegation_webui_bridge.py asserts on it, as does the
agent's own test_internal_notification_marker_82888.py. `display_kind` is
preferred whenever present so this improves on its own if that changes.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent
UI_JS = REPO / "static" / "ui.js"
UI_SRC = UI_JS.read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is required")

# The helpers are plain functions in a very large browser script. Rather than
# loading all of ui.js (which needs a DOM), lift the three functions under
# test and run them with the one dependency they have stubbed.
_DRIVER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

function lift(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('missing function: ' + name);
  // Walk braces from the first '{' after the signature to its match.
  let i = src.indexOf('{', start), depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) { i++; break; } }
  }
  return src.slice(start, i);
}

const markerLine = src.match(/const _ASYNC_DELEGATION_MARKER=[^\n]*\n/)[0];
const body = markerLine
  + lift('_isAsyncDelegationBatchText')
  + '\n' + lift('_asyncDelegationBatchInfo')
  + '\n' + lift('_isAsyncDelegationBatchMessage')
  + '\n' + lift('_asyncDelegationSummaryText');

// msgContent() is ui.js's own content extractor; the rows under test carry
// plain string content, which is all this needs.
const factory = new Function('msgContent', body + `
  return { _asyncDelegationBatchInfo, _isAsyncDelegationBatchMessage, _asyncDelegationSummaryText };
`);
const api = factory(m => (m && typeof m.content === 'string') ? m.content : '');

const input = JSON.parse(process.argv[3] || '{}');
const info = api._asyncDelegationBatchInfo(input.message);
process.stdout.write(JSON.stringify({
  info,
  detected: api._isAsyncDelegationBatchMessage(input.message),
  summary: info ? api._asyncDelegationSummaryText(info) : null,
}));
"""


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    path = tmp_path_factory.mktemp("async-deleg") / "driver.cjs"
    path.write_text(_DRIVER, encoding="utf-8")
    return path


def run(driver, message):
    proc = subprocess.run(
        [NODE, str(driver), str(UI_JS), json.dumps({"message": message})],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"driver failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


# A trimmed copy of the shape hermes-agent actually injects.
BATCH_TEXT = """[ASYNC DELEGATION BATCH COMPLETE — deleg_39b21f75]
A background fan-out unit you dispatched earlier — 6 subagent(s) — has finished.

Dispatched: 2026-09-09 15:12:46 (39s ago)
Role: leaf Model: ? Total duration: 40.0s

--- ✓ TASK 1/6: Read README.md (status=completed, api_calls=3, 18.46s) ---
Three sections.
--- ✓ TASK 2/6: List directories (status=completed, api_calls=3, 22.3s) ---
Nine directories.
--- ✓ TASK 3/6: Count tests (status=completed, api_calls=3, 18.07s) ---
None found.
--- ✓ TASK 4/6: Read rfcs (status=completed, api_calls=4, 26.27s) ---
Not found.
--- ✓ TASK 5/6: Count JS (status=completed, api_calls=3, 20.08s) ---
Zero.
--- ✓ TASK 6/6: Read pyproject (status=completed, api_calls=7, 38.94s) ---
Not a Python project.
"""


def user(text, **fields):
    row = {"role": "user", "content": text}
    row.update(fields)
    return row


# ── detection ────────────────────────────────────────────────────────────────

def test_a_delegation_batch_row_is_recognised(driver):
    out = run(driver, user(BATCH_TEXT))
    assert out["detected"] is True


def test_an_ordinary_user_message_is_left_alone(driver):
    # The whole point is that real messages keep rendering as messages.
    out = run(driver, user("Use delegate_task to run these six in parallel"))
    assert out["detected"] is False and out["info"] is None


def test_an_assistant_message_is_never_treated_as_a_delivery(driver):
    out = run(driver, {"role": "assistant", "content": BATCH_TEXT})
    assert out["detected"] is False


def test_a_stamped_row_is_recognised_even_without_the_marker(driver):
    # The gateway and TUI paths stamp display_kind; the WebUI's in-process path
    # does not. Honouring the stamp means this gets better on its own if that
    # ever changes.
    out = run(driver, user("consolidated results", display_kind="async_delegation_complete"))
    assert out["detected"] is True


# ── the summary a human reads ────────────────────────────────────────────────

def test_the_tally_is_read_from_the_task_headers_when_unstamped(driver):
    out = run(driver, user(BATCH_TEXT))
    info = out["info"]
    assert info["taskCount"] == 6
    assert info["completed"] == 6 and info["failed"] == 0
    assert info["durationSeconds"] == 40.0
    assert info["delegationId"] == "deleg_39b21f75"
    # JS renders 40.0 as "40"; a fractional duration keeps its decimal (see the
    # stamped-metadata case, which reads 9.5s).
    assert out["summary"] == "Background delegation finished — 6 subagents · all completed · 40s"


def test_failures_are_counted_and_named(driver):
    text = BATCH_TEXT.replace(
        "--- ✓ TASK 3/6: Count tests (status=completed, api_calls=3, 18.07s) ---",
        "--- ✗ TASK 3/6: Count tests (status=failed, api_calls=3, 18.07s) ---",
    )
    out = run(driver, user(text))
    assert out["info"]["failed"] == 1 and out["info"]["completed"] == 5
    assert "5 completed, 1 failed" in out["summary"], (
        "a failed subagent must be visible without expanding the card"
    )


def test_a_partial_tally_does_not_claim_a_clean_sweep(driver):
    # A truncated payload yields fewer task lines than the batch size. Saying
    # "all completed" there would be a summary that lies about the run.
    text = "\n".join(
        line for line in BATCH_TEXT.splitlines()
        if "TASK 3/6" not in line and "TASK 4/6" not in line
    )
    out = run(driver, user(text))
    assert "all completed" not in out["summary"]
    assert "of 6 completed" in out["summary"]


def test_stamped_metadata_wins_over_parsing(driver):
    out = run(driver, user(BATCH_TEXT, display_kind="async_delegation_complete",
                           display_metadata={"delegation_id": "deleg_x", "task_count": 3,
                                             "completed_count": 2, "failed_count": 1,
                                             "duration_seconds": 9.5}))
    info = out["info"]
    assert (info["taskCount"], info["completed"], info["failed"]) == (3, 2, 1)
    assert info["delegationId"] == "deleg_x" and info["durationSeconds"] == 9.5


def test_the_full_payload_is_kept_for_the_expanded_card(driver):
    # Collapsed, not discarded: the evidence is still one click away.
    out = run(driver, user(BATCH_TEXT))
    assert "TASK 6/6" in out["info"]["text"]


# ── rendering ────────────────────────────────────────────────────────────────

def test_the_row_renders_as_a_notice_rather_than_a_user_bubble():
    assert "async-delegation-row" in UI_SRC
    assert "row.dataset.role='async_delegation'" in UI_SRC, (
        "the row must not claim to be a user message: edit/retry affordances "
        "and 'last user message' lookups key off that role"
    )
    assert "details class=\"async-delegation-card" in UI_SRC, (
        "collapsed by default, expandable — the payload is kept, not dropped"
    )


def test_expanded_state_survives_a_rerender():
    # An open <details> serialises an `open` attribute into innerHTML, so
    # comparing against live innerHTML rebuilds and re-collapses the card while
    # the user is reading it. The process-wakeup card hit this first.
    at = UI_SRC.index("async-delegation-row")
    window = UI_SRC[at:at + 3000]
    assert "_delegationRenderedHtml" in window
    assert "_wasOpen" in window


def test_the_card_has_styling():
    assert ".async-delegation-card{" in CSS
    assert ".async-delegation-body{" in CSS
