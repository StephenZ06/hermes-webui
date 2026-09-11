# Chat split view — pluggable right-panel panes

- **Status:** Proposed (all 4 slices implemented)
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

**As shipped (Slice 4) — corrected from the design below.**
`api/helpers.py` already sends an *enforced* Content-Security-Policy on every
response, with `frame-src` same-origin by default and an existing,
already-validated operator opt-in to widen it
(`HERMES_WEBUI_CSP_FRAME_EXTRA`). This pane needed no CSP change at all —
it's a UI onto whatever that policy already allows:

- `mount` restores the workspace's remembered URL (if any) and loads it;
  `unmount` blanks the iframe `src` (stop the page, free the socket).
- URL bar + sandboxed iframe, `sandbox="allow-scripts allow-forms
  allow-popups"` — **not** `allow-same-origin`, corrected from the design
  below. This repo already has a hard invariant against that exact
  combination (`tests/test_779_html_preview.py::test_sandbox_allows_scripts_
  only`, "would expose parent cookies"), which this pane's first draft
  violated and the full suite caught before it shipped: `allow-scripts` +
  `allow-same-origin` on a URL that happens to be same-origin with the WebUI
  itself (nothing stops a user typing the app's own URL into the box) lets
  the framed page read/write the parent's cookies. The CSP `frame-src`
  allowlist controls *which origins* can be embedded at all; this sandbox
  attribute is a separate, independent layer underneath it, not something
  the allowlist substitutes for.
  Reload and "open in new tab" buttons. Enter in the URL field loads it.
- URL remembered per `session.workspace` in `localStorage`
  (`hermes-webui-livepreview:<workspace>`, no hash needed — a raw path is a
  fine key).
- A bare `host:port` (the common case people actually type) gets an assumed
  `http://` prefix. **Bug caught by the test for this**: a naive
  "does `new URL(x)` throw" check is not a valid http(s) test —
  `new URL("localhost:5173")` **succeeds**, parsing `localhost` as the
  *scheme* (any `scheme:opaque-path` is a valid URL, the same shape as
  `mailto:x`), so the very case this exists to handle silently produced an
  empty URL. Fixed by checking `protocol === 'http:' || 'https:'` on both the
  as-typed attempt and the `http://`-prefixed retry, not "did it throw".
- CSP silently drops a blocked iframe navigation — no `onerror` fires for it
  in any browser. Listens for the `securitypolicyviolation` DOM event
  (`effectiveDirective`/`violatedDirective` including `"frame-src"`) and shows
  an explanation naming `HERMES_WEBUI_CSP_FRAME_EXTRA`, instead of a
  permanently blank iframe with no indication of why.
- No settings gate: unconditionally available, same as Canvas and Tasks. A
  dedicated `chat_live_preview_enabled` toggle would be redundant with the
  CSP allowlist, which is the setting that actually determines whether the
  pane can do anything.
- **Deferred, not shipped**: auto-filling the URL bar from a
  `http://localhost:<port>`-shaped string the agent's tool output prints
  (mirroring `agent-canvas`'s URL mining). Real value, but a genuinely new,
  more speculative feature (scanning tool output for URLs) rather than UI on
  an existing capability like the rest of this slice — left for a follow-up
  if wanted.

Tests: `tests/test_chat_pane_registry.py` (URL loads and persists; a bare
host gets `http://`; a non-http URL and an empty URL are both rejected
safely; mount restores the saved URL; a `securitypolicyviolation` for
`frame-src` shows the blocked message and one for an unrelated directive is
ignored; reload forces a fresh navigation; unmount blanks the frame).

### Pane: Plane tasks

**As shipped (Slice 3) — corrected from the design below.** There is no
"chat's bound project → board" link anywhere in the codebase; Kanban boards
are a per-browser/global preference, independent of WebUI Projects. The pane
shows the same board the full Kanban panel shows:

- `mount` calls the existing `loadKanban()` (resolves/refreshes the active
  board, starts the shared poll/SSE connection if not already running).
  `_kanbanRenderBoard()`'s existing additive-branch pattern (already used to
  keep its "Office view" in sync with every caller) renders the pane via
  `_kanbanRenderSidebar()`, extended with an optional container id + click
  handler — no second fetch, poll, or SSE connection.
- `unmount` stops the shared connection unless the full Kanban panel is also
  showing (mirrors `switchPanel()`'s own guard for the same connection).
- Clicking a task switches to the full Kanban panel first, then opens it
  there (`#kanbanTaskPreview` lives inside that panel's own DOM) — no editing
  in the pane.
- Always available (no `isAvailable` gate) — same as the full Kanban panel's
  own availability today.

<details><summary>Original pre-implementation design (kept for history)</summary>

- `mount` renders a compact read-only board: reuse `renderKanbanBoard`'s row
  builder against `/api/kanban/config` + `/api/kanban/tasks` for the board
  resolved from the chat's bound project
  (`S.session.bound_project_key` → board slug; fall back to the default board).
- Poll on the existing kanban SSE while mounted; `unmount` closes it
  (`_kanbanStopPolling`).
- Clicking a task opens the full Kanban panel focused on it (`switchPanel
  ('kanban')` + task id) — no editing in the pane for v1.
- `isAvailable` → `!settings.hide_kanban_panel` and a board resolves.

</details>

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
3. **Slice 3 — Plane (Kanban tasks) pane. Implemented (2026-09-12), scope
   corrected.** The tab shows "Tasks" (`data-i18n="tab_tasks"`, an existing,
   already-15-locale key — no new translation needed) and its internal pane
   id stays `plane` for continuity with this RFC's naming; "Plane" was always
   this app's own built-in Kanban board (`api/kanban_bridge.py`), never an
   integration with the separate `plane.so` product.

   **Deviation found mid-implementation:** there is no "bound project → board"
   link anywhere in the codebase. Kanban boards are a per-browser/global
   preference (`localStorage` hint → server's `current` → `default`, see
   `loadKanbanBoards()`), entirely independent of the WebUI Projects concept
   this RFC assumed when it was written. Building that link would be a new
   data-model feature (a `board` field on Projects, or the reverse), not a
   "read-only pane" — out of scope for this slice. Shipped instead: the pane
   shows the SAME board the full Kanban panel shows.

   No new fetch, poll, or SSE connection: the pane reuses `loadKanban()`'s
   existing machinery and `_kanbanRenderSidebar()`'s row renderer (extended
   with an optional `containerId` + `opts.openTask`, default args unchanged
   for the Kanban panel's own sidebar) via an additive branch in
   `_kanbanRenderBoard()` — the same pattern that function already uses to
   keep its "Office view" (a *different* existing feature, Kanban-dispatched
   workers) in sync with every one of its callers. Opening a task switches to
   the full Kanban panel first, since the task detail view renders into
   `#kanbanTaskPreview`, which lives inside that panel's own DOM.

   Unmount stops the shared poll/SSE connection unless the full Kanban panel
   is *also* showing (mirrors `switchPanel()`'s own guard for the same
   connection) — the pane and the full panel are independent consumers of one
   shared board/connection, not two separate ones.

   Tests: `tests/test_chat_pane_registry.py` (mount loads the board; the pane
   renders through the shared sidebar renderer with the pane's own container
   id and click handler; it does not render while hidden; opening a task
   switches panels first; unmount's stop-polling guard both ways) plus the
   full existing Kanban suite, unchanged.
4. **Slice 4 — Live preview pane. Implemented (2026-09-12), scope corrected**
   — see "Pane: Live preview" above. No CSP change needed (the enforced
   policy + `HERMES_WEBUI_CSP_FRAME_EXTRA` already existed); no settings
   gate (redundant with that policy); URL-normalization bug caught by its
   own test before shipping; localhost-URL chip mining deferred as a
   separate, more speculative feature.

Each slice is its own PR with before/after screenshots at desktop + narrow +
mobile widths.

## Open questions

- Should the pane strip live where the Files/Artifacts/Todos strip is now
  (inside `.rightpanel`, workspace-scoped visually), or move up to a neutral
  bar so "Canvas" doesn't read as a workspace sub-view? Leaning: keep it in
  place, rename the strip's aria-label from "Workspace panel views" to
  "Chat side panel".
- ~~Live preview across origins needs `frame-src *`...~~ Resolved: this
  allowlist already existed (`HERMES_WEBUI_CSP_FRAME_EXTRA`,
  `api/helpers.py`) before this RFC was written; no new settings surface
  needed.
- Does Canvas-in-pane replace the "View live" affordance that currently jumps
  to the Office, or complement it? Complement: the pane is the glance, the
  Office is the room.
- Still open: whether the tab strip should keep rendering from six hardcoded
  buttons or start rendering from the registry (`listChatPanes()` +
  `isAvailable`) — no pane has needed dynamic availability yet, but a future
  one (e.g. Plane truly scoped to a bound project) likely will.
