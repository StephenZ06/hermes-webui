"""The subagent SSE events must have a frontend consumer.

api/streaming.py relays subagent_spawn / subagent_tool / subagent_complete
(see test_agent_canvas_sse_events.py); static/messages.js has to hand them to
whatever draws the delegation. Without that the backend work has no consumer
and the view never updates — the bug this file was opened for.

That consumer was Agent Canvas and is now the Office; the Agent Canvas panel
was removed once the Office covered it. The rule is unchanged, so the test
followed the consumer rather than being deleted with the panel.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
MESSAGES = (REPO / "static" / "messages.js").read_text(encoding="utf-8")


def _listener_body(event):
    marker = f"addEventListener('{event}'"
    assert marker in MESSAGES, f"no listener for {event}"
    start = MESSAGES.index(marker)
    return MESSAGES[start:MESSAGES.index("});", start) + 3]


def test_subagent_spawn_reaches_the_office():
    assert "HermesOffice.onSpawn" in _listener_body("subagent_spawn")


def test_subagent_tool_reaches_the_office():
    assert "HermesOffice.onToolActivity" in _listener_body("subagent_tool")


def test_subagent_complete_reaches_the_office():
    assert "HermesOffice.onComplete" in _listener_body("subagent_complete")


def test_the_retired_panel_is_no_longer_fed():
    # Agent Canvas' module stays loaded for the Scheduled-jobs delegation
    # diagram, but nothing should be accumulating live state for a panel that
    # can no longer be opened.
    for event in ("subagent_spawn", "subagent_tool", "subagent_complete"):
        assert "AgentCanvas" not in _listener_body(event)
