# Office: 3D Floor View of the Hermes Delegation Tree

- **Status:** Accepted — implemented; office is the default delegation view,
  Agent Canvas kept as the accessible peer
- **Author:** hermes-webui local
- **Created:** 2026-09-08

## Problem

The Agent Canvas (`docs/rfcs/agent-canvas-visualization.md`,
`static/agent-canvas.js`) renders Hermes' live delegation tree as an org
chart. It is accurate and dense, but it reads as a diagram: a run with six
parallel subagents looks like six boxes, and the shape of the work — who is
busy, who is waiting, what a subagent is touching right now — has to be read
rather than seen.

[agents-office](https://github.com/ajsahni/agents-office) demonstrates the
alternative: an isometric 3D office where each agent is a person at a desk,
and work is legible at a glance from posture and activity. Its rendering
layer is worth reusing. Its runtime is not — it is a simulation with a thin
live path that shells out to Claude through its own Node server, backed by a
hardcoded 35-agent roster.

## Goals

- A new `office` panel: an isometric 3D floor whose workers are Hermes'
  **real** subagents, driven by the delegation events the app already
  receives.
- Two outlets over one engine:
  - **Projects** — desks allocated dynamically per spawned subagent. No
    departments. This is the honest view of what `delegate_task` actually
    does.
  - **Business** — a fixed six-department roster (Marketing, Emails, Sales,
    Operations, Finance, Delivery) whose named agents are Hermes personas the
    conductor delegates to as normal.
- Clicking a worker opens that subagent's existing Hermes detail/log view.
- Ship behind a new panel without changing existing behaviour. Agent Canvas
  keeps working throughout.

## Non-goals

- **No new orchestration.** Hermes remains the sole source of truth for
  parent tasks, subagents, status, tool calls, results, failures and
  handoffs. The office draws; it never decides, never spawns, never runs an
  agent registry or a broadcast loop.
- No second transport. The office consumes the same SSE relay and REST
  endpoints Agent Canvas already uses.
- No build step. This app has no bundler (`package.json`) and does not
  acquire one here.
- Not a replacement for Agent Canvas in this RFC. Retirement is a later
  decision, and is blocked on parity (history view, pause/interrupt, and the
  cron delegation diagram, which reuses `AgentCanvas.renderStaticTree`).

## Architecture

```
hermes-agent delegate_tool          (unchanged — sole orchestrator)
        |  subagent.start / .tool / .complete
        v
api/gateway_chat.py                 (unchanged relay)
        |  SSE subagent_spawn / subagent_tool / subagent_complete
        v
static/messages.js _wireSSE
        |
   HermesOfficeAdapter              (new; pure state, zero three.js)
   normalises events -> OfficeState { workers, desks, tasks }
        |                                   |
        v                                   v
   office scene (three.js)          static/agent-canvas.js (untouched)
```

The adapter is the only new logic. It holds `Map<subagent_id, worker>` and
emits scene commands (`allocateDesk`, `setPose`, `toolPulse`, `bubble`,
`complete`, `error`). The scene never fetches, never polls, never holds app
state. That split is what makes the interesting half testable headlessly, in
the same style as the existing `tests/test_agent_canvas_*.py` suite.

### Event mapping, and what does not exist

Four of the states we want map onto events that already reach the browser
(`api/gateway_chat.py:537-583`):

| Visual state | Source |
|---|---|
| allocate desk | `subagent_spawn` |
| working animation | `subagent_spawn` |
| tool activity indicator | `subagent_tool` |
| completed / error | `subagent_complete` (`status`) |

Three do not, and are deliberately **not** faked in v1:

- **queued** — there is no pre-spawn event. `subagent.start` is the first
  signal. A queued status is visible only by polling
  `GET /api/subagents/active`.
- **agent message bubble** — there is no per-message event. The closest real
  signal is `subagent_tool.preview`.
- **handoff** — there is no handoff event. A nested spawn
  (`parent_id !== root`) is nested delegation, which is a different thing.

Adding first-class events for these is a separate backend change, out of
scope here.

### Outlets

Both outlets consume the same adapter state. The only difference is desk
assignment policy — not a second engine.

**Projects.** Conductor at the centre. Desks are allocated as
`subagent_spawn` arrives; layout is a function of the live worker count
rather than a constant, which is what the upstream reference gets wrong for
our purposes (its `LAYOUT` and `AGENTS` are static module exports and the
scene is built once from them). Worker label is the subagent's `goal`.

**Business.** Six fixed department pods. Each named agent is a Hermes persona
(`/api/personalities`, `_agent_definitions.get_definition()`); the conductor
reaches them through ordinary `delegate_task`. Spawns are bound to a roster
slot by persona/goal match, with an overflow pod for anything unmatched.
This outlet depends on a department-scoped agent library with briefs, which
does not exist yet — see the Agent Library item in
`docs/HERMES_STUDIO_PARITY_PLAN.md`.

The outlet choice persists in `localStorage['hermes-webui-office-mode']`.

### Routing

This app is panel-based (`switchPanel()`, `MAIN_VIEW_PANELS` in
`static/panels.js`), not route-based, so the office is a panel — `office` —
peer to `agentCanvas`, rather than a literal `/office` URL.

### No bundler

The reference code is ESM with bare `import ... from 'three'`. Rather than
adding a build step, three.js r185 is vendored at
`static/vendor/three/0.185.1/` (matching the existing
`static/vendor/<lib>/<version>/` convention) and an import map in
`static/index.html` maps the bare `three` specifier to it. Office modules are
the app's only first-party ES modules; everything else stays IIFE-with-global
as before.

Two implementation notes that cost time when missed:

- The r185 module build is **split**: `three.module.min.js` re-exports from
  `three.core.min.js`. Both must be vendored or the module 404s at load and
  the panel is silently blank.
- The import map must precede every `<script type="module">` in the document.
  A map that lands after one is ignored for the module graph already
  resolving.

### WebGL lifecycle

WebGL inside a long-lived SPA panel leaks hard, so ownership is explicit:

- `createOfficeScene()` owns the renderer, its geometries and materials, and
  the rAF loop.
- Device pixel ratio is capped at 2.
- The loop stops on `visibilitychange`.
- **Leaving the panel disposes the context outright**, not merely pauses it.
  Browsers cap live WebGL contexts per page; a panel the user flips in and
  out of would exhaust that cap within a session, after which every later
  mount draws nothing.

## Phases

1. **Vendored three.js, import map, `office` panel rendering a lit floor.**
   Proves the no-bundler ES-module path and the WebGL lifecycle. *(done)*
2. **`HermesOfficeAdapter` plus headless tests. No 3D.** *(done)*
3. **Projects outlet: dynamic desks, the four real event states, click-through
   to the existing agent detail view.** *(done)*
4. **Parity: interrupt/pause controls, `GET /api/subagents/active`
   reconciliation, history via `GET /api/agent-canvas/sessions`.** *(done)*
5. **Business outlet.** *(done — see the caveat below; it does not wait for
   the Agent Library, it degrades honestly without one.)*
6. **Considered making the office the default and retiring Agent Canvas.**
   *(done — decided against; see below.)*

## Licensing

agents-office is PolyForm Noncommercial 1.0.0; this repository is MIT. Copied
code cannot ship under this repo's licence. This work therefore treats the
upstream project as a **visual and structural reference only** — the same
posture `Agent Canvas FounderOS Migration.md` took toward FounderOS — and
writes its own scene code. three.js itself is MIT and is vendored with its
licence (`static/vendor/three/0.185.1/LICENSE.md`).

## Phase 1 as built

| Path | Role |
|---|---|
| `static/vendor/three/0.185.1/` | three.js r185 (module + core + LICENSE) |
| `static/office/scene.js` | renderer, iso camera, lighting, ground, loop, dispose |
| `static/office/index.js` | `window.HermesOffice.mount/unmount`, observers |
| `static/index.html` | import map, rail + nav tabs, `#mainOffice`, `#panelOffice` |
| `static/panels.js` | `MAIN_VIEW_PANELS` entry, mount hook, unmount-on-leave |
| `static/style.css` | panel visibility rules, `.office-wrap` / `.office-canvas` |
| `eslint.runtime-guard.config.mjs` | ESM override for `static/office/**` |
| `tests/test_office_panel.py` | structure invariants for all of the above |

Phase 2 adds `static/office/adapter.js`, `static/office/package.json`, the
`window.HermesOffice` event intake, the `static/messages.js` fan-out, and
`tests/test_office_adapter.py`.

Verified in headless Chromium (SwiftShader): the module graph resolves,
a WebGL2 context comes up, the loop runs, and `unmount()` tears the canvas
and context down without throwing.

## Phase 2 as built

`static/office/adapter.js` is the whole brain, and knows nothing about how
anything looks: no DOM, no fetch, no three.js, no timers of its own. It takes
the three SSE events and the `/api/subagents/active` snapshot and maintains
one state object — a conductor, workers, desks — emitting small commands
(`worker.spawn`, `worker.tool`, `worker.status`, `worker.pose`,
`desk.reclaim`, `conductor`, `reset`) to subscribers.

That purity is load-bearing rather than tidiness: `static/office/package.json`
declares `"type": "module"` so node can import the file directly, and
`tests/test_office_adapter.py` therefore drives the **real** adapter through
scenarios (with an injected clock) instead of asserting on its source text —
a first for the front-end suite here, which is otherwise structural.

Rules the tests pin, each of which is a way the office could quietly lie
about what Hermes is doing:

- **A repeat spawn allocates no second desk.** The live stream and the
  reconcile snapshot both report the same subagent.
- **Terminal is sticky.** A late `subagent_tool` after completion must not
  resurrect a finished worker into a working pose, and an unrecognised
  completion status still ends the worker — a card stuck on "running"
  forever is a failure mode Agent Canvas already had.
- **Orphan events are counted, not invented.** A page attached mid-run sees
  tool and completion events for subagents that spawned before the stream
  existed; the office must not conjure a worker out of a tool call.
- **A snapshot never removes anyone.** Reconcile is catch-up, not truth about
  absence.
- **Desk pressure never evicts a live worker.** Finished workers keep their
  seats; at the cap the office reclaims the desk of the worker that finished
  longest ago, preferring one in the same parent cluster so siblings stay
  together. If nothing can be reclaimed, the office grows past its cap rather
  than reseating a running subagent.
- **State outlives the panel.** The adapter is module-level and `unmount()`
  does not touch it: subagents keep running while the user is on Chat, and
  their events keep arriving.

`static/messages.js` now fans the three events to `window.HermesOffice`
alongside Agent Canvas. Both views read the same Hermes truth; neither owns
it.

Verified in headless Chromium as well as under node: a spawn/tool/spawn/
complete sequence through the real page produces two seated workers, an
orchestrating conductor, and state that survives `unmount()`.

## Phase 3 as built

The floor plan is a function of the live delegation tree, so it lives in its
own pure module: `static/office/layout.js` takes the adapter's desks and
returns world positions — pods grouped by cluster (a subagent's parent), laid
out on concentric rings around the conductor. Like the adapter it runs under
node, and `tests/test_office_layout.py` pins the two properties that are not
obvious from reading it:

- **Pods never overlap**, at 2, 6, 7, 13 and 20 pods. Ring radius has to clear
  both the ring inside it and its own neighbours around the circle; taking
  only the first leaves the office a small island in a large empty floor,
  taking only the second lets adjacent rings collide.
- **A new subagent does not move the existing office.** Pods keep their ring
  slot for as long as their cluster exists, in first-seen order. An office
  that rearranges itself on every spawn is unreadable.

The camera frames `center` and `radius` rather than the origin: a part-filled
ring is lopsided — two pods out of six sit on one side of the conductor — and
framing on the origin leaves the office in a corner with dead floor opposite
it. Framing also accounts for isometric foreshortening (a horizontal distance
R covers only R·sin(elevation) of screen height), without which the office
sits as a small island in the middle of the panel whatever the zoom.

`static/office/builders.js` holds the procedural meshes — pod slab, desk with
a live canvas-texture monitor, chair, jointed figure, sprite nameplate — and
`poseWorker` drives a figure toward its pose each frame. Poses come straight
from adapter state: `work`, `tool`, `done`, `error`, `stopped`, `idle`. The
desk screen shows the current tool call; the nameplate carries the label and a
status glyph. Geometries and materials are shared through caches, since a busy
run puts a few dozen figures on the floor.

Clicking a worker raycasts to its seat group and opens a detail panel with the
same fields Agent Canvas shows, plus **Open conversation** — `delegate_task`
gives every child a real session, so that is the existing chat view rather
than an office-only log.

Verified in headless Chromium: five subagents across two clusters render as
pods, desks, figures and readable nameplates in both themes; a click sweep
resolves a worker and opens its detail panel; `unmount()` still releases the
context with office state intact.

## Phase 4 as built

The office now reaches parity with Agent Canvas on controls and history, over
exactly the REST surface Agent Canvas already uses — no second transport:

- **Reconcile.** `GET /api/subagents/active` every 5s while the panel is
  mounted, fed through `adapter.applySnapshot`. It is a catch-up for what the
  stream missed while the page was closed or reconnecting, never the primary
  source, and it is best-effort: a transient failure must not blow away the
  office already built from live events. The timer is cleared on unmount —
  one left running keeps hitting the API forever for a panel nobody is
  looking at.
- **Pause spawning / Interrupt.** `POST /api/subagents/pause` in the header,
  `POST /api/subagents/interrupt` on a selected worker. Interrupt is offered
  only on a live, non-terminal worker: a historical office is a record of
  something that already finished, and there is nothing there to stop.
- **History.** The panel sidebar lists the chats that ever delegated
  (`GET /api/agent-canvas/sessions`); clicking one replays it on the floor.

History is replayed through an **ordinary adapter** rather than by teaching
the adapter a frozen mode: `static/office/history.js` translates state.db rows
into the same `onSpawn` / `onComplete` payloads the live stream delivers, and
a second adapter instance consumes them. The live adapter keeps accumulating
underneath, untouched, so "Back to live" is a view switch rather than a
rebuild. That second instance is given a much larger desk cap — a finished run
can exceed the live one, and nothing should be reclaimed in a record of what
already happened.

One correction the translation makes: a child row with no `ended_at` reads as
`running` from the raw query, but in a *finished* session that can only mean
it was cut off, so it replays as `interrupted`. Showing it as running would
claim a subagent is live when nothing is. Agent Canvas makes the same
correction.

Verified in headless Chromium against stubbed endpoints: reconcile adopts a
subagent the stream never delivered, the pause button posts and relabels, the
sidebar lists two chats, clicking one replays three workers (including a
nested grandchild seated in its parent's cluster, and a never-ended row shown
as interrupted), and "Back to live" restores the live office intact.

## Phase 5 as built

Business and Projects are one engine, and the mechanism is smaller than the
RFC first assumed: `static/office/roster.js` returns a desk list in **exactly
the shape the adapter produces**, so `computeLayout` and the scene never learn
which outlet is showing. The outlet is a desk-assignment policy and nothing
else — no second orchestrator, no agent registry, no way to "run" an agent
from the floor. Hermes decides what to delegate and to whom; a department is
somewhere to sit the subagents it actually spawned.

- Six standing departments in fixed order — Marketing, Emails, Sales,
  Operations, Finance, Delivery — plus a visible overflow, **The Floor**.
- Every department always has at least one desk, so an idle office reads as a
  company rather than an empty room. A desk with nobody at it shows its roster
  name; the scene prefers `desk.seatLabel` when a seat is free.
- Workers are seated by matching their goal against department keywords,
  scored rather than first-match ("invoice reminder email" mentions both
  Finance and Emails; the department with more evidence wins). Running workers
  are seated before finished ones, so a busy department shows live work.
- Nothing unrecognised is forced into a department — it goes to The Floor,
  where it is visibly unfiled. And a full office grows rather than dropping a
  worker Hermes really is running.
- The choice persists in `localStorage['hermes-webui-office-mode']`, read
  through a try/catch because blocked site data throws on access rather than
  returning null.

### The Agent Library caveat

This phase was planned to wait for a department-scoped agent library. It does
not, because it can degrade honestly without one: `/api/personalities` carries
a persona's name and description and nothing else, so departments are inferred
from the persona's own words. That inference is the only part of the Business
outlet that is a guess, it is contained in one function
(`roster.js#departmentFor`), and anything it cannot place is shown on The
Floor rather than filed somewhere convenient. When a real agent library lands
with a department field, `buildRoster` reads it and the keyword pass is
deleted. See `docs/HERMES_STUDIO_PARITY_PLAN.md`.

Verified in headless Chromium: four subagents across three departments seat
correctly with the unmatched one on The Floor, empty roster desks show their
persona names, and the outlet choice survives a reload.

## Phase 6: the office does not replace Agent Canvas

Phase 6 asked whether the office should become the default view and Agent
Canvas retire. Having built the office, the answer is no, and not on grounds
of polish.

**Agent Canvas is the accessible view of this data, and the office cannot be.**
The office is a `<canvas>`. A screen reader gets nothing from it, and no
amount of ARIA changes that — the picture *is* the view. Retiring the DOM
rendering of the delegation tree would remove the only version of this
information some users can read. That alone settles it.

Two further reasons:

- **WebGL is not universal.** Blocked, unavailable or software-rendered
  contexts are real. The office already falls back to a message pointing at
  Agent Canvas; that fallback has to point at something that exists.
- **`renderStaticTree` has a second consumer.** The Scheduled-jobs page draws
  a cron run's delegation diagram with it (`static/panels.js`). Retiring the
  module means porting that too, for no user-visible gain.

So the two views stay peers, reading the same Hermes truth through the same
adapter-shaped path, and neither is the "real" one. What phase 6 did instead
was close the parity gaps that made the office the lesser view:

- Live duration for a running subagent, rather than nothing until it finishes.
- Recent tool activity (`output_tail`), files read and files written in the
  detail panel.
- **Interrupt branch**, deepest descendant first, so a parent is not left
  interrupting into children that already stopped.
- A sidebar filter over the delegating chats, matching Agent Canvas.
- An `sr-only` live region summarising the floor in words — how many
  subagents, how many running, and what each is touching. Not a replacement
  for the DOM view; a courtesy for anyone who lands on this panel.

### Default view

The office now leads: it sits above Agent Canvas in the rail and in the mobile
sidebar-nav, so it is the delegation view reached first. Agent Canvas is kept
directly beneath it for the reasons above — it is not hidden and not retired.

Promoting the office is deliberately **not** the same as booting into it. The
landing panel is still Chat; opening a chat app into a 3D floor instead of the
user's conversations would be a surprising default, and nothing about that is
implied by "make the office the default view of delegation".

One caveat worth knowing: this app has a persistent custom tab order
(`localStorage['hermes-webui-tab-order']`, applied by `_applyTabOrder()` on
every boot). A user who has already reordered their rail keeps their own
order, with the office appended — their preference wins over this default,
which is correct, but it means the promotion is invisible to them until they
reorder.

## Packing, after seeing it against a real config

Running the office in the real app with a real persona list exposed a defect
the synthetic checks could not: every uniform-pod test passed while the actual
floor was unreadable. Two fixes, both in `layout.js`:

- **Ring radius is set by the widest pod *on that ring*,** not across the whole
  office. One large department used to push every ring outward, marooning
  small pods in empty floor.
- **Large pods widen toward square** (3 columns minimum, 6 maximum) instead of
  staying three wide. Fifteen desks three across is a corridor five rows deep
  that shoves everything else off the floor.
- The camera centre is weighted by how much floor each pod occupies, so a
  fifteen-desk department does not sit half off-frame opposite a one-desk pod.

The tests that missed this used uniformly-sized pods throughout; there is now
a mixed-size non-overlap case, which is what a real roster produces.

## Status summary

| Phase | State |
|---|---|
| 1. Vendored three.js, import map, panel shell | done |
| 2. `HermesOfficeAdapter` | done |
| 3. Projects outlet | done |
| 4. Reconcile, pause/interrupt, history | done |
| 5. Business outlet | done (roster inferred from personas — see caveat) |
| 6. Default/retirement decision | office leads the rail; Agent Canvas kept as the accessible peer |

Everything Hermes owns it still owns. Across all six phases the office added
no orchestration: no spawn, no retry, no agent registry, no second transport.
It reads `subagent_spawn` / `subagent_tool` / `subagent_complete`, four REST
endpoints Agent Canvas already used, and draws what it is told.

## Reconcile in the single-container deployment

`GET /api/subagents/active` answers from `tools.delegate_tool`'s own in-process
registry when there is no separate gateway process, returning a fully
populated `active` list **alongside `gateway_enabled: false`**
(`api/routes.py`, added 2026-08-26). Agent Canvas' reconcile had skipped on
that flag since 2026-08-18 — eight days earlier — so reconciliation was a
permanent no-op for exactly the deployment that needs it most: with no gateway
process, a fire-and-forget subagent that finishes after its parent's stream
has closed has no other way to be noticed, and its card stayed "running"
forever. The office had inherited the same guard by copying it.

Both are fixed. `gateway_enabled` is now read for what it actually means —
whether the *gateway process* is there — rather than as "no data". The one
field it does gate is `spawn_paused`, and only against an error response: a
502 returns `spawn_paused: false`, which is an error, not a fact about
pausing.

Relatedly, `POST /api/subagents/pause` returns 409 without a gateway process,
so the office hides its Pause button in that deployment. A button that can
only ever error is worse than no button.

## Queued, revisited

Phase 4 recorded that `queued` has no backing event. Confirmed at the source
while wiring the default view: `delegate_tool_child_run.py` registers a child
with `status: "running"` and the registry drops the record on completion, so
the live snapshot only ever reports `running`. There is no queued state to
read anywhere — not in SSE, not in the snapshot. It stays unimplemented rather
than guessed.
