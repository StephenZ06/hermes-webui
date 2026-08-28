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
        body = _fn(BOOT_JS, "_onPwaSidebarSwipeMove")
        assert "translate3d(calc(-100% + " in body, "the drawer must be pinned to the finger"
        assert "Math.min(dx,width)" in body.replace(" ", ""), "travel must be clamped to the viewport"

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
        assert "touch-action:manipulation" in block
        assert "-webkit-tap-highlight-color:transparent" in block

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
