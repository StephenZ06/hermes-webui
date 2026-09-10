"""The app-wide loading placeholder is an indeterminate progress bar (was a
spinning ring), it paints an opaque ground so it stands in front of a panel
rather than letting stale content bleed through, and the panels that fetch on
switch drop it in synchronously before awaiting."""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
PANELS = (REPO / "static" / "panels.js").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    i = CSS.index(selector)
    return CSS[i:CSS.index("}", i) + 1]


def test_the_placeholder_is_a_bar_not_a_ring():
    rule = _rule(".loading-spinner{")
    assert "border-radius:999px" in rule and "height:3px" in rule
    assert "border-radius:50%" not in rule
    # the moving fill
    assert ".loading-spinner::after{" in CSS
    assert "@keyframes loading-bar-slide" in CSS
    # the old spin keyframe is gone
    assert "loading-spinner-spin" not in CSS


def test_the_placeholder_covers_what_is_behind_it():
    assert "background:var(--bg)" in _rule(".loading-spinner-wrap{")
    assert "background:var(--bg)" in _rule(".loading-spinner-wrap--overlay{")


def test_reduced_motion_is_respected():
    assert "@media (prefers-reduced-motion:reduce)" in CSS
    i = CSS.index("@media (prefers-reduced-motion:reduce)")
    assert ".loading-spinner::after" in CSS[i:i + 200]


def test_fetching_panels_show_the_loader_before_awaiting():
    assert "function _panelLoading(el)" in PANELS
    for fn, anchor in [
        ("loadSkills", "_panelLoading(box)"),
        ("loadAgentDefinitions", "_panelLoading(box)"),
        ("loadKanban", "_panelLoading(board)"),
        ("loadMemory", "_panelLoading(panel)"),
        ("loadProfilesPanel", "_panelLoading(panel)"),
        ("loadWorkspacesPanel", "_panelLoading(panel)"),
    ]:
        start = PANELS.index("function " + fn + "(")
        body = PANELS[start:PANELS.index("\n}\n", start)]
        head = body[:body.index("await ")] if "await " in body else body
        assert anchor in head, f"{fn} must show the loader before its first await"


def test_the_loader_is_not_forced_over_cached_content():
    body = PANELS[PANELS.index("function _panelLoading(el)"):]
    body = body[:body.index("\n}\n")]
    assert "el.querySelector('.loading-spinner')" in body and "return" in body
