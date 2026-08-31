"""Coverage for the touch responsiveness and drawer-drag work.

Three separate causes of "the app does not feel native on a phone", none of
which is frame rate:

  1. The drawer snapped open at a fixed threshold instead of following the
     finger, so nothing moved at all until everything moved at once.
  2. Taps waited on the browser's double-tap-to-zoom timer, painted a grey
     highlight box, and produced no press acknowledgement.
  3. `transition: all` let a hover transition any property the rule touched,
     including layout ones, and panels chained their scroll to the page.
"""
import pathlib
import re


REPO_ROOT = pathlib.Path(__file__).parent.parent
STYLE_CSS = (REPO_ROOT / "static" / "style.css").read_text(encoding="utf-8")
BOOT_JS = (REPO_ROOT / "static" / "boot.js").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    nxt = src.find("\nfunction ", start + 1)
    return src[start:nxt] if nxt != -1 else src[start:]


class TestDrawerFollowsTheFinger:
    def test_drag_state_is_prepared_without_opening(self):
        # The drawer has to be laid out and paintable while it is being dragged,
        # but must not be "open" until the gesture is released.
        body = _fn(BOOT_JS, "_prepareMobileSidebarForDrag")
        assert "is-dragging" in body
        assert "mobile-open" not in body, "preparing a drag must not open the drawer"

    def test_transform_tracks_the_pointer(self):
        # The move handler measures the finger; the write itself is coalesced into
        # rAF so a burst of touchmoves costs one style write per painted frame.
        body = _fn(BOOT_JS, "_onPwaSidebarSwipeMove")
        assert "Math.min(dx,width)" in body.replace(" ", ""), "travel must be clamped to the viewport"
        assert "_scheduleSidebarDragFrame(swipe)" in body
        frame = _fn(BOOT_JS, "_scheduleSidebarDragFrame")
        assert "requestAnimationFrame" in frame
        assert "translate3d(calc(-100% + " in frame, "the drawer must be pinned to the finger"

    def test_css_transition_is_suspended_while_dragging(self):
        # A transition during the drag would make the drawer trail the finger.
        assert ".sidebar.is-dragging{transition:none!important;}" in STYLE_CSS

    def test_release_settles_on_velocity_as_well_as_position(self):
        body = _fn(BOOT_JS, "_settleMobileSidebarDrag")
        assert "_PWA_SIDEBAR_FLING_VELOCITY" in body, "a fast flick must open regardless of distance"
        assert "_PWA_SIDEBAR_SETTLE_FRACTION" in body
        assert "classList.remove('is-dragging')" in body, "the settle is handed back to CSS"

    def test_a_backwards_fling_closes_even_past_the_distance_threshold(self):
        body = _fn(BOOT_JS, "_settleMobileSidebarDrag")
        assert "velocity<-_PWA_SIDEBAR_FLING_VELOCITY" in body.replace(" ", "")

    def test_a_live_drag_is_only_ended_by_release(self):
        # Abandoning mid-drag used to drop the gesture state while leaving the
        # inline transform in place, freezing the drawer wherever the finger
        # was. A small backwards wobble or a bit of vertical drift was enough.
        body = _fn(BOOT_JS, "_onPwaSidebarSwipeMove")
        bail = body[body.index("if(!swipe.dragging){") :]
        assert "_pwaSidebarSwipe=null" in bail.split("if(dx>=")[0], (
            "the bail-out must sit inside the not-yet-dragging branch"
        )
        before_branch = body[: body.index("if(!swipe.dragging){")]
        assert "_pwaSidebarSwipe=null" not in before_branch, (
            "no unconditional bail-out may run once the drawer is being dragged"
        )

    def test_a_stranded_drag_is_always_cleaned_up(self):
        assert "function _clearStrandedSidebarDrag" in BOOT_JS
        for handler in ("_onPwaSidebarSwipeEnd", "_onPwaSidebarSwipeCancel"):
            assert "_clearStrandedSidebarDrag()" in _fn(BOOT_JS, handler), handler

    def test_cancel_restores_the_closed_state(self):
        body = _fn(BOOT_JS, "_onPwaSidebarSwipeCancel")
        assert "style.transform=''" in body.replace(" ", "")
        assert "is-dragging" in body

    def test_velocity_is_smoothed(self):
        body = _fn(BOOT_JS, "_onPwaSidebarSwipeMove")
        assert "swipe.vx*0.4" in body.replace(" ", ""), "one jittery sample must not decide the fling"


class TestTouchResponsiveness:
    def test_tap_delay_and_highlight_are_removed_from_controls(self):
        block = STYLE_CSS[STYLE_CSS.index("/* ── Touch responsiveness"):]
        block = block[: block.index("/* Hero text shimmer")]
        assert "touch-action:pan-y" in block
        assert "-webkit-tap-highlight-color:transparent" in block

    def test_controls_never_hand_the_horizontal_axis_back(self):
        # `manipulation` is pan-x + pan-y + pinch-zoom. It removes the tap delay
        # exactly like pan-y does, but it also gives the browser the horizontal
        # axis back, which re-enables its edge-swipe-back navigation on every
        # control and silently undoes the fix in d461309a8. pan-y removes the
        # delay without conceding the axis the drawer gesture needs.
        block = STYLE_CSS[STYLE_CSS.index("/* ── Touch responsiveness"):]
        block = block[: block.index("/* Hero text shimmer")]
        assert "touch-action:manipulation" not in block

    def test_the_block_does_not_reach_selectors_other_rules_own(self):
        # .project-chip (long-press) and the #4696 control group both chose
        # manipulation deliberately. This block sits later in the file, so
        # naming any of them here would silently override those decisions --
        # which is exactly how both broke.
        block = STYLE_CSS[STYLE_CSS.index("/* ── Touch responsiveness"):]
        block = block[: block.index("/* Hero text shimmer")]
        # Comments in this block name those selectors on purpose, explaining why
        # they are excluded, so the prose has to go before matching.
        code = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        at = code.index("touch-action:pan-y pinch-zoom")
        touch_rule = code[code.rindex("}", 0, at) + 1 : code.index("}", at) + 1]
        for owned in (".project-chip", ".panel-icon-btn", "[role=\"button\"]"):
            assert owned not in touch_rule, f"{owned} is owned by another rule"

    def test_horizontally_scrolling_chips_keep_their_axis(self):
        # .topbar-chips is overflow-x:auto on a phone; its chips must still pan.
        block = STYLE_CSS[STYLE_CSS.index("/* ── Touch responsiveness"):]
        block = block[: block.index("/* Hero text shimmer")]
        assert ".chip{touch-action:pan-x pan-y pinch-zoom;}" in block

    def test_press_feedback_is_scoped_to_coarse_pointers(self):
        block = STYLE_CSS[STYLE_CSS.index("/* ── Touch responsiveness"):]
        block = block[: block.index("/* Hero text shimmer")]
        assert "@media (hover:none) and (pointer:coarse)" in block
        assert "transform:scale(.97)" in block

    def test_press_feedback_is_composited_and_brief(self):
        block = STYLE_CSS[STYLE_CSS.index("/* ── Touch responsiveness"):]
        block = block[: block.index("/* Hero text shimmer")]
        durations = re.findall(r"transition:transform \.(\d+)s", block)
        assert durations, "press feedback must declare its own short transition"
        for d in durations:
            assert int(d) <= 12, "press acknowledgement must feel instant, not animated"

    def test_full_width_rows_do_not_scale(self):
        # Shrinking something that spans the viewport reads as the layout
        # flexing rather than the row being pressed.
        block = STYLE_CSS[STYLE_CSS.index("/* ── Touch responsiveness"):]
        block = block[: block.index("/* Hero text shimmer")]
        rows = block[block.index(".session-item:active,") :]
        assert "transform:none" in rows
        assert "background:var(--hover-bg)" in rows

    def test_reduced_motion_disables_press_scaling(self):
        block = STYLE_CSS[STYLE_CSS.index("/* ── Touch responsiveness"):]
        block = block[: block.index("/* Hero text shimmer")]
        assert "@media (prefers-reduced-motion:reduce)" in block


class TestFrameCost:
    def test_no_transition_all_remains(self):
        # `all` transitions every property the rule touches, layout included,
        # and forces the style system to diff all of them each frame.
        assert "transition:all" not in STYLE_CSS
        assert "transition: all" not in STYLE_CSS

    def test_replacement_lists_exclude_layout_properties(self):
        for decl in re.findall(r"transition:background-color[^;}]*", STYLE_CSS):
            for banned in ("width", "height", "margin", "padding", "top", "left"):
                assert banned not in decl, f"{banned} in {decl}"

    def test_panels_contain_their_scroll(self):
        block = STYLE_CSS[STYLE_CSS.index("/* Scroll containment."):]
        block = block[: block.index("/* ── Touch responsiveness")]
        for sel in (".file-tree", ".main-view-body", "#workspacesPanel"):
            assert sel in block, sel
        assert "overscroll-behavior:contain" in block


class TestHorizontalAxisIsNeverConceded:
    """Standing guard against the regression that keeps coming back.

    The browser's edge-swipe-back navigation is only suppressed while the page
    keeps the horizontal axis. Any rule that grants pan-x -- directly, or via
    `manipulation`, which is pan-x + pan-y + pinch-zoom -- hands it back for the
    elements it matches, and the left-edge drawer gesture stops working with no
    error anywhere. It has now broken twice this way, both times because a rule
    added for an unrelated reason (removing the tap delay) chose `manipulation`
    when `pan-y pinch-zoom` does the same job without conceding the axis.
    """

    # Selectors allowed to keep the horizontal axis, each for a recorded reason.
    # Adding to this set is a decision, not a formality: every entry widens the
    # surface on which the browser can claim an edge-swipe-back.
    ALLOWED_PAN_X = {
        # Genuinely horizontal surfaces.
        ".chip",                        # lives in .topbar-chips, overflow-x:auto on mobile
        ".mermaid-viewer-viewport",     # owns every gesture itself (touch-action:none)
        # #4696: iOS Safari's tap-delay removal is documented against
        # `manipulation` specifically. These were in place when the drawer
        # gesture last worked, so they are not what regressed it.
        "button", ".icon-btn", ".panel-icon-btn", ".send-btn", ".approval-btn", "[onclick]",
        # Long-press handling relies on manipulation; see test_project_chip_ui.
        ".project-chip",
        ".agent-canvas-card", ".agent-canvas-sidebar-item",
        ".agent-canvas-project-row", ".agent-canvas-pause-btn",
    }

    @staticmethod
    def _rules():
        stripped = re.sub(r"/\*.*?\*/", "", STYLE_CSS, flags=re.S)
        return re.findall(r"([^{}@]+)\{([^{}]*)\}", stripped)

    def test_no_rule_grants_pan_x_outside_the_allowlist(self):
        offenders = []
        for selectors, block in self._rules():
            value = ""
            for decl in block.split(";"):
                key, _, val = decl.partition(":")
                if key.strip().lower() == "touch-action":
                    value = val.strip().lower()
            if not value:
                continue
            grants_x = "pan-x" in value or value == "manipulation" or value == "auto"
            if not grants_x:
                continue
            for sel in (s.strip() for s in selectors.split(",")):
                if sel not in self.ALLOWED_PAN_X:
                    offenders.append(f"{sel} -> touch-action:{value}")
        assert not offenders, (
            "these hand the horizontal axis back to the browser, re-enabling "
            "edge-swipe-back navigation:\n  " + "\n  ".join(offenders)
        )

    def test_rows_the_drawer_gesture_crosses_keep_the_axis(self):
        # These are the ones that actually regressed: .session-item declared
        # pan-y, a later rule gave it manipulation, and the left-edge gesture
        # stopped working with nothing reporting a conflict.
        for sel in (".session-item", ".ws-row", ".workspace-panel-tab"):
            rules = [
                block for selectors, block in self._rules()
                if sel in [s.strip() for s in selectors.split(",")] and "touch-action" in block
            ]
            assert rules, f"{sel} must pin its touch-action"
            for block in rules:
                assert "pan-x" not in block and "manipulation" not in block, sel

    def test_scroll_containers_still_block_horizontal_overscroll(self):
        # The other half of the fix: overscroll-behavior-x stops the page
        # rubber-banding into a back navigation.
        for sel in (".main{", ".messages{"):
            rule = next(r for r in STYLE_CSS.split("\n") if sel in r)
            assert "overscroll-behavior-x:none" in rule, sel

    def test_no_selector_declares_conflicting_touch_action(self):
        # A later rule silently overriding an earlier touch-action is exactly
        # how this broke: .session-item had pan-y, and a new rule gave it
        # manipulation without anything flagging the contradiction.
        seen = {}
        conflicts = []
        for selectors, block in self._rules():
            for decl in block.split(";"):
                key, _, val = decl.partition(":")
                if key.strip().lower() != "touch-action":
                    continue
                val = val.strip().lower()
                for sel in (s.strip() for s in selectors.split(",")):
                    if sel in seen and seen[sel] != val:
                        conflicts.append(f"{sel}: {seen[sel]!r} then {val!r}")
                    seen[sel] = val
        assert not conflicts, "contradictory touch-action declarations:\n  " + "\n  ".join(conflicts)
