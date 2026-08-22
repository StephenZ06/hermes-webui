"""Regression test for the Agent Canvas delegation tree wrap-to-grid layout.

Before this, `.agent-canvas-tree` had `width:max-content` and
`.agent-canvas-children` had no `flex-wrap`, so a parent with many concurrent
subagent children rendered one endless horizontal row -- the user had to
scroll end-to-end to see the whole fan-out. Pins:
  - the tree container is bounded by its scroll parent's width instead of
    growing to fit content
  - the children row wraps onto additional rows instead of growing sideways
  - the old per-child stem (`.agent-canvas-branch::before`) and shared rail
    (`.agent-canvas-rail`) connectors are gone, replaced by a single trunk
    line into a `.agent-canvas-children-cluster` box (agent-canvas.js's
    buildChildrenRow), which is what makes wrapping onto multiple rows
    visually sane in the first place
"""
import pathlib
import re

REPO = pathlib.Path(__file__).parent.parent
STYLE = (REPO / "static" / "style.css").read_text(encoding="utf-8")
AGENT_CANVAS = (REPO / "static" / "agent-canvas.js").read_text(encoding="utf-8")


def _rule(selector_substr: str) -> str:
    """Return the CSS block starting at selector_substr, up to its matching
    closing brace (brace-depth aware, so @keyframes blocks with multiple
    nested {...} stops are captured whole, not cut off at the first stop).
    """
    idx = STYLE.find(selector_substr)
    assert idx != -1, f"CSS rule for {selector_substr!r} not found"
    depth = 0
    for i in range(idx, len(STYLE)):
        if STYLE[i] == "{":
            depth += 1
        elif STYLE[i] == "}":
            depth -= 1
            if depth == 0:
                return STYLE[idx : i + 1]
    raise AssertionError(f"unterminated CSS block for {selector_substr!r}")


def test_tree_container_is_not_width_max_content():
    rule = _rule(".agent-canvas-tree{")
    assert "width:max-content" not in rule, (
        "`.agent-canvas-tree` must not force unbounded width -- that's what "
        "made a wide fan-out require horizontal scrolling end-to-end"
    )


def test_children_row_wraps():
    rule = _rule(".agent-canvas-children{")
    assert "flex-wrap:wrap" in rule, (
        "`.agent-canvas-children` must wrap siblings onto new rows instead "
        "of growing one endless row"
    )


def test_old_per_child_stem_and_rail_removed():
    assert ".agent-canvas-branch::before" not in STYLE, (
        "old per-child connector stem should be removed -- it can't be "
        "routed sanely once children wrap onto more than one row"
    )
    assert ".agent-canvas-rail{" not in STYLE, (
        "old shared horizontal rail should be removed in favor of the "
        "trunk + cluster-box connector"
    )


def test_cluster_box_exists_and_used_at_every_depth():
    assert ".agent-canvas-children-cluster{" in STYLE
    # buildChildrenRow is the single code path used for both the root's
    # children and any nested branch's children (called from renderTree()
    # and recursively from buildBranch()) -- one connector scheme at every
    # nesting depth, no special-casing.
    fn_start = AGENT_CANVAS.find("function buildChildrenRow(")
    assert fn_start != -1, "buildChildrenRow() not found"
    fn_end = AGENT_CANVAS.find("\n  }", fn_start)
    fn_body = AGENT_CANVAS[fn_start:fn_end]
    assert "agent-canvas-children-cluster" in fn_body
    assert "agent-canvas-trunk" in fn_body
    assert re.search(r"buildChildrenRow\(kids,\s*!TERMINAL_STATUSES", AGENT_CANVAS), (
        "buildBranch() must call buildChildrenRow() for its own children too, "
        "not just the root's"
    )


def test_card_entrance_is_staggered_spring():
    rule = _rule("@keyframes agent-canvas-card-spring-in{")
    assert "scale(1.03)" in rule or "scale(1.0" in rule, (
        "spring keyframe should overshoot slightly before settling"
    )
    assert "agent-canvas-card-spring-in" in _rule(".agent-canvas-card{")
    assert "staggerIndex" in AGENT_CANVAS
    assert "animationDelay" in AGENT_CANVAS
