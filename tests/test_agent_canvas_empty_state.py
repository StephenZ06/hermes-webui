"""Regression test for the Agent Canvas empty-state placeholder.

Before this, the panel body was a blank <canvas> with nothing explaining
why it was empty when no subagents had spawned yet. Pins:
  - a static #agentCanvasEmpty placeholder exists inside #agentCanvasWrap
  - static/agent-canvas.js toggles its visibility based on node count
  - the "empty" threshold accounts for the synthetic root node that persists
    after every real subagent has faded out (size<=1, not size===0), or the
    placeholder would stay hidden forever after the first delegation run.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
INDEX = (REPO / "static" / "index.html").read_text(encoding="utf-8")
AGENT_CANVAS = (REPO / "static" / "agent-canvas.js").read_text(encoding="utf-8")


def test_empty_placeholder_exists_inside_wrap():
    wrap_start = INDEX.find('id="agentCanvasWrap"')
    assert wrap_start != -1, "#agentCanvasWrap not found"
    wrap_end = INDEX.find("</div>", INDEX.find("</div>", wrap_start) + 1)
    wrap_block = INDEX[wrap_start:wrap_end]
    assert 'id="agentCanvasEmpty"' in wrap_block, (
        "#agentCanvasEmpty placeholder must be nested inside #agentCanvasWrap"
    )
    assert "subagents" in wrap_block.lower(), (
        "placeholder text must explain why the canvas is empty"
    )


def test_draw_loop_updates_empty_state():
    assert "function _updateEmptyState()" in AGENT_CANVAS
    draw_start = AGENT_CANVAS.find("function _draw()")
    assert draw_start != -1, "_draw() not found"
    draw_end = AGENT_CANVAS.find("\n  function _scheduleRemoval(", draw_start)
    draw_body = AGENT_CANVAS[draw_start:draw_end]
    assert "_updateEmptyState()" in draw_body, (
        "_draw() must call _updateEmptyState() every visible frame so the "
        "placeholder reacts to spawn/complete/fade transitions"
    )


def test_empty_threshold_accounts_for_persistent_root_node():
    start = AGENT_CANVAS.find("function _updateEmptyState()")
    end = AGENT_CANVAS.find("\n  }", start)
    body = AGENT_CANVAS[start:end]
    assert "_nodes.size <= 1" in body, (
        "the empty check must be size<=1, not size===0 -- the synthetic "
        "ROOT_ID node is never pruned (_scheduleRemoval guards it), so after "
        "every real subagent fades out the map settles at size 1, not 0"
    )
