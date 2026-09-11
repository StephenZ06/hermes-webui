# Chat split view — pluggable right-panel panes

- **Status:** Proposed (Slices 1-2 implemented)
- **Author:** @StephenZ06
- **Created:** 2026-09-11

## Problem

The chat view already has a right-hand `.rightpanel` (`static/index.html`
`<aside class="rightpanel">`) with a small tab strip — Files / Artifacts /
Todos, switched by `switchWorkspacePanelTab()` (`static/workspace.js:372`). It
is resizable (`#rightpanelResize`), width-persisted, and collapses on mobile.

Three things people want next to a chat are not reachable from there:

1. **Canvas** — the subagent delegation tree. It used to be a full nav panel
   (`static/agent-canvas.js`, `AgentCanvas`), was replaced by the Office
   (`4af629c49 feat: remove the Agent Canvas panel in favour of the Office`),
   and now has no in-chat surface at all. The Office is a whole-screen view;
   there is no "watch the fan-out while I keep typing".
2. **Live preview** — a URL in an iframe (a dev server, a deployed preview,
   a running app). The panel can already preview a *file* as HTML
   (`#previewHtmlWrap` / `#previewHtmlIframe`), but not an arbitrary origin
   the agent just started serving.
3. **Plane tasks** — the Kanban board (`api/kanban_bridge.py`, `/api/kanban/*`,
   panel `#kanbanBoard`). Scoped to a board today; not visible beside the chat
   that is working the tasks.

"Connect them" — each pane should follow the active session: Canvas streams the
current chat's subagents, Plane filters to the chat's bound project/board, Live
preview remembers a URL per session/workspace.

## Goals

- One extensible pane registry for the chat right-panel. Adding a pane is a
  registry entry + a mount/unmount/relayout triple, not edits scattered
  through `switchWorkspacePanelTab`, the resize code, and the mobile code.
- Ship three panes on top of it: **Canvas**, **Live preview**, **Plane tasks**.
- Each pane is session-aware and tears down cleanly on session switch, panel
  collapse, and mobile drawer close (AGENTS.md guideline #7 — name the owner of
  every piece of state and prove release on every exit).
- No regression to Files / Artifacts / Todos, the preview interplay, resize,
  width persistence, or the mobile layout.

## Non-goals

- A free-form multi-pane / drag-to-split layout. One pane visible at a time,
  chosen from the tab strip, same as today.
- A second copy of the Office 3D scene. Canvas here is the 2-D tree
  (`agent-canvas.js`), which is cheap; the Office stays the dedicated view.
- Editing Plane tasks from the pane in v1 — read + open-in-panel only.
- Persisting a live-preview iframe across a full reload (it re-navigates from
  the remembered URL).

## Proposal

### Pane registry

`static/panes.js` (new), loaded before `workspace.js`:

```js
// registerChatPane({ id, label, i18nKey, order, isAvailable, mount, unmount,
//                     relayout, onSession })
```

- `id` — dataset value, persistence key (`hermes-webui-rightpanel-pane`).
- `isAvailable(ctx)` — hide the tab when the pane can't apply (no session, no
  bound project, feature disabled). `ctx = { session, project, workspace }`.
- `mount(host, ctx)` — build into a pane-owned container; returns nothing.
- `unmount()` — release SSE, timers, iframes, WebGL. Called on tab-away,
  collapse, session switch, teardown.
- `relayout()` — width/height changed (resize handle, mobile↔desktop).
- `onSession(ctx)` — active session changed while mounted.

`switchWorkspacePanelTab()` becomes `switchRightPanelPane(id)`: the built-in
`files` / `artifacts` / `todos` are registered through the same registry (their
current show/hide of `#fileTree`, `#workspaceArtifacts`, `#workspaceTodosPanel`
moves into their `mount`/`unmount`). The tab strip is rendered from the
registry, filtered by `isAvailable`.

### Pane: Canvas

- `mount` calls `AgentCanvas.mount(host)` (already exists) and subscribes the
  same adapter feed the Office uses (`static/office/adapter.js` /
  `messages.js` `_wireSSE` → `onSpawn` / `onToolActivity` / `onComplete`).
- `onSession` → `AgentCanvas.reset()` then replay from
  `/api/agent-canvas/sessions` for the new sid (same as the Office's
  `applyHistory`).
- `unmount` → `AgentCanvas.unmount()` + drop the subscription.
- `isAvailable` → always (empty state: "No subagents yet").

### Pane: Live preview

- `mount` renders a URL bar + a sandboxed iframe
  (`sandbox="allow-scripts allow-forms allow-popups allow-same-origin"` —
  same-origin only if the URL is the WebUI's own origin; otherwise drop it).
- URL remembered per `workspace` in `localStorage`
  (`hermes-webui-livepreview:<workspace-hash>`).
- Auto-fill: if the agent runs a tool that prints `http://localhost:<port>` or
  `http://127.0.0.1:<port>` (mirror `agent-canvas`'s URL mining), offer it as a
  one-click chip. Do **not** auto-navigate.
- A reload button and an "open in browser tab" button.
- `unmount` → blank the iframe `src` (stop the page, free the socket).
- CSP: the iframe loads third-party origins, which the app CSP must allow in
  `frame-src`. Gate the whole pane behind a setting
  (`chat_live_preview_enabled`, default off) so self-hosters opt in.

### Pane: Plane tasks

- `mount` renders a compact read-only board: reuse `renderKanbanBoard`'s row
  builder against `/api/kanban/config` + `/api/kanban/tasks` for the board
  resolved from the chat's bound project
  (`S.session.bound_project_key` → board slug; fall back to the default board).
- Poll on the existing kanban SSE while mounted; `unmount` closes it
  (`_kanbanStopPolling`).
- Clicking a task opens the full Kanban panel focused on it (`switchPanel
  ('kanban')` + task id) — no editing in the pane for v1.
- `isAvailable` → `!settings.hide_kanban_panel` and a board resolves.

### State ownership / exits

| State | Owner | Released on |
|---|---|---|
| Canvas adapter subscription | Canvas pane | unmount (tab-away, collapse, teardown) |
| Canvas DOM | `AgentCanvas` | `AgentCanvas.unmount()` |
| Live-preview iframe socket | Live-preview pane | unmount → `src=''` |
| Plane SSE | Plane pane | unmount → `_kanbanStopPolling()` |
| Active pane id | `localStorage` | n/a (survives reload; re-validated by `isAvailable`) |

Session switch (`loadSession`): call the active pane's `onSession`. Panel
collapse (`toggleWorkspacePanel(false)`) and mobile drawer close: call
`unmount`; `mount` again on re-open. This mirrors what `switchPanel` already
does for the Office (`panels.js:455` `HermesOffice.unmount()`).

## Rollout plan

1. **Slice 1 — registry, no behaviour change. Implemented (2026-09-12).**
   Extracted Files / Artifacts / Todos into `registerChatPane` entries;
   `switchWorkspacePanelTab()` is now a one-line delegate to the new
   `switchRightPanelPane()`. Tests: `tests/test_chat_pane_registry.py`
   (built-ins register on load, mount/unmount fire correctly, unknown id
   falls back to `files`) plus the full existing workspace-panel suite,
   unchanged.

   **Deviation from the original text above:** the registry lives in
   `static/workspace.js` itself, not a new `static/panes.js`. A large number
   of existing tests build an isolated page by injecting only `workspace.js`'s
   source (`page.add_script_tag(content=WORKSPACE_JS)`, ~30 files) — a second
   file would need its own script tag added to every one of them, and any
   harness that was missed fails with a bare `ReferenceError` (found by
   `test_issue6867_artifacts_settled_recovery.py` red on the first attempt).
   The tab strip itself still renders from the three hardcoded buttons, not
   the registry — that part of Slice 1 is deferred to whichever later slice
   first needs a pane not named files/artifacts/todos in the strip.
2. **Slice 2 — Canvas pane. Implemented (2026-09-12).** A non-interactive
   delegation tree, `AgentCanvas.renderStaticTree()` fed from
   `window.HermesOffice.adapter`/`.getState()` — the SAME live feed the Office
   3D view reads — not from `AgentCanvas`'s own `onSpawn`/`onToolActivity`/
   `onComplete` handlers, which agent-canvas.js's own file header says were
   retired when the Office replaced it as a panel (`static/messages.js` no
   longer calls them). Reviving that path would have meant re-wiring the SSE
   fan-out; reading the Office's adapter instead needs nothing extra, since it
   already receives every event live.

   **Deviation found mid-implementation:** `buildTreeNodes()`'s status mapping
   unconditionally coerced `running` → `interrupted`, correct for its only
   prior caller (a *finished* cron run row that never recorded a completion
   event) but wrong for a subagent that is genuinely still running right now.
   Added a `live` option (default `false`, so the cron delegation card's exact
   existing behavior is unchanged) that the Canvas pane passes `true` — the
   same distinction `office/history.js`'s `historicalStatus()` already makes
   for the Office's own historical replay.

   Nesting: a worker becomes a direct child of the root unless its `parentId`
   names another currently-live worker, in which case it nests under that
   worker instead — mirrors `office/history.js`'s `isDirect` check for the 3D
   floor's replay.

   Added `workspace_canvas_tab` to all 15 locale blocks (a short, standard
   translation of "canvas" per locale — flag for a native-speaker pass rather
   than treat as final).

   Tests: `tests/test_chat_pane_registry.py` (tree renders from the adapter
   state with `live: true`; nested delegation keeps its real parent; mount
   subscribes, leaving unsubscribes; a live adapter event re-renders while
   mounted) plus `tests/test_cron_delegation_diagram.py` (unchanged cron
   behavior with the new `live`-less default).
3. **Slice 3 — Plane pane.** Read-only board, bound-project resolution, SSE
   teardown. Tests: board resolves from bound project; unmount closes the SSE.
4. **Slice 4 — Live preview pane.** Setting-gated, CSP `frame-src` change,
   URL persistence, localhost-URL chip mining. Tests: URL persists per
   workspace; unmount blanks `src`; pane hidden when the setting is off.

Each slice is its own PR with before/after screenshots at desktop + narrow +
mobile widths.

## Open questions

- Should the pane strip live where the Files/Artifacts/Todos strip is now
  (inside `.rightpanel`, workspace-scoped visually), or move up to a neutral
  bar so "Canvas" doesn't read as a workspace sub-view? Leaning: keep it in
  place, rename the strip's aria-label from "Workspace panel views" to
  "Chat side panel".
- Live preview across origins needs `frame-src *` (or a user allowlist) in the
  CSP. Allowlist is safer but is another settings surface. Default-off + a
  single `frame-src` relaxation behind the flag is the v1 compromise.
- Does Canvas-in-pane replace the "View live" affordance that currently jumps
  to the Office, or complement it? Complement: the pane is the glance, the
  Office is the room.
