# Office: 3D Floor View of the Hermes Delegation Tree

- **Status:** Accepted — implemented; the office is the delegation view and
  the Agent Canvas panel has been removed
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
- **Desk pressure never evicts a live worker.** At the cap the office reclaims
  the desk of the worker that finished longest ago, preferring one in the same
  parent cluster so siblings stay together. If nothing can be reclaimed, the
  office grows past its cap rather than reseating a running subagent.
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

### Correction: reconcile cannot complete anything by itself

An earlier revision of this document claimed the guard fix was what let a
fire-and-forget subagent finally report completion. That was wrong, and a
live run proved it — the card still sat at "running".

`delegate_tool`'s `_unregister_subagent` **removes** a child from the live
registry the moment it finishes (`tools/delegate_tool_child_run.py`). A
finished subagent therefore never appears in `/api/subagents/active` with a
terminal status; it simply disappears. An adapter that only adds and updates
workers from that list — which is what both this office and Agent Canvas did —
can never learn that anything completed.

What the guard fix actually repaired is real but narrower: the snapshot's data
was being discarded wholesale, so running subagents were not being *adopted*.
Completion was never covered.

**Absence is the completion signal.** The registry holds exactly the live
children, so a worker previously observed running and now gone from a healthy
snapshot has stopped. The office acts on that, narrowly:

- only for workers it has actually seen in a healthy snapshot (a worker known
  only from SSE may sit outside whatever the snapshot covers, and its absence
  says nothing);
- only when the snapshot itself carries no error (a 502 returns an empty
  `active`, and treating that as "everyone finished" would wipe the office on
  one bad poll);
- only after two consecutive misses, so a single racing snapshot cannot retire
  a live worker.

The resulting status is **`ended`**, not `completed`, and its nameplate glyph
is `◦` rather than `✓`. We know the subagent stopped; we never saw how it
went. A tick would claim a clean result nobody reported.

A real `subagent_complete` still wins — retirement is only the fallback for
when that event never arrives. Note the latency: polling runs at 5s and only
while the panel is mounted, so retirement lands roughly 10s after the child
actually finishes, or ~10s after the user next opens the panel.

Agent Canvas has the same structural gap and is left as it is; this RFC does
not change it.

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

## Finished workers leave

The first cut had finished workers keep their desks indefinitely, on the
reasoning that a completed subagent is part of the record of the run. Real use
disproved it inside a day: delegate twice and the second run stacks on top of
the first, and the floor only ever grows.

**A new run starts on a clean floor.** When a spawn arrives and *nothing* is
still running, the previous run's leftovers go first. The "nothing still
running" condition is what keeps this safe — a spawn arriving mid-run is a
sibling in the same batch or a nested child, and clearing then would erase
live work.

A 25s linger was tried alongside this and removed again. It deleted the desks,
the goals on their nameplates and the completion summaries while the user was
still reading them — the office emptied itself out for no reason a viewer
could see. Clearing on the next run already solves the stacking the linger was
reaching for, and it does it at the only moment the old run genuinely stops
being what you are looking at. `completedLingerMs` survives as an option and
defaults to 0.

When a linger *is* configured, the sweep runs from `tick()`, which the scene
already calls each frame, so the adapter still owns no timer of its own.

One consequence worth noting: desk reclaim under cap pressure now only comes
up while something is still running, since an all-finished office is cleared
outright instead. The reclaim tests were rewritten to hold a live worker open
rather than deleted, because that is the case reclaim still serves.

## Phase 6 revisited: the Agent Canvas panel was removed after all

Phase 6 argued for keeping Agent Canvas as a peer, chiefly on accessibility:
the office is a `<canvas>` and Agent Canvas was the DOM rendering of the same
tree. The panel has since been removed at the user's direction, the office
having covered its job.

What that reasoning got right is worth keeping in view: **a screen reader now
gets the office's `sr-only` summary and nothing else.** That summary is no
longer a courtesy — it is the only non-visual account of a delegation, which
is a real reduction from a full DOM tree. Anyone changing it should treat it
as load-bearing.

The other two objections were dependencies rather than opinions, and were
handled rather than overruled:

- **`renderStaticTree` has a second consumer.** The Scheduled-jobs page draws
  each cron run's delegation diagram with it, over the `.agent-canvas-*`
  styles. `static/agent-canvas.js` therefore stays loaded, headless: no rail
  tab, no panel-view, no main-view, and `static/messages.js` no longer fans
  live events at it. Its live code is now unreachable and is documented as
  such at the top of the file, left in place because `renderStaticTree()`
  shares this file's card and tree builders and unpicking that is a refactor
  with no user-visible gain.
- **The no-WebGL fallback pointed at Agent Canvas.** It now says what is wrong
  and what would fix it, instead of directing people to a panel that no longer
  exists.

Two tests followed their subject rather than being deleted with the panel: the
blank-sidebar guard now checks *every* main-view panel has a matching
`#panel<Name>` (the rule outlived the panel that first broke it), and the SSE
listener test now asserts the office receives the events, since "the backend
relay must have a frontend consumer" is unchanged. The empty-state test was
dropped outright — its subject was the panel's own placeholder.

## Business floor visual parity (2026-09-12)

Three more things brought over from the agents-office reference — visual
reference only, per the Licensing section above; all hand-written:

- **Department floor colour.** Each of the six standing departments
  (`static/office/roster.js`'s `DEPARTMENTS`) now carries a `color`, threaded
  through `businessView()` → `computeLayout()`'s `pod.color` → `makePod()`,
  which blends it into the palette's own pod colours (`THREE.Color.lerp`)
  rather than painting a flat brand colour over whichever theme is active.
  "The Floor" overflow deliberately stays uncoloured (an unrecognised worker
  is not a department). Projects pods have no department to hang a human
  colour on, but as of the same-day follow-up below they are not left bare
  either — `computeLayout()` distinguishes "no colour, on purpose" (an
  explicit `clusterColor: null`) from "no signal at all" (a Projects desk,
  which never carries the key) and derives a stable colour for the latter
  from `colorForProjectsCluster()`, a plain string hash into a fixed palette
  — same cluster id always renders the same colour, with no state to persist.
- **Per-pod floating stat card.** One card per pod (seat count, live
  active/done counts derived from the same adapter state the floor is drawn
  from), positioned every frame by a new `podScreenRect(cluster)` query on
  the scene (world-to-screen projection, CSS pixels relative to the canvas)
  so it tracks the pod as the camera pans/zooms. No metric this app cannot
  actually measure — unlike the reference's "cost per user" style numbers,
  which have no equivalent here. Generalised to Projects the same day
  (`officeCardSpecs()`): a Projects pod is just "whoever's parent spawned
  this cluster", not a named thing, so its card carries no name — but it
  does carry a colour, the same derived one as its floor, so the card still
  reads as belonging to that pod rather than a colourless placeholder.
- **Aggregate Task Status panel.** A new right-hand column inside the office
  view (`.office-body` now splits `.office-stage` and `.office-tasks`),
  listing every worker the adapter is tracking with a live All/Running/Done/
  Stopped filter, independent of which outlet is showing — it reads the raw
  adapter state, not `businessView()`'s desk transform, since a subagent is
  the same real subagent whichever floor plan draws it. Clicking a row calls
  the existing `focusOnWorker()`, the same as clicking a desk.

All three are real screen-projected/DOM state, not screenshots — verified
against the actual running scene in `tests/test_office_browser_smoke.py`
(`HERMES_WEBUI_BROWSER_TESTS=1`, both outlets), plus node-level tests for the
pure pieces (`test_office_roster.py`, `test_office_layout.py`,
`test_office_pod_color.py`, `test_office_task_status.py`,
`test_office_pod_stat_cards.py`).

### Follow-up same day: Projects floor colour

Asked directly: "why are there no colours [on the Projects floor]?" The
department-colour work above deliberately left Projects pods bare, on the
reasoning that colour is a human choice and a Projects cluster (a subagent's
own id) has nobody to make that choice. On reflection that reasoning does
not hold up the same way the "no name" call does — colour, unlike a name, has
a mechanical fallback: derive one, deterministically, from the cluster id
itself, so a pod stays the same colour every time it is drawn without
inventing an identity for it.

- `layout.js` gained `colorForProjectsCluster(cluster)` (a small string hash
  mod a fixed 8-colour palette) and `computeLayout()` now calls it for any
  desk cluster that never carries a `clusterColor` key at all — as opposed to
  a Business desk, which always carries the key explicitly (a real colour, or
  `null` for the "The Floor" overflow). `hasOwnProperty` is the actual
  decision point, not the value's truthiness, precisely so the overflow's
  deliberate `null` is never mistaken for "no signal" and coloured anyway.
- `roster.js`'s `businessView()` was tightened so both of its overflow-desk
  code paths set `clusterColor: null` explicitly (one already did; the
  "every seat taken, add another desk" fallback did not and needed it).
- `officeCardSpecs()`'s Projects branch now passes the same derived colour
  through to the floating stat card, so the card matches its floor.
- The palette intentionally overlaps Business's six department colours (the
  two outlets are never on screen at once) plus two new hues, so a Projects
  floor doesn't come out visually thinner than Business's.

### Follow-up same day: colour pop, then six more visual features

Reported: the pod colours above still read too washed-out next to the
reference screenshot. Two causes, both tuning rather than behaviour: `makePod`
blended a department/cluster's tint into the palette at 0.3/0.34 (barely a
wash); bumped to 0.62/0.68. And `roster.js`'s six department colours and
`layout.js`'s `PROJECTS_POD_PALETTE` were themselves fairly desaturated dusty
tones; replaced with more saturated hues, same roles, no exact value pinned by
any test (`test_office_pod_color.py` only asserts relational properties).

Asked next for further ideas, then to build all of them (explicitly
including bloom: "I have a good enough computer to run no.6 (MinisForum
UM790)" — bloom cost is paid by whoever's *browser* renders the page, not the
machine running hermes-webui itself, but the office is normally opened by the
person running it, so this held). Six additions, all original code against
observed behaviour/screenshots only (see Licensing above):

1. **A working pod's own glow** (`builders.js`'s `makePodGlow`). A soft
   additive-blended plane over a pod's floor, invisible (`opacity: 0`) until
   the pod is actually doing work, then pulses gently
   (`scene.js`'s `pulseGlow`, eased rather than snapped — same reasoning as
   the marching outline's own dash fade). Its own per-instance material,
   never the shared `material()` cache: two different clusters can share a
   colour (`colorForProjectsCluster`'s hash can collide), and every pod's
   activity is independent. The conductor gets one too, driven by
   `orchestrating` status rather than `liveClustersWithWork`.
2. **Small props**: a whiteboard (`makeWhiteboard`) alongside the two
   existing plants — pure scenery, no state, one per pod.
3. **A faint floor grid** (`makeFloorTiles`), drawn to each pod's own exact
   footprint (not a shared repeating texture) so the line spacing reads as a
   consistent physical size regardless of a pod's dimensions.
4. **A department's own glyph** (`roster.js`'s new `icon` field on
   `DEPARTMENTS`, `iconForDepartment()`, threaded through `businessView()` →
   `computeLayout()`'s `pod.icon` → `makeDeptIcon()`). First attempt painted
   it into the same canvas as the floor-sign text, in its own band above the
   name — worked as a 2D drawing (verified in isolation) but the extra height
   pushed the sign backward into the pod, hiding the icon behind/under the
   desk. Fixed by making it a separate camera-facing `THREE.Sprite`,
   floating well above the pod (y 8.5, scaled down) instead of lying flat on
   the floor — sidesteps the occlusion problem entirely and reads at any
   zoom, the same reasoning `makeNameplate` already uses for worker labels.
   Business only; a Projects pod has no department to draw a mark for.
5. **Lighting**: the flat `AmbientLight` became a `HemisphereLight` (a
   sky-toned colour from above, a ground-toned one from below, per palette),
   plus a low rim `DirectionalLight` opposite the key light so a pod's far
   side isn't flat black. Both repainted on `applyTheme()`.
6. **Bloom**: `EffectComposer` + `RenderPass` + `UnrealBloomPass` +
   `OutputPass`, vendored from the upstream three.js r185 examples (same MIT
   licence as the core build already vendored; unminified, since three ships
   no minified addon build) at `static/vendor/three/0.185.1/addons/`, resolved
   via a new `"three/addons/"` import-map prefix entry (one entry maps the
   whole tree, not one per file). Threshold set to 1.0: everything in the
   ordinary palette sits under normal 0-1 colour range, so nothing here needs
   the usual "selective bloom" layer trick — only the glow mesh above, whose
   colour is deliberately pushed past 1.0
   (`THREE.Color.multiplyScalar(2.4)`), actually blooms. `renderer.toneMapping
   = ACESFilmicToneMapping` so that over-bright colour rolls off softly
   instead of clipping to flat white. The panel's canvas stays transparent
   through the whole pipeline (`renderer.setClearAlpha(0)`, unset on
   `RenderPass` so it inherits that) — checked directly by reading back the
   canvas's own pixels at a background corner during manual verification,
   not just inferred from the API.

Composer passes own further GPU resources beyond what
`EffectComposer.dispose()` itself frees (bloom's blur render targets, the
output pass's material) — `dispose()` now calls `pass.dispose()` on each pass
individually first, or a panel revisited enough times would leak them the same
way an undisposed renderer would.

Verified: the pure logic (`iconForDepartment`, the pod colour/icon threading)
under real node (`test_office_roster.py`, `test_office_layout.py`); the new
builders under real three.js-under-node
(`test_office_visual_extras.py`, same vendored-build stub as
`test_office_pod_color.py`, plus a minimal no-op canvas-2D stub since these
draw to a canvas and node has none); scene.js's wiring pinned at the source
level (`test_office_visual_polish.py` — composer ordering/resize/dispose,
hemisphere/rim lights, icon threading, glow-eases-not-snaps, one whiteboard
per pod); the addon vendoring itself (`test_office_panel.py` — every
`three/addons/...` import in scene.js is checked against a file that actually
exists on disk, the same failure class as the existing three.core.min.js
split check); and the real running app end to end
(`test_office_browser_smoke.py`, `HERMES_WEBUI_BROWSER_TESTS=1`), plus manual
screenshots taken through Playwright during development to confirm the icon
placement fix, the floor tiles, the whiteboard, and canvas transparency
(RGBA read back as `[0,0,0,0]` at a background corner) all actually look
right — this repo has no pixel-diffing harness, so a rendering-only feature
like this gets a real look, not just an assertion that code ran.

### Follow-up same day: smoothness, an outline artifact, and reworking the icon

Four reports against the pass above, all fixed the same day:

1. **"Not as smooth"** since bloom landed. Three concrete costs, all cut:
   - `EffectComposer.setPixelRatio(1)`, independent of the renderer's own
     (uncapped, up to 2x) ratio. Bloom is a soft, blurred effect; its
     five-level mip blur chain gained no visible sharpness from rendering at
     full device pixel ratio and was the single biggest new per-frame cost.
   - The per-pod floor-tile grid (a canvas-texture plane per pod) is gone
     entirely — see point 3 below; one less draw call and texture per pod.
   - `makeWhiteboard`'s four parts (board, frame, two legs) now set
     `castShadow = false`. A decorative prop this small wasn't worth the
     shadow pass rendering four more objects from the light's point of view,
     on every pod, every frame.
   - The floating per-pod DOM stat cards (`officeCardSpecs`/
     `renderDepartmentCards`/`repositionDepartmentCards`, `index.js`) are
     removed entirely (see point 4) — their per-frame `podScreenRect`
     projection and DOM writes for every visible pod are gone too.
2. **The dashed pod outline visibly "stuck out" past the floor's corners.**
   `makeSlabOutline`'s default height was 0.66 (originally chosen to match
   the floor sign, for no real reason tied to the outline itself) against a
   slab top at 0.6. The isometric camera looks down at an angle, so a line
   held higher above the slab at the same x/z projects to a screen position
   shifted outward from the slab's own edge — the higher the gap, the more
   the dashes read as floating past the corners rather than tracing them.
   Dropped to 0.605, right at the surface.
3. **The floor grid texture is gone.** Reported as visual noise on top of an
   already-tinted, now-textured (icon+stroke) sign — not polish. Removed
   `makeFloorTiles` entirely rather than toning it down.
4. **The department icon moved from a floating badge into the sign itself**,
   and the floating per-pod stat cards are gone. Both were the same
   complaint really — "the floor already says what this is, stop drawing
   more things above it":
   - `makeFloorTitle` now takes `opts.icon` and paints it once, inline, to
     the left of the name, on the same line and baseline — "📦 DELIVERY" as
     one sign, not a name plus a separately-floating sprite badge. Simpler
     than either of the two previous attempts (a canvas band above the name,
     then a floating `THREE.Sprite`) and needs no vertical offset math that
     could push anything into the desk.
   - The per-pod floating stat card (`.office-dept-card`, its CSS, and every
     function that built/positioned it) is removed outright, in both
     outlets. The floor sign already carries the pod's identity; a black
     floating box repeating seat/active/done counts above it was judged
     redundant now that the sign itself is more legible (see point 5) — the
     Task Status panel (a separate, still-present feature) already covers
     the aggregate counts in one place instead of scattered over the floor.
5. **"Subagents" (and department names) were hard to read against some pod
   colours.** A fixed mid-tone fill reads fine against a plain palette tone
   but not against every saturated department/cluster tint the floor can now
   be. `makeFloorTitle` now strokes each letter (and, implicitly, the space
   around the icon) in a colour from the opposite end of the lightness scale
   from its fill (new palette field `floorTitleStroke`, one per theme) before
   filling it — the classic "text with an outline" trick, which guarantees
   legibility against literally any floor colour rather than tuning one grey
   that happens to work against six specific hues. Sign opacity also bumped
   0.7 -> 0.85 for the same reason.

Verified: the pure `makeFloorTitle`/`makeWhiteboard`/`makePodGlow` behaviour
under real three.js-under-node (`test_office_visual_extras.py`, rewritten);
scene.js's wiring re-pinned (`test_office_visual_polish.py` — capped bloom
pixel ratio, shadowless whiteboard, the outline's new height constant, the
stroke/fill fields, the icon now living inside the `makeFloorTitle` call
instead of a `makeDeptIcon` sprite, `makeFloorTiles` gone from both files);
`test_office_pod_stat_cards.py` deleted outright (nothing left to test); the
Task Status panel's own node test fixed to match the renamed shared constant
(`_DEPT_CARD_TERMINAL` → `_TERMINAL_STATUSES`, since it now serves only that
panel); `test_office_browser_smoke.py`'s dept-card assertions removed, its
camera/task-status/console-error coverage otherwise unchanged and still
green; and manual Playwright screenshots (Business and Projects, overview and
focused) confirming the inline icon, the readable stroked text, the flush
outline, the absent floor grid, and the absent floating cards all actually
look right in the real running app.

### Follow-up same day: jagged edges, the outline gone for good, and reverting the icon

Screenshot-driven feedback against the pass immediately above -- some of it
reversed decisions from the *same day's earlier* follow-up:

1. **Model edges (a figure's head especially) were visibly jagged.** Root
   cause: routing the render through `EffectComposer` moved it off the
   canvas' own framebuffer, and WebGL only antialiases the default
   framebuffer -- the renderer's `antialias: true` had silently stopped
   doing anything the moment bloom landed. Fixed by constructing the
   composer with its own `WebGLRenderTarget(1, 1, { samples: 4, type:
   THREE.HalfFloatType })` instead of letting `EffectComposer` build its
   default one — `samples` asks for multisampling explicitly on that
   offscreen target; `HalfFloatType` is carried over from what the default
   target would have used, and matters because dropping it would clamp the
   glow mesh's deliberately-over-1.0 colour to white before bloom ever saw
   it.
2. **The dashed pod outline is gone entirely**, not just moved closer to the
   surface as the previous follow-up tried. `makeSlabOutline`,
   `setOutlineActive`/`marchOutline`/`advanceDashFade` calls on
   `record.outline` and `conductor.userData.outlineLine`, and the outline
   mesh itself are all removed from `scene.js`. `makeSlabOutline` stays
   defined in `builders.js` and fully tested in `test_office_outlines.py` --
   it's the same dashed-line machinery `makeConnector` (the conductor<->pod
   bridges, unaffected) still uses, just no longer called for a pod's own
   edge. A working pod's glow is now the only "this is active" signal on the
   floor.
3. **The department icon is removed, full stop** -- not moved, reverted.
   Both the inline-in-the-sign version from the same day's earlier
   follow-up and the floating-sprite version before that are gone:
   `makeFloorTitle` no longer takes an `icon` option, `roster.js`'s
   `DEPARTMENTS` lost their `icon` field and `iconForDepartment()`,
   `businessView()` stopped stamping `clusterIcon` on desks, and
   `layout.js`'s `computeLayout()` stopped deriving `pod.icon`. The
   contrast fix (stroked text, see the previous follow-up) stays -- that
   was a separate, still-wanted change.
4. **The floating per-desk nameplate ("<Department> Lead", the placeholder
   label an empty Business seat shows) is gone; the *nameplate feature
   itself* is not.** Only reported as unwanted for a seat nobody is
   actually sitting at, since the floor sign already names the department --
   a real worker's nameplate (current tool activity while running, or a
   summary once done, exactly what the report asked to keep) is untouched.
   `syncOffice`'s desk loop now sets `seat.plate.visible = (lod === 'near')
   && !!worker`, and `syncLod()`'s own zoom-driven toggle was given the same
   `!!seat.workerId` guard -- without it, zooming in/out would resurrect an
   empty seat's nameplate regardless of the desk loop's own decision.
5. **One of the two plants was blocking the floor sign's text.** The sign
   sits on a pod's `+z` corner; the plant at `[1, 1]` (also `+z`) shared that
   side and could overlap it, especially on a small pod. Removed that one,
   kept the `[-1, -1]` plant. The whiteboard (a different corner) is
   unaffected.

Verified: full office node suite green after each removal (`makeSlabOutline`
usage tests replaced with a "the outline is gone" assertion in
`test_office_visual_polish.py`, the two removed `test_office_outlines.py`
tests that pinned scene.js's old outline wiring dropped with a note pointing
at `makeSlabOutline`'s continued, correct, tested-elsewhere existence, every
`icon`-related test across `test_office_roster.py`/`test_office_layout.py`/
`test_office_visual_polish.py`/`test_office_visual_extras.py` removed
alongside the feature); `test_office_browser_smoke.py` unchanged and still
green under `HERMES_WEBUI_BROWSER_TESTS=1`; and manual Playwright screenshots
confirming an idle desk's nameplate is actually gone while a working one's
stays, the outline is actually gone, no icon appears, only one plant sits
near the sign, and — cropped in tight on a figure's head — the edges read as
antialiased rather than a staircase.

### Follow-up same day: the per-pod stat card was never asked to go

Reported: "the stat cards above the employees are now gone, please add that
back." A miscommunication from two follow-ups back — the floating per-pod
stat card (`.office-dept-card`: seat count, active/done, a department's name
and colour on Business) and the per-*desk* nameplate (`✓ Under tests/...`,
the black bar over a worker's own head) are two different, unrelated UI
elements, and "remove the black-background labels above the pods" was read
as covering both. The nameplate-only correction two follow-ups later (idle
seats hide theirs, a real worker's stays) fixed the wrong half of that
misread and never restored the other.

Fixed by reverse-applying exactly the hunks that removed it in the
smoothness/outline/icon commit — `officeCardSpecs()`/`renderDepartmentCards()`
/`repositionDepartmentCards()` and their module state back in `index.js`, the
`.office-dept-cards`/`.office-dept-card*` rules back in `style.css`,
`tests/test_office_pod_stat_cards.py` restored from git history, and
`tests/test_office_browser_smoke.py`'s dept-card assertions restored — while
leaving every other change from that commit and the two after it (bloom's
multisampled target, the outline's full removal, the icon's full reversion,
the idle-seat nameplate fix, the single-plant fix) untouched, since none of
those diffs ever touched this feature's code. The one adjustment on top:
`_DEPT_CARD_TERMINAL` (the restored feature's original name for its terminal-
status `Set`) renamed to `_TERMINAL_STATUSES` to match the name a later,
unrelated cleanup in the same commit gave it — the Task Status panel's own
node-driver test already expects that name, and duplicating the same `Set`
under two names would be worse than keeping one.

Verified: full office node suite green, including `test_office_pod_stat_cards
.py` restored verbatim; `test_office_browser_smoke.py` (its full original
dept-card assertions plus everything added since) green under
`HERMES_WEBUI_BROWSER_TESTS=1`; and manual screenshots of both outlets
confirming the cards are back, correctly named/coloured, positioned over
their pods, alongside every fix from the two follow-ups since (no outline,
no icon, the idle "Emails Lead"-style nameplate still correctly hidden).

### Follow-up same day: a collapsible Task Status column

Asked directly: make the Task Status column collapsible. `.office-tasks`
sits beside `.office-stage` in a flex row (`.office-body`); collapsing it
frees that width back to the canvas rather than merely hiding content in
place, since the canvas (`position: absolute; inset: 0` inside `.office-
stage`) already fills whatever room its flex sibling leaves it.

- A new `.office-tasks-collapse-btn` sits next to the "Task Status" title
  (both now wrapped in a `.office-tasks-head-row` flex row). Clicking it
  toggles `_tasksCollapsed` and an `is-collapsed` class on `.office-tasks`;
  `.office-tasks.is-collapsed{flex:0 0 40px;min-width:40px}` shrinks the
  column to a slim strip holding only the button, with everything else
  (title, filters, list) `display:none` under that class — never torn down
  and rebuilt, so re-expanding shows exactly what was there a moment ago.
  `flex-basis`/`min-width` transition over 180ms rather than snapping.
- Remembered the same way the outlet choice already is: a new
  `TASKS_COLLAPSED_STORAGE_KEY` / `readTasksCollapsed()` / `writeTasksCollapsed()`
  trio mirroring `OUTLET_STORAGE_KEY`/`readOutlet()`/`writeOutlet()` — a
  reload should not silently re-expand a column the user deliberately
  collapsed to get the canvas' width back.

Verified: new source-pinned tests in `test_office_task_status.py` (the button
is wired to the toggle function, the toggle flips state and persists it, the
collapsed CSS rule hides filters/list without removing them, `unmount()`
nulls the new element refs); the existing browser smoke test extended with a
real click-collapse-expand round trip under `HERMES_WEBUI_BROWSER_TESTS=1`,
asserting the canvas' own `getBoundingClientRect().width` actually grows
when collapsed and returns to exactly its original value on expand (not just
that a class toggled) and that the collapsed flag lands in `localStorage`;
plus manual screenshots of both states.

### Follow-up same day: conductor glow, a stray sidepanel, a fade, and unbounded ground

Five more reports, landed together:

1. **The conductor's own plinth no longer tints/glows with activity.**
   Reported as distracting -- it's the one fixed landmark on the floor,
   there whether anything is running or not, so it shouldn't visually
   change the way a working pod does. `ensureConductor()` no longer builds
   a glow mesh at all; the pacing figure already carries the "it's doing
   something" cue. Regular pods and the conductor's own status tracking
   (still needed by the pacing/wanderer logic) are unaffected.
2. **The chat-only Workspace panel (`<aside class="rightpanel">`:
   Files/Artifacts/Todos/Canvas/Live/Plane) was showing next to the Office.**
   It's a sibling of `<main>`, not a child, so none of the existing
   per-view `main.main.showing-X > #mainX` CSS rules ever touched it --
   added `main.main.showing-office ~ .rightpanel` (plus its edge-toggle
   button) via a general sibling combinator, hiding both specifically for
   the Office's own whole-screen, already-has-its-own-right-column layout.
3. **A cross-fade when switching Projects/Business.** `.office-canvas`
   fades to 0 and back via a new `is-switching-outlet` CSS class, so
   scheduleSync's desk/pod add-and-remove reconciliation (a hard cut
   otherwise -- furniture and figures blinking away mid-frame) reads as a
   deliberate transition. Two real bugs surfaced building this, both
   caught by sampling `getComputedStyle(...).opacity` every 10ms through a
   real switch rather than trusting a screenshot or a fixed wait:
   - A first attempt revealed the floor on a fixed `setTimeout` (guessed at
     220ms, matching the CSS transition duration). Switching to Business
     can mean waiting on a `/api/personalities` fetch and rebuilding a
     department's worth of floor signs -- measured well past that guess
     under load, so the timer fired before the new floor was actually
     drawn, revealing a stale or half-built frame. Fixed by tying the
     reveal to `scheduleSync()` itself finishing (a new `_outletFadePending`
     flag it clears once the synced floor is drawn), however long that
     takes.
   - That alone made the opposite mistake for a *cheap* switch: reconciling
     within a couple of frames let the class get added and removed again
     before the browser ever painted the faded-out state -- add-then-remove
     within the same frame or two is a known case of a CSS transition never
     being visibly observed, confirmed by the opacity sampling staying at
     `1` for the entire switch. Fixed with `OUTLET_FADE_MIN_MS` (220): the
     reveal now waits out whichever is longer, that minimum or the real
     sync time.
4. **Ground/grid size grows with the office instead of a fixed cap.**
   Reported: zooming out far enough on a large office showed the ground
   plane's own hard edge against the transparent canvas. A fixed size can
   never rule that out for an arbitrarily large delegation tree, so
   `ensureGroundCovers(radius)` (called from `frameOffice()`, which already
   recomputes the office's radius on every sync) rebuilds a bigger one --
   sized to cover the worst case the user can actually zoom out to
   (`ZOOM_MIN` beyond the office's own auto-framed fit, times a safety
   factor for wide-monitor aspect ratios) -- whenever the current one falls
   short. Never shrunk back down (a big run's pods being swept shouldn't
   flash the edge back into view), and grid divisions are capped at 600
   regardless of size (past a few hundred, lines are imperceptible anyway,
   and this only grows for a very large, very zoomed-out office).
5. **Investigated, not fixed here**: subagent interrupt ("Gateway chat
   backend is not enabled") turns out to need a `webui_chat_backend: gateway`
   config value *and* a running Hermes API server on the port it points at
   (`http://127.0.0.1:8642` by default) -- neither is present in this
   deployment (confirmed: nothing listening on that port), so flipping the
   config flag alone would just change the error, or break the main chat's
   own backend routing. Real fix is standing up that server, which is
   outside this repo's own code and needs its own decision, not a quick
   toggle.

Verified: full office node suite green, including new
`test_office_panel.py` (`.rightpanel` hiding), `test_office_visual_polish.py`
(conductor glow gone, ground growth/cap/never-shrinks, the two fade fixes --
the min-duration one pinned by name so a future refactor can't quietly drop
it back to "just wait for scheduleSync") tests; the existing browser smoke
test green under `HERMES_WEBUI_BROWSER_TESTS=1` (twice, given how
timing-sensitive this area proved); full suite (16034 passed clean); plus
manual Playwright verification for each -- a real 10ms-interval opacity
sampling script for the fade (screenshots alone had missed both bugs
entirely, since each failure mode is invisible at any single sampled
instant), and a zoomed-way-out screenshot with eight subagents for the
ground.
