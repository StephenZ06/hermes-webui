"""Entrances that start and then stop halfway.

Three defects with one shape: motion that is set up correctly but lands on the
wrong element, the wrong render, or the wrong final frame.

1. The empty-state heading shimmer ended with the highlight parked on the last
   word, and left the heading gradient-clipped forever.
2. The project binder spent its row entrance on the throwaway "Scanning…"
   render, so the rows that actually arrive never animated.
3. A function-level re-import inside ``handle_get`` shadowed the module-level
   profile helpers for the whole handler, so ``GET /api/projects`` raised
   ``NameError`` on every call.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_shimmer_sweeps_past_the_end_of_the_text():
    """background-position percentages place the image against the box, so with
    background-size:200% the highlight sits at -W*P + W. P=0% is exactly the
    right edge — the accent ramp stopped on the final word."""
    js = read("static/motion-ui.js")
    assert "{ backgroundPosition: ['200% center', '-30% center'] }" in js
    assert "'0% center'" not in js


def test_shimmer_hands_the_heading_back_as_plain_text():
    js = read("static/motion-ui.js")
    assert "heading.classList.remove('motion-text-shimmer');" in js


def test_shimmer_resting_position_shows_no_accent():
    """Belt and braces for an interrupted sweep that never drops the class:
    the resting position must keep the highlight clear of the text."""
    css = read("static/style.css")
    block = css.split(".motion-text-shimmer{", 1)[1].split("}", 1)[0]
    assert "background-position:-30% center;" in block


def test_binder_entrance_skips_the_loading_render():
    """Every binder navigation renders twice — once with _projectBindLoading set
    and no folder rows, then again once the listing arrives. Keying only on the
    view burned the guard on the first, so the real rows never animated."""
    js = read("static/workspace.js")
    assert "if(!_projectBindLoading && bindViewKey !== _projectBindLastAnimatedKey){" in js
    # The key must still be recorded, or every render would re-animate.
    assert "_projectBindLastAnimatedKey = bindViewKey;" in js


def test_handle_get_does_not_shadow_module_level_profile_helpers():
    """A `from api.profiles import ...` inside handle_get makes those names
    locals of the ENTIRE handler, so every earlier branch using the bare name
    reads an unassigned local. GET /api/projects raised NameError on every
    call because of exactly this. Checks cellvars too: a bare use inside a
    list comprehension makes the name a cell, not a plain local."""
    from api import routes

    code = routes.handle_get.__code__
    bound_in_function = set(code.co_varnames) | set(code.co_cellvars)
    shadowed = bound_in_function & {"_profiles_match", "get_active_profile_name"}
    assert not shadowed, (
        f"handle_get rebinds module-level helper(s) {sorted(shadowed)} as function "
        "locals; earlier branches using the bare name will raise NameError"
    )


def test_profile_helpers_are_importable_from_routes_module_scope():
    """The shadowing fix relies on these staying module-level re-exports."""
    from api import routes

    assert callable(routes._profiles_match)
    assert callable(routes.get_active_profile_name)
