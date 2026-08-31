from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSIONS_JS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
CANVAS_JS = (ROOT / "static" / "agent-canvas.js").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def _fn(src, name):
    """Slice from a marker to the end of the chip-building block."""
    start = src.index(name)
    return src[start:start + 1400]


def test_folder_toggle_is_not_deferred_behind_a_double_click_timer():
    """A project folder in the chat sidebar took 220ms to react to any click.

    The handler wrapped every toggle in setTimeout(..., 220) so it could find out
    whether a second click was coming (double-click renames the project). That
    put the delay on every expand and every collapse -- the common action paying
    for the rare one -- while the Agent Canvas rows, which toggle straight out of
    onclick, felt instant by comparison. Measured before/after in a real browser:
    220.6ms -> 0.3ms to flip the expanded class.

    A double-click still works: it fires two clicks, the folder toggles twice and
    lands back where it started, then the rename input opens.
    """
    block = _fn(SESSIONS_JS, "chip.onclick=")
    assert "setTimeout" not in block.split("chip.ondblclick")[0], (
        "the folder toggle must run on the click, not behind a double-click timer"
    )
    assert "chip.onclick=(e)=>{ toggleFolder(e); };" in SESSIONS_JS
    assert "_pClickTimer" not in SESSIONS_JS, (
        "the deferred-click timer and every reference to it should be gone"
    )
    # The rename path stays reachable.
    assert "chip.ondblclick=" in SESSIONS_JS and "_startProjectRename" in SESSIONS_JS


def test_canvas_project_rows_still_toggle_synchronously():
    """The reference behaviour the chat rows are being matched to."""
    start = CANVAS_JS.index(".agent-canvas-project-row').forEach")
    block = CANVAS_JS[start:start + 600]
    assert "setTimeout" not in block


def test_chat_folder_row_is_the_same_height_as_a_canvas_folder_row():
    """Both views render `.project-chip.project-folder-row` inside
    `.project-folder-list`, so they share padding and font size. The chat row
    additionally carries a kebab button, and while that button was 20px tall it
    -- not the row's text -- set the row height. Both the kebab and the chevron
    are 16px so the text line box is the tallest child again and the padding
    actually controls the row height: 24px at the default font size, measured on
    the real rendered rows in both views.
    """
    assert ".project-folder-list .project-chip{width:100%;box-sizing:border-box;border-radius:8px;padding:3px 8px;" in STYLE_CSS, (
        "both views share this selector, so the row height must be set here or they diverge"
    )
    # Coarse pointers keep a real touch target; shrinking the row is a mouse-density
    # change, not a reason to ship a 29px tap target on a phone.
    assert ".project-folder-list .project-chip{padding:9px 8px;min-height:40px;}" in STYLE_CSS, (
        "the touch-target override must survive the desktop density change"
    )
    assert ".project-folder-kebab{width:16px;height:16px;" in STYLE_CSS, (
        "a kebab taller than the row's text line box silently drives the row height"
    )
    assert ".project-folder-chevron{" in STYLE_CSS
    chevron = STYLE_CSS[STYLE_CSS.index(".project-folder-chevron{"):]
    chevron = chevron[:chevron.index("}")]
    assert "width:16px;height:16px" in chevron, "chevron and kebab should match"


def test_folder_row_has_a_press_state_and_a_matched_chevron_curve():
    assert ".project-folder-list .project-chip:active{background:var(--hover-bg);" in STYLE_CSS, (
        "a click on the row should show immediately, not only once the list has expanded"
    )
    chevron = STYLE_CSS[STYLE_CSS.index(".project-folder-chevron{"):]
    chevron = chevron[:chevron.index("}")]
    assert "cubic-bezier(.2,.8,.2,1)" in chevron, (
        "the chevron should turn on the same curve the session list expands with"
    )
    sessions = STYLE_CSS[STYLE_CSS.index(".project-folder-sessions{"):]
    sessions = sessions[:sessions.index("}")]
    assert "cubic-bezier(.2,.8,.2,1)" in sessions
