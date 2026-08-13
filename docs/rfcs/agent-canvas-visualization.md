# Agent Canvas: Live Subagent Workflow Visualization

- **Status:** Proposed
- **Author:** hermes-webui local
- **Created:** 2026-08-13

## Problem

Hermes already splits work across parallel subagents via `delegate_task`
(`tools/delegate_tool.py`), but that activity is invisible to the user.
The in-memory `_active_subagents` registry lives inside the `hermes` agent
container's process memory with no reachable endpoint — there is no way to
see, at a glance, which subagents are running, what spawned them, or how
they're progressing.

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

### Backend: SSE event feed

Add lifecycle hooks around `_active_subagents` in `tools/delegate_tool.py`
that emit `agent_tree_event` messages on the existing SSE channel used by
other WebUI event streams (see `docs/rfcs/session-sse-contract-v1.md` for
the established contract pattern this should follow):

- `spawn` — `{id, parent_id, agent_type, name}`
- `status_change` — `{id, status}` (running / tool-call / done / error)
- `complete` — `{id}`

Events are tagged with the session id so the frontend can scope a canvas
to the active session. No persistence layer — this is a live stream only,
matching the "live only" scope decision.

### Frontend: new `AgentCanvas` panel

- `static/vendor/d3-force/` — vendor the physics-only d3-force build
  (~20KB), following the existing single-purpose-vendored-lib pattern
  used for `static/vendor/katex` and `static/vendor/js-yaml`.
- `static/agent-canvas.js` — subscribes to the SSE feed, maintains
  node/edge state, drives a Canvas2D render loop:
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
- Orphaned nodes (parent completed but a child's `complete`/`error` event
  never arrives, e.g. subagent process crash): prune after a timeout so
  the canvas doesn't accumulate zombie nodes across a long session.

## Testing

- Backend: unit tests in the style of `tests/test_kanban_office_view.py`,
  asserting `agent_tree_event` emission and shape on spawn / status_change
  / complete / error paths in `delegate_tool.py`.
- Frontend: manual browser verification (canvas rendering, animation, and
  live update behavior are not practically unit-testable); no automated
  test planned for the Canvas2D render loop itself.

## Open questions

- Exact SSE channel/endpoint to extend: reuse
  `GET /api/sessions/{session_id}/events` (per
  `session-sse-contract-v1.md`) with a new event type, or a dedicated
  endpoint? Needs a decision against that RFC's current status before
  implementation starts.
- Multi-session concurrency: if multiple sessions each spawn subagents
  simultaneously, does the panel scope to the currently-viewed session
  only, or offer a session picker?

## Rollout plan

Not scheduled. This RFC documents a design direction captured during
brainstorming, for future implementation pickup — no PR planned until
prioritized.
