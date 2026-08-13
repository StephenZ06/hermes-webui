"""Regression test for subagent lifecycle events reaching the browser.

The bug: delegate_tool.py (sibling hermes-agent runtime, imported in-process)
already emits "subagent.start"/"subagent.complete" through the child's
progress callback, which IS the parent agent's tool_progress_callback —
that's on_tool in api/streaming.py. But on_tool has no branch matching
those event_type strings, so every subagent spawn/complete is silently
swallowed before it reaches STREAMS or the browser.

This pins the two new branches so Agent Canvas
(docs/rfcs/agent-canvas-visualization.md) keeps working: 'subagent.start'
must put() a 'subagent_spawn' SSE event, 'subagent.complete' must put() a
'subagent_complete' SSE event, and both must carry subagent_id so the
frontend can pair a completion back to its spawn.

on_tool is a closure nested inside a large function and isn't
unit-testable in isolation (same situation as on_reasoning — see
test_issue4729_reasoning_sse_coalesce.py). These are source-structure
assertions on the closure body.
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
STREAMING = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")


def _on_tool_body() -> str:
    start = STREAMING.index("def on_tool(*cb_args, **cb_kwargs):")
    nxt = STREAMING.index("\n            def on_tool_start(", start + 1)
    return STREAMING[start:nxt]


def test_subagent_start_emits_subagent_spawn_event():
    body = _on_tool_body()
    assert "'subagent.start'" in body, (
        "on_tool must branch on the 'subagent.start' event_type "
        "delegate_tool.py emits on every subagent spawn"
    )
    assert "put('subagent_spawn'" in body, (
        "on_tool must put() a 'subagent_spawn' SSE event so the browser "
        "learns a subagent was spawned"
    )


def test_subagent_complete_emits_subagent_complete_event():
    body = _on_tool_body()
    assert "'subagent.complete'" in body, (
        "on_tool must branch on the 'subagent.complete' event_type "
        "delegate_tool.py emits when a subagent finishes"
    )
    assert "put('subagent_complete'" in body, (
        "on_tool must put() a 'subagent_complete' SSE event so the "
        "browser learns a subagent finished"
    )


def test_subagent_events_carry_subagent_id():
    body = _on_tool_body()
    spawn_start = body.index("put('subagent_spawn'")
    spawn_end = body.index("})", spawn_start) + 2
    assert "subagent_id" in body[spawn_start:spawn_end]

    complete_start = body.index("put('subagent_complete'")
    complete_end = body.index("})", complete_start) + 2
    assert "subagent_id" in body[complete_start:complete_end]


def test_subagent_branches_return_before_tool_boundary_logic():
    # Subagent lifecycle events are not tool-call boundaries — they must
    # return before falling into the reasoning-index-advance / tool-call
    # batching logic below, or a spawn/complete would get mis-treated as
    # a real tool call.
    body = _on_tool_body()
    subagent_branch_idx = body.index("'subagent.start'")
    boundary_comment_idx = body.index(
        "Advance reasoning index at tool-call boundaries"
    )
    assert subagent_branch_idx < boundary_comment_idx, (
        "the subagent.start/complete branch must sit before the "
        "tool-call-boundary logic, and must return, so it never falls "
        "through"
    )
