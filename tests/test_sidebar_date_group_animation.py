"""Smooth expand/collapse animation for the sidebar's date groups.

TODAY / THIS WEEK / LAST WEEK / OLDER collapse via a `grid-template-rows`
transition on `.session-date-body` (the same mechanism `.project-folder-sessions`
already uses), instead of an instant `display:none`.

Two facts make this non-trivial and are what these tests pin:

  * A collapsed date group does not render its rows at all, so *expanding* must
    re-render first and grow the fresh node from 0.
  * Collapsing must animate the live node (which still holds its rows) and only
    commit the state + re-render once the animation lands -- re-rendering first
    would drop the rows and pop.

The animation itself is driven by `_applyDateGroupCollapsedState`, exercised
here through a node harness against a fake element.
"""
import json
import pathlib
import subprocess
import textwrap

REPO_ROOT = pathlib.Path(__file__).parent.parent.resolve()
SESSIONS_JS = (REPO_ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
STYLE_CSS = (REPO_ROOT / "static" / "style.css").read_text(encoding="utf-8")


def _extract_function(source: str, name: str) -> str:
    marker = f"function {name}"
    start = source.index(marker)
    brace_start = source.index("{", start)
    depth = 0
    for idx in range(brace_start, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]
    raise AssertionError(f"Could not extract {name}")


def _run_animation_case(script_body: str) -> dict:
    functions = _extract_function(SESSIONS_JS, "_applyDateGroupCollapsedState")
    script = textwrap.dedent(
        f"""
        {functions}
        // Fake element: records the class list at every style flush so the
        // pre-state/target sequence is observable.
        function makeBody(initialClasses){{
          const classes = new Set(initialClasses || []);
          const snapshots = [];
          const inner = {{inert: false, classList: {{contains: c => c === 'session-date-inner'}}}};
          const body = {{
            classList: {{
              contains: c => classes.has(c),
              add: c => classes.add(c),
              remove: c => classes.delete(c),
              toggle: (c, on) => {{
                if (on === undefined) on = !classes.has(c);
                if (on) classes.add(c); else classes.delete(c);
                return on;
              }},
            }},
            get offsetHeight() {{ snapshots.push([...classes].sort().join(' ')); return 100; }},
            firstElementChild: inner,
          }};
          return {{body, classes, snapshots, inner}};
        }}
        {script_body}
        """
    )
    proc = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def test_date_group_collapse_is_a_grid_template_rows_transition():
    assert ".session-date-body{display:grid;grid-template-rows:1fr;" in STYLE_CSS
    assert ".session-date-body.is-collapsed{grid-template-rows:0fr;}" in STYLE_CSS
    assert ".session-date-body.no-transition{transition:none;}" in STYLE_CSS
    assert ".session-date-inner{overflow:hidden;min-height:0;}" in STYLE_CSS


def test_date_group_collapse_respects_reduced_motion():
    assert ".session-date-body{transition:none;}" in STYLE_CSS


def test_date_group_render_uses_the_animation_helper_and_inner_wrapper():
    assert "function _applyDateGroupCollapsedState(" in SESSIONS_JS
    assert "inner.className='session-date-inner';" in SESSIONS_JS
    # The expand hint travels through module state so the widely-relied-on
    # zero-arg render signature stays intact.
    assert "_pendingDateGroupAnimationLabel=g.label;" in SESSIONS_JS
    assert "function renderSessionListFromCache(){" in SESSIONS_JS
    # The old instant-collapse mechanism must be gone for date groups.
    assert "if(isGroupCollapsed){body.style.display='none';" not in SESSIONS_JS


def test_collapsing_animates_the_live_node_then_commits():
    result = _run_animation_case(
        """
        function _sessionPrefersReducedMotion(){ return false; }
        const {body, classes, snapshots, inner} = makeBody([]);
        _applyDateGroupCollapsedState(body, true, true);
        process.stdout.write(JSON.stringify({
          flushSnapshot: snapshots[0],
          final: [...classes].sort().join(' '),
          innerInert: inner.inert,
        }));
        """
    )
    # Pre-state is the un-collapsed node, committed with transitions disabled.
    assert result["flushSnapshot"] == "no-transition"
    assert result["final"] == "is-collapsed"
    assert result["innerInert"] is True


def test_expanding_grows_the_fresh_node_from_zero():
    result = _run_animation_case(
        """
        function _sessionPrefersReducedMotion(){ return false; }
        const {body, classes, snapshots, inner} = makeBody(['is-collapsed']);
        _applyDateGroupCollapsedState(body, false, true);
        process.stdout.write(JSON.stringify({
          flushSnapshot: snapshots[0],
          final: [...classes].sort().join(' ') || '<none>',
          innerInert: inner.inert,
        }));
        """
    )
    # The fresh node is first forced into the collapsed pre-state so that
    # removing it animates 0fr -> 1fr instead of popping in at full height.
    assert "is-collapsed" in result["flushSnapshot"]
    assert "no-transition" in result["flushSnapshot"]
    assert result["final"] == "<none>"
    assert result["innerInert"] is False


def test_reduced_motion_skips_the_animation_but_keeps_the_end_state():
    result = _run_animation_case(
        """
        function _sessionPrefersReducedMotion(){ return true; }
        const {body, classes, snapshots} = makeBody([]);
        _applyDateGroupCollapsedState(body, true, true);
        process.stdout.write(JSON.stringify({
          flushes: snapshots.length,
          flushSnapshot: snapshots[0],
          final: [...classes].sort().join(' '),
        }));
        """
    )
    # One flush, no pre-state hop, and the node still ends collapsed.
    assert result["flushes"] == 1
    assert "is-collapsed" in result["flushSnapshot"]
    assert result["final"] == "is-collapsed"
