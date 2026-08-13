"""Regression coverage: click-and-hold anywhere on a mouse-pointer session
row should start a folder drag, not just the dedicated drag handle.

Mouse has no competing long-press-menu or swipe gesture on the row body —
both are touch/pen-only (`_scheduleSessionLongPressMenu` is only called for
'pen' and touchstart; `_isSessionSwipeTarget` explicitly excludes 'mouse').
So a plain movement-while-pressed threshold is enough to start the drag,
matching how the dedicated handle already starts a drag immediately on
pointerdown+move (no artificial hold delay needed).

This is a source-structure assertion — `static/sessions.js` is a large,
non-modular script with no test harness that constructs its inline row
closures in isolation.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
SESSIONS = (REPO / "static" / "sessions.js").read_text(encoding="utf-8")


def _onpointermove_body() -> str:
    start = SESSIONS.index("el.onpointermove=(e)=>{")
    end = SESSIONS.index("\n    };\n", start)
    return SESSIONS[start:end]


def test_row_pointermove_starts_folder_drag_on_mouse_movement():
    body = _onpointermove_body()
    assert "_gesturePointerType==='mouse'" in body
    assert "_gestureState==='pressing'" in body
    assert "_startSessionDrag(e,el,el,s);" in body, (
        "moving the mouse while pressed on the row body must hand off to "
        "the same _startSessionDrag() the dedicated handle uses"
    )


def test_folder_drag_start_guards_against_readonly_and_special_modes():
    body = _onpointermove_body()
    assert "!readOnly" in body
    assert "!_sessionSelectMode" in body
    assert "!_renamingSid" in body
    assert "!_isSessionActionTarget(e.target)" in body


def test_folder_drag_start_is_idempotent_per_press():
    # Once the drag has started for this press, further pointermove events
    # must not re-invoke _startSessionDrag (it manages its own document-level
    # listeners from that point on) or fall through into _updateSessionGesture.
    body = _onpointermove_body()
    assert "if(_mouseFolderDragStarted) return;" in body
    assert "_mouseFolderDragStarted=true;" in body


def test_mouse_folder_drag_flag_resets_on_new_press():
    start = SESSIONS.index("el.onpointerdown=(e)=>{")
    end = SESSIONS.index("\n    };\n", start)
    body = SESSIONS[start:end]
    assert "_mouseFolderDragStarted=false;" in body, (
        "a new press must reset the flag, or a row could only ever start "
        "one mouse folder-drag for its whole DOM lifetime"
    )


def test_touch_pointer_type_still_bails_out_first():
    # The mouse-hold-drag addition must not touch the touch code path at all
    # — touch keeps using its separate touchstart/touchmove/touchend handlers.
    body = _onpointermove_body()
    touch_guard_idx = body.index("if(e.pointerType==='touch') return;")
    mouse_check_idx = body.index("_gesturePointerType==='mouse'")
    assert touch_guard_idx < mouse_check_idx, (
        "the touch early-return must come before any mouse-drag logic"
    )
