"""The completed-subagent summary reaches the side panel's Goal block.

Two halves of one path:

1. ``api/streaming.py``'s ``on_tool`` relay. delegate_tool.py's
   ``complete_kwargs`` already carries ``summary`` plus duration, token/cost
   counts, touched files and an output tail, and ``api/gateway_chat.py``'s
   ``_subagent_complete_fields`` already forwards all of it on the gateway
   path. The in-process path forwarded only ``subagent_id``/``status``, so
   every one of the detail panel's richer blocks stayed permanently empty for
   WebUI turns. That "identity + status only" v1 scope is deliberately
   retired here (see docs/rfcs/agent-canvas-visualization.md).

2. ``static/agent-canvas.js``'s ``renderDetail``. Once a node is terminal and
   has a summary, the Goal block shows the summary instead — what the
   subagent *did*, not what it was asked to do. The goal itself stays visible
   as the panel title.

Both are source-structure assertions: ``on_tool`` is a closure nested inside a
large function and ``renderDetail`` builds an HTML template string, so neither
is unit-testable in isolation (same situation as
test_agent_canvas_sse_events.py).
"""
import pathlib

REPO = pathlib.Path(__file__).parent.parent
STREAMING = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")
CANVAS = (REPO / "static" / "agent-canvas.js").read_text(encoding="utf-8")

# Every field delegate_tool.py puts in complete_kwargs and gateway_chat.py's
# _subagent_complete_fields already forwards. The two paths must agree, or
# the panel renders differently depending on whether the turn went through
# the gateway.
RELAYED_FIELDS = (
    "summary",
    "duration_seconds",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cost_usd",
    "api_calls",
    "files_read",
    "files_written",
    "output_tail",
)


def _on_tool_body() -> str:
    start = STREAMING.index("def on_tool(*cb_args, **cb_kwargs):")
    nxt = STREAMING.index("\n            def on_tool_start(", start + 1)
    return STREAMING[start:nxt]


def _subagent_complete_call() -> str:
    body = _on_tool_body()
    start = body.index("put('subagent_complete'")
    return body[start:body.index("})", start) + 2]


def _goal_block_body() -> str:
    start = CANVAS.index("function goalBlockHtml(node){")
    return CANVAS[start:CANVAS.index("\n  function ", start + 1)]


def test_relay_forwards_every_completion_field():
    call = _subagent_complete_call()
    for field in RELAYED_FIELDS:
        assert f"'{field}'" in call, (
            f"put('subagent_complete', {{...}}) must forward {field!r} — the "
            "detail panel renders it and delegate_tool.py already emits it "
            f"(got: {call!r})"
        )


def test_relay_reads_completion_fields_off_the_callback_kwargs():
    call = _subagent_complete_call()
    for field in RELAYED_FIELDS:
        assert f"cb_kwargs.get('{field}')" in call, (
            f"{field!r} must be read from cb_kwargs — that is where "
            "delegate_tool.py's child_progress_cb(**complete_kwargs) puts it"
        )


def test_relay_matches_the_gateway_paths_field_set():
    # api/gateway_chat.py already forwards this exact set on the gateway
    # path; a node must not gain or lose blocks depending on which path the
    # turn took.
    gateway = (REPO / "api" / "gateway_chat.py").read_text(encoding="utf-8")
    start = gateway.index("def _subagent_complete_fields(")
    gateway_fields = gateway[start:gateway.index("\n\n\ndef ", start)]
    call = _subagent_complete_call()
    for field in RELAYED_FIELDS:
        assert f'"{field}"' in gateway_fields and f"'{field}'" in call, (
            f"{field!r} is forwarded on one path but not the other"
        )


def test_goal_block_shows_the_summary_once_terminal():
    # The block keeps its slot in the panel and swaps its label, so a
    # completed card reads as what the subagent did.
    assert "TERMINAL_STATUSES.has(node.status) && node.summary" in _goal_block_body(), (
        "renderDetail must decide between goal and summary on "
        "terminal-status + summary-present, so a still-running subagent "
        "keeps showing its goal"
    )


def test_goal_block_label_follows_what_it_shows():
    assert "'Summary' : 'Goal'" in _goal_block_body(), (
        "the block's label must swap with its content — labelling a summary "
        "'Goal' is what made the panel confusing in the first place"
    )


def test_no_separate_summary_block_remains():
    # Rendering both would show the same text twice on the gateway path,
    # which already forwards summary.
    start = CANVAS.index("function renderDetail()")
    body = CANVAS[start:CANVAS.index("\n  function tickDurations", start + 1)]
    assert body.count("agent-canvas-detail-label\">Summary") == 0, (
        "the old standalone Summary block must be gone — the Goal block "
        "now carries the summary"
    )
