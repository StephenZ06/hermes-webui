"""Regression test pinning the vendor script load order for Agent Canvas.

The bug this guards against: the four d3-force vendor scripts have a strict
dependency order — d3-timer, d3-dispatch, and d3-quadtree must each load
before d3-force.min.js (which references their globals at parse time), and
all four must load before static/agent-canvas.js (which calls
d3.forceSimulation() etc. at panel-mount time). All five tags carry `defer`,
so browsers execute them in source order — but nothing enforces that source
order at edit time. If a future edit reorders these tags (e.g. an alphabetize
pass, or inserting a new vendor script in the wrong spot), `window.d3` ends
up missing `forceSimulation` and the whole Agent Canvas panel silently goes
blank with no console error (see docs/rfcs/agent-canvas-visualization.md).

This is a source-structure assertion in the same style as
test_agent_canvas_sse_events.py: read static/index.html as text, locate each
script tag by its `src` substring, and assert they appear in strictly
increasing index order.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
INDEX_HTML = (REPO / "static" / "index.html").read_text(encoding="utf-8")

# Dependency order: each of these must appear (and load) before the next.
EXPECTED_ORDER = [
    "static/vendor/d3-force/3.0.0/d3-timer.min.js",
    "static/vendor/d3-force/3.0.0/d3-dispatch.min.js",
    "static/vendor/d3-force/3.0.0/d3-quadtree.min.js",
    "static/vendor/d3-force/3.0.0/d3-force.min.js",
    "static/agent-canvas.js",
]


def _index_of(src_substring: str) -> int:
    idx = INDEX_HTML.find(src_substring)
    assert idx != -1, (
        f"expected a <script src=\"...{src_substring}...\"> tag in "
        "static/index.html but found none"
    )
    return idx


def test_all_expected_scripts_present():
    for src_substring in EXPECTED_ORDER:
        _index_of(src_substring)


def test_d3_force_vendor_and_agent_canvas_scripts_load_in_dependency_order():
    indexes = [_index_of(src) for src in EXPECTED_ORDER]
    assert indexes == sorted(indexes), (
        "d3-force vendor scripts and agent-canvas.js must appear in "
        f"static/index.html in this exact relative order: {EXPECTED_ORDER}. "
        "Out-of-order loading leaves window.d3 missing forceSimulation and "
        "the Agent Canvas panel renders blank with no console error."
    )


def test_each_script_tag_is_deferred():
    # All five must be `defer` (not plain sync, not `async`) so source order
    # is guaranteed to match execution order — that guarantee is the whole
    # basis for the ordering assertion above.
    for src_substring in EXPECTED_ORDER:
        idx = _index_of(src_substring)
        tag_start = INDEX_HTML.rfind("<script", 0, idx)
        tag_end = INDEX_HTML.index(">", idx)
        tag = INDEX_HTML[tag_start:tag_end + 1]
        assert "defer" in tag, (
            f"script tag containing {src_substring!r} must carry `defer` so "
            f"it executes in source order: {tag}"
        )
        assert "async" not in tag, (
            f"script tag containing {src_substring!r} must not be `async` — "
            f"async breaks the source-order execution guarantee: {tag}"
        )
