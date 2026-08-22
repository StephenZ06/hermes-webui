"""Regression test for the Agent Canvas empty-state placeholder.

Before this, the panel body was a blank <canvas> with nothing explaining
why it was empty when no subagents had spawned yet. Pins:
  - static/panels.js mounts AgentCanvas into #agentCanvasWrap, and
    static/agent-canvas.js's mount() injects a #agentCanvasEmpty placeholder
    into it at runtime (the tree/DOM-based render replaced the old
    static-markup + <canvas> _draw() loop design)
  - updateEmptyState() toggles its visibility based on whether the root node
    has any children, and is called on every render() pass so it reacts to
    spawn/complete/fade transitions
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
INDEX = (REPO / "static" / "index.html").read_text(encoding="utf-8")
PANELS = (REPO / "static" / "panels.js").read_text(encoding="utf-8")
AGENT_CANVAS = (REPO / "static" / "agent-canvas.js").read_text(encoding="utf-8")


def test_empty_placeholder_mounted_inside_wrap():
    assert 'id="agentCanvasWrap"' in INDEX, "#agentCanvasWrap not found"
    assert "window.AgentCanvas.mount($('agentCanvasWrap'))" in PANELS, (
        "AgentCanvas must be mounted into #agentCanvasWrap"
    )
    mount_start = AGENT_CANVAS.find("function mount(container)")
    assert mount_start != -1, "mount() not found"
    mount_end = AGENT_CANVAS.find("\n  function ", mount_start + 1)
    mount_body = AGENT_CANVAS[mount_start:mount_end]
    assert 'id="agentCanvasEmpty"' in mount_body, (
        "mount() must inject the #agentCanvasEmpty placeholder into the container"
    )
    assert "subagents" in mount_body.lower(), (
        "placeholder text must explain why the canvas is empty"
    )


def test_render_updates_empty_state():
    assert "function updateEmptyState()" in AGENT_CANVAS
    render_start = AGENT_CANVAS.find("function render()")
    assert render_start != -1, "render() not found"
    render_end = AGENT_CANVAS.find("\n  }", render_start)
    render_body = AGENT_CANVAS[render_start:render_end]
    assert "updateEmptyState()" in render_body, (
        "render() must call updateEmptyState() every pass so the "
        "placeholder reacts to spawn/complete/fade transitions"
    )


def test_empty_threshold_uses_root_children_not_node_count():
    start = AGENT_CANVAS.find("function updateEmptyState()")
    end = AGENT_CANVAS.find("\n  }", start)
    body = AGENT_CANVAS[start:end]
    assert "childrenOf(ROOT_ID).length" in body, (
        "the empty check must look at whether the root has any children -- "
        "the synthetic ROOT_ID node itself is never pruned, so a raw "
        "_nodes.size check would never read as empty again after the first "
        "delegation run"
    )
