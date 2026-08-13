"""Regression coverage: click-and-hold anywhere on a TOUCH session row
should start a folder drag, matching the mouse behavior added earlier
(test_session_row_mouse_hold_drag.py).

Touch is the harder case: the row already runs a long-press-for-menu timer
(_scheduleSessionLongPressMenu, touchstart-triggered) and a horizontal
swipe-to-archive/delete gesture on the same surface. The fix:
_scheduleSessionLongPressMenu's timer now only ARMS (_longPressArmed=true)
instead of opening the menu immediately, leaving a window for a subsequent
finger movement to redirect into _startSessionDrag() via a dedicated
pointermove listener (native Pointer Events fire before their Touch Event
counterparts for the same input, so this listener gets first refusal before
the existing touchmove-driven swipe tracking runs). If the finger never
moves and lifts instead, _finishSessionGesture opens the menu at that point.

Source-structure assertions — same precedent as
test_session_row_mouse_hold_drag.py.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
SESSIONS = (REPO / "static" / "sessions.js").read_text(encoding="utf-8")


def _block(start_marker: str, end_marker: str) -> str:
    start = SESSIONS.index(start_marker)
    end = SESSIONS.index(end_marker, start)
    return SESSIONS[start:end]


def test_long_press_timer_arms_instead_of_opening_menu_directly():
    body = _block(
        "const _scheduleSessionLongPressMenu=()=>{",
        "const _isSessionSwipeTarget=()=>{",
    )
    assert "_longPressArmed=true;" in body
    assert "_openSessionActionMenu" not in body, (
        "the timer must no longer open the menu directly — that would open "
        "it before a subsequent move could redirect into a drag"
    )


def test_finish_gesture_opens_menu_on_release_when_armed_and_not_dragged():
    body = _block(
        "const _finishSessionGesture=(clientX,clientY,target,pointerType)=>{",
        "\n    };\n",
    )
    assert "_longPressArmed&&_gestureState==='pressing'" in body
    assert "_openSessionActionMenu(s, el);" in body


def test_touch_pointermove_listener_starts_folder_drag_when_armed():
    body = _block(
        "el.addEventListener('pointermove',(e)=>{\n      if(e.pointerType!=='touch') return;",
        "});\n    el.onpointercancel=(e)=>{",
    )
    assert "_touchFolderDragStarted" in body
    assert "_longPressArmed" in body
    assert "_gestureState!=='pressing'" in body
    assert "_startSessionDrag(e,el,el,s);" in body, (
        "moving the finger while armed must hand off to the same "
        "_startSessionDrag() the handle and mouse path use"
    )


def test_touch_drag_start_guards_against_readonly_and_special_modes():
    body = _block(
        "el.addEventListener('pointermove',(e)=>{\n      if(e.pointerType!=='touch') return;",
        "});\n    el.onpointercancel=(e)=>{",
    )
    assert "readOnly" in body
    assert "_sessionSelectMode" in body
    assert "_renamingSid" in body
    assert "_isSessionActionTarget(e.target)" in body


def test_touchmove_suppresses_native_scroll_once_dragging():
    body = _block(
        "el.addEventListener('touchmove',(e)=>{",
        "},{passive:false});",
    )
    assert "_touchFolderDragStarted" in body
    assert "e.preventDefault();" in body, (
        "once the folder drag has started, native touch scroll (the row has "
        "touch-action:pan-y) must be suppressed for the rest of the gesture "
        "or the list scrolls underneath the drag ghost"
    )


def test_begin_gesture_resets_touch_drag_state_on_new_press():
    body = _block(
        "const _beginSessionGesture=(clientX,clientY,pointerType='')=>{",
        "\n    };\n",
    )
    assert "_longPressArmed=false;" in body
    assert "_touchFolderDragStarted=false;" in body
