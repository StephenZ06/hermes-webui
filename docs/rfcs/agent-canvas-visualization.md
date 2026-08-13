# Agent Canvas: Live Subagent Workflow Visualization

- **Status:** Accepted
- **Author:** hermes-webui local
- **Created:** 2026-08-13

## Problem

Hermes already splits work across parallel subagents via `delegate_task`
(`tools/delegate_tool.py`, in the sibling hermes-agent runtime — see
Proposal below), but that activity is invisible to the user. The subagent
lifecycle events it emits are relayed up to hermes-webui's `on_tool`
callback (`api/streaming.py:8655`) but hit no matching branch there today
and are silently dropped — there is no way to see, at a glance, which
subagents are running, what spawned them, or how they're progressing.

The existing Kanban "Office View" (`static/panels.js:2626-2777`) is the
closest thing today, but it only visualizes Kanban-dispatched workers
(`task.worker_pid`) as a flat card grid, and explicitly does not cover
`delegate_task` subagents.

## Goals

- Real-time visualization of active subagent delegation as a node graph:
  parent agent → child subagents, with live status per node.
- Fluid, "Jarvis-style" animated presentation — pulsing/glowing active
  nodes, particle flow along active edges — not a static tree diagram.
- New top-level panel (peer to Kanban Office View), not embedded in chat.

## Non-goals

- No history/replay of past runs. Live-only: the canvas reflects the
  current run and clears when it completes.
- No per-node metrics (tokens, duration, tool-call counts) or log preview
  in v1. Nodes carry identity + status only.
- No changes to Kanban Office View or its worker model.

## Proposal

### Backend: relay existing subagent lifecycle events

Corrected after investigation (2026-08-13): `delegate_tool.py` is not part
of this repo — it lives in the sibling hermes-agent runtime
(`~/hermes-core-custom/tools/delegate_tool.py`, deployed at
`~/.hermes/hermes-agent/`). But that runtime is imported and run
**in-process** inside hermes-webui (`api/streaming.py` constructs
`AIAgent` directly in a background thread), not over any IPC boundary —
so this is still a single-repo (hermes-webui) change.

Better still: the events already exist and already cross into
hermes-webui today. `delegate_tool.py`'s child-progress callback already
emits `"subagent.start"` (on spawn, with `subagent_id`, `parent_id`,
`depth`, `model`, `toolsets`, `child_session_id`, `goal`) and
`"subagent.complete"` (on finish, with `status` — `ok`/`error`/`timeout`/
`interrupted`/`failed`/`completed`, `duration_seconds`, `summary`,
token/cost counts) via `parent_agent.tool_progress_callback`, which *is*
`on_tool` in `api/streaming.py:8655`. They just hit no matching branch in
`on_tool` today and are silently dropped.

The fix is two new branches in `on_tool`, alongside the existing
`'tool.started'`/`'tool.completed'` branches, each calling `put()` (the
same helper that already pushes `'tool'`/`'tool_complete'` into
`STREAMS[stream_id]`, which the browser already reads via
`api/chat/stream`):

- `'subagent.start'` → `put('subagent_spawn', {subagent_id, parent_id, depth, goal, model})`
- `'subagent.complete'` → `put('subagent_complete', {subagent_id, status})`

The upstream `"subagent.complete"` event carries more than this (`duration_seconds`,
`summary`, token/cost counts) but the v1 relay deliberately forwards only
`subagent_id` and `status` — per the "identity + status only" non-goal above,
confirmed after a task review caught an earlier draft leaking
`duration_seconds`/`summary` into the emitted event (2026-08-13).

No new SSE endpoint and no new contract — this rides the same
`api/chat/stream` connection the browser already has open for the active
turn, matching the "live only" scope decision. These events are journaled
like every other `put()` event, because `put()` unconditionally calls
`run_journal.append_sse_event` for whatever it emits — that's just how the
existing helper works, not something this feature opted into or skipped.
The added volume is negligible and replay is benign (`onSpawn` dedupes on
`subagent_id`). (No `status_change`
event exists upstream today — only spawn and terminal complete. A future
richer node-detail tier could also relay `"subagent.tool"`/
`"subagent.progress"`, which are emitted but currently unused here too.)

### Frontend: new `AgentCanvas` panel

- `static/vendor/d3-force/` — vendor the physics-only d3-force build
  (~20KB), following the existing single-purpose-vendored-lib pattern
  used for `static/vendor/katex` and `static/vendor/js-yaml`.
- `static/agent-canvas.js` — defines a `window.AgentCanvas` hook object
  (`onSpawn`/`onComplete`) that `static/messages.js`'s existing `_wireSSE`
  calls into from two new `source.addEventListener('subagent_spawn'|
  'subagent_complete', ...)` listeners (added next to the existing
  `'tool'`/`'tool_complete'` listeners at `messages.js:5589`/`5625`) —
  no separate `EventSource` of its own. Maintains node/edge state, drives
  a Canvas2D render loop:
  - Force-directed layout via d3-force ticks (physics only; rendering is
    custom, not d3's SVG/DOM binding).
  - Node glow/color keyed to status.
  - Particle flow animated along edges while the child node is active.
  - On `complete`: node fades and its edge stops animating, then the node
    is pruned after a ~5s grace period so the finish is visible rather
    than an abrupt disappearance.
- New nav entry alongside the Kanban Office View toggle to open the panel.

### Error handling

- SSE disconnect: canvas freezes in place with a "reconnecting…" banner;
  resumes live updates on reconnect. No event replay (consistent with
  live-only scope — a missed event is not backfilled).
  **Deferred (not implemented in v1):** no task in the implementation plan
  covered the "reconnecting…" banner, so it does not exist in the shipped
  panel. Today an SSE drop is visually indistinguishable from "no
  subagents currently running" — the canvas simply stops updating without
  any indicator. This is a known gap for a future task, not a description
  of current behavior.
- Orphaned nodes (parent completed but a child's `complete`/`error` event
  never arrives, e.g. subagent process crash): prune after a timeout so
  the canvas doesn't accumulate zombie nodes across a long session.

## Testing

- Backend: `on_tool` in `api/streaming.py` is a closure nested inside a
  large function and isn't unit-testable in isolation (no harness
  constructs it standalone) — same situation as `on_reasoning`. Follow
  the established precedent in
  `tests/test_issue4729_reasoning_sse_coalesce.py`: source-structure
  assertions that extract the closure body by text-slicing
  `api/streaming.py` and assert it contains the expected `put(...)` calls
  for `'subagent.start'`/`'subagent.complete'`.
- Frontend: manual browser verification (canvas rendering, animation, and
  live update behavior are not practically unit-testable); no automated
  test planned for the Canvas2D render loop itself.

## Open questions

- Multi-session concurrency: if multiple sessions each spawn subagents
  simultaneously, does the panel scope to the currently-viewed session
  only, or offer a session picker? (v1: current-session-only, since
  `on_tool`/`STREAMS` are already per-`stream_id`.)

## Rollout plan

Implementation starting now (2026-08-13) — see
`docs/superpowers/plans/2026-08-13-agent-canvas.md` for the task
breakdown.
