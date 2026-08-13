"""Regression test: static/messages.js must relay the subagent_spawn /
subagent_complete SSE events (added in api/streaming.py, see
test_agent_canvas_sse_events.py) to window.AgentCanvas, or Task 1's
backend work has no frontend consumer and Agent Canvas never updates.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
MESSAGES = (REPO / "static" / "messages.js").read_text(encoding="utf-8")


def test_subagent_spawn_listener_calls_agent_canvas():
    assert "addEventListener('subagent_spawn'" in MESSAGES
    start = MESSAGES.index("addEventListener('subagent_spawn'")
    end = MESSAGES.index("});", start) + 3
    assert "AgentCanvas.onSpawn" in MESSAGES[start:end]


def test_subagent_complete_listener_calls_agent_canvas():
    assert "addEventListener('subagent_complete'" in MESSAGES
    start = MESSAGES.index("addEventListener('subagent_complete'")
    end = MESSAGES.index("});", start) + 3
    assert "AgentCanvas.onComplete" in MESSAGES[start:end]
