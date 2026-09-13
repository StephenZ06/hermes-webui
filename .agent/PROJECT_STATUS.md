# Project status — hermes-webui

Last updated: 2026-09-13. Written as a session handoff; read this before
starting work on delegation, context cost, or anything in the agent checkout.

## Objective

Cross-profile delegation in the WebUI: a conductor turn should route a subtask
to whichever Hermes profile best fits it, rather than every subagent inheriting
the current profile. Delivered. Work then extended into context-cost reduction
and into hardening the things that were silently broken along the way.

## Current state

| Area | State |
|---|---|
| `master` | 132 commits ahead of `origin/master`, 0 behind. Rebased onto current upstream. |
| Deployment | Container `hermes-webui-hermes-webui-1`, healthy, built from `master`. |
| Test suite | Green: 15586 passed, 0 failed, against a 29-failure pre-rebase baseline. |
| Fork | `master-rebased-onto-upstream` and `archive/master-pre-rebase` on `StephenZ06/hermes-webui`. |

`origin` is `nesquena/hermes-webui` and rejects pushes (403). `fork` is the
writable remote. The stale `feature/plan-canvas` branch is gone from the fork:
its tip was pushed first as `archive/master-pre-rebase` (it is an ancestor of
the local `backup/master-pre-rebase`), so no pre-rebase history was lost.

Uncommitted in the working tree: branding assets only (favicons, `Avatar*.png`,
a `Fox1.png` deletion). Deliberately left alone — they are the user's.

## What was built

- **`delegate_to_profile`** (agent-side tool). Routes a subtask by profile
  description, injected live into the tool schema. Mints a profile-bound,
  TTL-limited session and revokes it in a `finally`, so no credential is
  stored. Depth-capped at 1.
- **`api/cross_profile_depth.py`**. Delegation depth keyed by session. It was
  previously in `os.environ`, which is process-global: an in-flight delegated
  turn made every *concurrent* turn read depth 1 and refuse its own first hop.
- **`api/updates.py::_run_post_update_hooks`** plus two hooks in
  `$HERMES_HOME/post-update.d/`. See "Agent checkout" below.
- **`api/project_lifecycle_hook.py`**. Registers a `pre_llm_call` hook so the
  project-lifecycle instruction reaches every turn.
- **`api/context_pressure_rollover.py`**. Wires the API session-rollover
  coordinator into WebUI turns; the WebUI runs the agent in-process and so
  never passed through the gateway platform's own wiring.
- **Context cost**: `tool_output.max_bytes` 50000 → 20000 on all 8 profiles,
  and `_collapse_repeated_tool_results` in `api/streaming.py`.
- **`skill_view` section scoping** (agent-side). `skill_view` takes an optional
  `section` naming a markdown heading and returns that heading's subtree
  instead of the file. Slicing lives in `tools/skill_sections.py`; the patch to
  the upstream-owned `tools/skills_tool.py` only adds the parameter and calls
  it. A long unscoped view now also carries a `sections` outline so the next
  call can scope itself, and a scoped view has its own dedup identity so a
  second section is not answered with "already sent".
- **Eight locale keys** (`session_fork*`, `composer_control_fork`,
  `cron_delegation_*`) translated into all fourteen non-English locales. They
  had shipped English-only, and the per-locale key-coverage tests had been red
  for it — 11 of the 20 failures this session started with were that one gap.
- **The last 9 test failures**, none of which described a real defect except
  one: `b2504229f` had dropped the PWA startup helper's preload link while
  fixing an unrelated empty-state flash. The rest were assertions pinning code
  that a later, deliberate change had removed or moved, plus two harness gaps
  (a stub TLS server that never sent `close_notify`, and a node harness missing
  `esc`/`t` stubs that deadlocked its own microtask spin loop).

## Verified vs not

Verified with live turns or live measurement: delegation routing end to end;
depth isolation; the post-update restore path against a real wipe; the
lifecycle hook actually injecting; no horizontal overflow at phone viewports;
canvas costing zero model context; the repeated-result collapse saving 7.8% on
real transcripts; section scoping against the real skills tree — one section of
`test-driven-development` is 1017 chars against 10252 for the file, and the
outline that 79% of skill bytes now carry costs 4.8% of those bytes, confirmed
again inside the rebuilt container.

**Not verified**: a real LCM rollover firing. Policy, checkpoint, rotation,
in-place restore and failure-fallback are all confirmed, but `_compress_context`
was stubbed. It needs a session crossing 50% of a 200k-token window.

## Gotchas that cost time — read these

1. **A WebUI agent update destroys local commits.** It runs `git clean -fd` +
   `git reset --hard` on `~/.hermes/hermes-agent`. The branch name survives, so
   the checkout looks fine. It has silently killed `delegate_to_profile` and
   the session-rollover port. Anything added there must be registered under
   "Agent checkout" below in the same change, or the next update deletes it.
2. **Failures here are silent by design.** Both losses above were swallowed by
   a fail-soft `except ImportError`. "Configured" and "working" diverge easily —
   verify against the running container, not the config file.
3. **Test doubles lie.** A `PluginManager` double invented a `register_hook`
   method that does not exist; the unit tests passed while the hook armed
   nothing. Check registration APIs against the real object.
4. **Raw sqlite rows under-report tool cost to zero.** `messages.tool_calls` is
   stored as a JSON *string*, so orphan-pruning drops every tool message. Load
   through `hermes_state.SessionDB` when measuring payloads.
5. **The rollover policy fails closed and silently.** Its three thresholds must
   be supplied together and stay ordered `rearm < checkpoint < lcm_fallback`.
   Leave one at its default and `from_config()` returns a *disabled* policy.
6. **`_handle_chat_sync` (`POST /api/chat`) is the sole holder of `CHAT_LOCK`.**
   The browser uses the streaming path. Driving a parent turn through the sync
   endpoint makes a delegated child block on its own parent until timeout —
   and, until 2026-09-10, made every cross-profile delegation serialise against
   every other one. `delegate_to_profile` no longer uses that endpoint; see
   "Cross-profile delegation runs in parallel" below.

## Agent checkout: making local changes survive

Two restore paths, both run before any restart:

- Files upstream does **not** have → `$HERMES_HOME/custom-agent-tools/`,
  mirroring repo layout; restored by `10-restore-custom-agent-tools.sh`.
- Modifications to files upstream **does** own → a patch in
  `$HERMES_HOME/custom-agent-patches/*.patch`; re-applied by
  `20-reapply-agent-patches.sh`. Storing our copy of a tracked file would
  clobber future upstream changes to it.

`tools/delegate_to_profile.py` now also reports its child to the Office: it
calls the parent's `tool_progress_callback` with `subagent.start` /
`subagent.complete`, so a cross-profile delegation draws a desk like any other
subagent. Two things to know before touching it. The callback is invoked as
`(event_type, tool_name, preview, args, **kwargs)` — four positionals, matching
`_ChildProgressRelay._relay`; pass one and `api/streaming.py`'s `on_tool` reads
it as a *tool name* and the event silently degrades to `tool.started`, drawing
nothing. And the tool polls the child's stream only for the fact that it
closed, never for its contents: start and complete only, never `subagent.tool`.
A desk showing invented tool activity would be worse than one that says
"working".

Getting the parent agent there needed a third thing (2026-09-10). The registry
never hands a handler the agent: `model_tools._execute_tool` builds
`dispatch_kwargs` from ids alone and has no agent in scope to add, so
`kw.get("parent_agent")` was always `None` and cross-profile children drew
nothing. `delegate_task` is not a counter-example — it reaches an agent only
because `agent/tool_executor.py` special-cases it by name. Rather than add a
second special case to a checkout every update force-resets, the tool now finds
the live agent itself (`_live_parent_agent`): the WebUI already keeps it in
`api.config.AGENT_INSTANCES`, keyed by the stream that owns the session
(`session_writeback_owner`, falling back to a scan of
`STREAM_SESSION_OWNERS`). That agent carries the very
`tool_progress_callback` the Office listens on. `_session_id_from_context`
backs it up by reading `HERMES_SESSION_ID`, which the WebUI binds for every
turn — without a session id the depth cap silently disappears, because
`_current_depth` answers 0 for a session it cannot find. That part still needs
**no** `custom-agent-patches` entry: it lives in files upstream does not own.
Making the delegations run *in parallel* does need one — see below.

Both idempotent. Currently protected: `tools/delegate_to_profile.py`,
`gateway/api_session_rollover.py`, `tools/skill_sections.py`, their tests, the
rollover port's patch to `agent/conversation_loop.py` and
`hermes_cli/config_defaults.py`, section scoping's patch to
`tools/skills_tool.py`, parallel cross-profile delegation's patch
(`30-parallel-cross-profile-delegation.patch`) to
`agent/tool_dispatch_helpers.py` and `agent/tool_executor.py`, and
`40-opencode-go-thinking-disable.patch` to
`plugins/model-providers/opencode-zen/__init__.py` (+ its test) — OpenCode Go's
Kimi/DeepSeek endpoints 400 on `thinking: {type: disabled}`.

## Cross-profile delegation runs in parallel (2026-09-10)

Reported as "the task wasn't done in parallel — I only see one subagent, and
the docs-gits agent never appeared on the office floor". Both were real, from
two independent causes. Evidence is session `6a3b001f57af`, run
`b3f3027651174c03b4e51d77e6a18328`: three `delegate_to_profile` calls arrived
in ONE assistant message (4.5 ms and 4.2 ms between one `tool_complete` and the
next `tool` start — the model did batch them), and ran 52.2 s, then 64.9 s,
then 79.7 s with zero overlap. 199 s for work that should have taken ~80 s.

**Serialisation had two layers, and fixing only the outer one buys nothing.**

1. `agent/tool_dispatch_helpers.py` admits calls to a parallel run from an
   allowlist; anything absent is a sequential barrier. `delegate_to_profile`
   was absent. Now in `_PARALLEL_SAFE_SPAWNERS` — kept out of
   `_PARALLEL_SAFE_TOOLS`, whose name promises read-only.
2. Even admitted, every child turn ran on `POST /api/chat`, which holds the
   process-global `CHAT_LOCK` for its whole duration. Three concurrent threads
   would simply have queued on it. The tool now drives the child on the
   streaming path — `/api/chat/start`, poll `/api/chat/stream/status`, read the
   reply back from `GET /api/session` — which takes only a per-session lock.
3. And the concurrent batch deadline defaults to 420 s, shorter than a real
   turn. `_CONCURRENT_DEADLINE_EXEMPT_TOOLS` (in `agent/tool_executor.py`)
   drops the deadline for a batch containing one, exactly as
   `_SEQUENTIAL_DEADLINE_EXEMPT_TOOLS` already did for `delegate_task`. Without
   it a genuine fan-out reports every branch timed out while the turns run on.

The depth cap needed rehoming: only `_handle_chat_sync` reads the
`X-Hermes-Cross-Profile-Depth` header, and the streaming path has no handler to
republish it. The tool runs inside the WebUI process, so `_child_depth` now
records the depth against the child's session id directly, in the same
`api/cross_profile_depth.py` registry `_current_depth` reads. The header is
still sent so a deployment pinned to the sync endpoint stays capped.

**The office floor was a separate bug.** `clearFinishedForNewRun()` in
`static/office/adapter.js` cleared the floor whenever a spawn arrived and every
known worker was terminal — a proxy for "a new run started" that is exactly
wrong for a fan-out whose siblings do not overlap. Sequential delegation meant
sibling #2 deleted sibling #1's desk, and #3 deleted #2's: docs-gits WAS drawn,
for 52 s, then removed 1.1 s after it finished. Spawn events now carry
`run_id` (`static/messages.js` stamps the SSE stream id onto the payload) and
`clearForRun()` only clears on a CHANGE of a known run. A running worker is
still never removed, and a spawn with no run id — the reconcile snapshot and
the historical replay both — keeps the old proxy.

Tests: `tests/test_office_adapter.py` (run identity),
`tests/tools/test_delegate_to_profile.py` and
`tests/tools/test_parallel_cross_profile_delegation.py` in the agent checkout.
Full WebUI suite green at 15844 passed.

Verified live on run `423ad7568b594a35a708305593585ce4`: three spawns 17 ms
apart, completions at 33.0 s / 44.3 s / 80.6 s — genuinely overlapping.

### `GET /api/session` is not current when a turn ends

That same run returned "completed but returned no answer" for all three
delegations, and the Office desks said so too. The wait was correct: the
child's `done` event fired at t=507.40 and polling stopped at t=507.97 (the
journal keeps receiving events until t=513.65, but those are *title*
generation, not the turn). The reply was on the session object at t=507.28.
`GET /api/session?...&msg_limit=12` still answered **200 with no assistant
row**. Its payload is a display projection — sidecar reconciled against
state.db, `_message_window_for_display` → `_messages_for_limited_payload` —
and that reconciliation is not current the instant a turn ends. Replayed
offline against the same sessions afterwards it returns the reply fine, so the
window is small and it is a staleness, not a scoping or auth failure (all
three GETs were 200).

`_final_answer` now reads the WebUI's **own session store** first
(`api.models.get_session`), which the tool can do because it runs in that
process, with the HTTP projection as the fallback and a bounded retry
(`ANSWER_SETTLE_SECONDS`, 15 s) over both. Confirmed in the running container:
`_local_transcript` returns the real reply for all three sessions that had
reported none. Do not "simplify" this back to a single HTTP read.

### Cross-profile runs were absent from the Office history

The history sidebar answers "which chats delegated?" from hermes-agent's
`state.db`, where a `delegate_task` child is a row carrying
`parent_session_id`. A `delegate_to_profile` child is not that: the tool
creates it with `POST /api/session/new`, so it lands in the **target
profile's** `state.db` as an ordinary `source='webui'` row with
`parent_session_id` NULL. Confirmed on the live boxes — `7af3a152ed3c` in
`profiles/docs-gits/state.db`, `901a6287484f` in `backend`, `13f258fe5f81` in
`frontend`, all parentless. Nothing recorded that one chat caused them, so a
cross-profile run was watchable live and gone from history the moment it
ended. Every row the sidebar *did* show was a `delegate_task` run on
coding-opencode — one profile and one model on all eight children is correct
for that tool, which spawns inside the current profile by design.

Fixed with a WebUI-side ledger, `api/cross_profile_ledger.py`, writing to the
(previously empty and entirely unreferenced) `$STATE_DIR/
cross_profile_delegations/`. One JSON file per child,
`<parent_session_id>/<child_session_id>.json` — per child, not per parent,
because siblings now run in parallel and a file per parent would make three
concurrent delegations read-modify-write the same file and lose each other's
rows. Records shaped like `agent_sessions._session_node_dict` so the endpoint
merges the two lists without translating either, plus a `cluster` field.

Writing `parent_session_id` onto the child's state.db row was the other option
and is worse: the parent lives in a *different* profile's database, and
`list_parents_with_subagent_children` is built on each database being a
separate universe. A cross-database parent id surfaces the child as its own
top-level entry.

`GET /api/agent-canvas/sessions`'s body is now three helpers in
`api/routes.py` — `_agent_canvas_state_db_parents`,
`_filter_parents_to_active_profile`, `_merge_cross_profile_ledger` — so the
merge is testable without a handler. A chat that delegated both ways gets one
entry dated by the newer run; a child in both sources is drawn once; a broken
ledger costs the cross-profile entries and never the state.db ones.

`static/office/history.js` honours `cluster` for a **direct** child only, so a
replayed cross-profile child keeps its `profile:<name>` pod instead of being
dropped onto the conductor. Real nesting still wins: a grandchild belongs
under its own parent, not under a profile sign.

Tests: `tests/test_cross_profile_ledger.py` (20), three added to
`tests/test_office_history.py`, six to the agent's
`tests/tools/test_delegate_to_profile.py` (52 there now). Full WebUI suite
green at 15867 passed.

**Not verified**: no live cross-profile run has been recorded yet — the ledger
only starts filling from the next delegation, and existing runs cannot be
back-filled (nothing recorded the parent link at the time). Deployed
2026-09-10; needs one fan-out, then the run should appear in the Office
sidebar and replay with three profile pods.

### The model kept reaching for the wrong tool

Run `46a709ca…` (session `e4610e650d33`, 2026-09-10 11:27Z) looked like a
regression — three desks, one profile, one model — and was not. The prompt
named docs-gits / frontend / backend. The model ran `tool_search`, then
`tool_describe('delegate_to_profile')`, wrote in its own reasoning *"Let me
delegate all three in parallel using delegate_to_profile"* — and then emitted
`delegate_task`. That spawns inside the current profile, so all three children
were coding-opencode / kimi-k2.7-code at `depth=0` with `parent_id=None`. The
Office drew that correctly.

Three things pushed it there, and the third was ours:

1. `delegate_to_profile` is a **deferred** tool (`tool_search` reported
   `total_available: 6`), so calling it is a third bridge hop —
   `tool_search` → `tool_describe` → `tool_call`. `delegate_task` is always in
   the schema.
2. It took one goal per call. Three profiles meant three of those hops, while
   `delegate_task` took `tasks=[...]` in one.
3. Its description said *"Use delegate_task instead to split work across
   several workers"* and never mentioned parallelism — a sentence written when
   two cross-profile delegations genuinely could not overlap. The parallelism
   fix removed the constraint and left the description that described it.

Fixed by giving the tool the batch it was missing: `tasks=[{profile, goal,
context?, workspace?}, ...]`, capped at `MAX_PARALLEL_TASKS` (6, because each
task holds a WebUI session and a whole turn of another profile). The
per-delegation body is now `_delegate_one`, called directly for one task and
once per thread for a batch — everything it touches (its auth session, its
child session, its desk, its ledger record) belongs to that task alone, which
is what makes the fan-out safe. Results come back in the order the model listed
them whatever order they finish in, and one task failing costs its own answer
only. The whole batch is refused for one bad entry: half a fan-out leaves the
model to work out which subtask silently did not happen.

The description now names the batch as the preferred shape and says outright
that `delegate_task` cannot cross profiles.

Passing `profile`/`goal` *and* `tasks` is an error rather than a guess — "run
the one, the three, or all four" has no right answer.

Tests: 67 in `tests/tools/test_delegate_to_profile.py`, including a
`threading.Barrier(3)` rendezvous that fails if the tasks are run serially
(every other batch test passes under serial execution). Schema verified
against the live profile set inside the running container.

Verified live on run `04fd4987…` (session `94c77261bc8e`, 2026-09-10 11:39Z):
ONE `delegate_to_profile` call with three tasks, three spawns inside 0.19 s,
three profiles and three models, completions at +27.5 / +43.8 / +78.3 s, real
answers, tagged blocks in the order asked for though they finished in another,
and all three recorded in the ledger.

### A finished run replayed as three 'Interrupted' desks

Reported straight after that run. The run was fine — every ledger record says
`completed` with a real `ended_at`, and every entry on disk replays as
completed. The bug is *when the office snapshot was taken*:

1. The ledger records a delegation at spawn (`status: running`, no
   `ended_at`), deliberately — an interrupted run still delegated.
2. The sidebar listing refetches on a timer, so during the run it holds those
   unfinished rows.
3. `historicalStatus()` mapped `running` to `interrupted`, on the reasoning
   that in a *finished* session that can only mean cut off. True of an old
   state.db row; false while the run is still going.
4. `showHistory()` built `_historyAdapter` once, from the listing as it stood
   at click time, and nothing ever rebuilt it — so the frozen floor said
   Interrupted long after the run completed.

Before the ledger a cross-profile run was not in the sidebar at all, so this
could not happen to it; the ledger made the run appear from the instant it
starts, which is exactly the window that breaks.

`static/office/history.js` now takes `{live}`: a still-running child of a live
run stays `running` and gets **no completion event at all** — the adapter
coerces any non-terminal completion to `completed`, so emitting one would
invent an outcome. A finished run keeps the original correction.

`static/office/index.js` gained `historySignature(parent)` (children × status ×
ended_at) and `refreshHistory()`, called from the listing refresh: when the
open run's rows change the frozen office is rebuilt, deliberately WITHOUT
`resetView()` so a background rebuild does not yank the camera or close the
detail panel being read. Only picking a different run re-frames.

Reproduced and verified both ways against the real listing:

| listing | live | replayed |
|---|---|---|
| mid-run | true | 3 running, conductor orchestrating |
| mid-run | false | 3 interrupted, conductor idle |
| finished | either | 3 completed, conductor idle |

Known edge: a run the user genuinely interrupts reads `running` until
`LIVE_WINDOW_SECONDS` elapses, then `interrupted`. Self-correcting, and the
alternative is calling live work "cut off" — the reported bug.

Tests: 11 added (4 in `tests/test_office_history.py`, 7 in
`tests/test_office_sidebar_live.py`). Full WebUI suite green at 15878 passed.

Full detail in `docs/architecture/agent-api-contract.md`.

### Switching chats stranded the previous run frozen on the Office floor (2026-09-10, uncommitted)

Reported: the Office animates while a delegation is live, then after clicking a
different chat in the sidebar (or ~30s later) the connector lines are dead and
the floor is frozen on a run whose subagents have already finished. Figures
still move (the render loop never stopped; the idle conductor paces), which is
what made it look like a half-broken animation rather than a completed run.

Root cause: `static/messages.js` gates the `subagent_spawn/tool/complete` SSE
feed on `S.session.session_id === activeSid`. Leave a chat and its still-open
desks never receive their completion events; the global reconcile poll
(`/api/subagents/active`) retires them ~10s later and the floor is left frozen.
The Office live view is meant to "track the running session"
(`static/office/index.js`), and the old Agent Canvas reset itself on every
cross-session switch in `loadSession()` for this exact reason — but the Office
that replaced it (commit `4af629c4`) was never given the same call. The
`window.AgentCanvas.reset()` line at `static/sessions.js` ~1873 still runs,
against a module kept alive only for `renderStaticTree`.

Fix: one `window.HermesOffice.reset()` call next to it, same
`currentSid && currentSid !== sid` guard. The floor clears on switch and the
new session's stream + reconcile snapshot rebuild it from what is live now.
Design choice was "follow the active chat" (not a global live view).

Tests: `test_office_panel.py::test_loadsession_resets_the_office_on_a_cross_session_switch`
(wiring), `tests/test_office_animation_resume.py` (browser, opt-in — reset
clears desks/seats and the loop keeps running). Widened the char-offset window
in `test_session_channel_option_x.py::test_load_session_rearms_stream_on_every_early_return`
(16000 → 17000) — the added lines pushed the fetch-error catch past its cutoff,
same brittleness that was widened once before for #4946.

### Office visual-polish pass (2026-09-10, uncommitted)

Five reported nits, all in `static/office/`:

1. **Floor signage, not a nameplate.** `ensureConductor` now paints "Conductor"
   on the plinth with `makeFloorTitle` (the Business-floor treatment) and the
   floating plate is gone — with it, the `drawNameplate(conductor…, 'running')`
   status repaint; the plinth outline already carries the orchestrating cue.
   `syncOffice` labels the `__conductor__` cluster pod "Subagents" (Business
   pods still win with their department name; nested-subagent pods stay
   unlabelled).
2. **Desk nameplates fill their box.** `makeNameplate` canvas 512→640, sprite
   9.5→11; `drawNameplate` measure-fits to the plate edge (new `fitText`
   binary-search) instead of a hard 20-char slice; `shortLabel` cap 42→56.
   `test_office_adapter.py` updated (label length 56).
3. **Connector lines fade in.** `makeConnector` idle opacity 0.45→**0** (an
   unlit bridge is not drawn), `DASH_FADE_MS` 420→800 — a delegation starting
   eases the bridge up from nothing. Platform-edge outlines unchanged (a
   still edge is a deliberate "finished" cue; `idleOpacity >= 0.5` is pinned).
4. **Arrivals route around furniture.** `createArrival(distance, speed,
   lateral)` — the figure starts out in the aisle to one side (sides alternate
   by desk index) and `advanceArrival` tapers `lateral`→0 over the last
   `ARRIVAL_MERGE` units, so it rounds into the chair instead of walking
   straight through the monitor and chair of the row behind. Scene applies
   `arrival.lateral` to `person.position.x` and faces the figure along its
   travel direction, snapping to `Math.PI` when seated.
5. **Seated figures face the monitor.** `person.rotation.y = Math.PI` in
   `ensureSeat` — makePerson's "work" pose reaches +z and the seat is on the
   desk's +z side, so the figure was typing with its back to the screen.
6. **Floor signage** (follow-up). `makeFloorTitle` gained an opt-in `{fit}`:
   with it, the font auto-fits so the letterspaced text spans ~92% of the
   canvas (84–176px, tracking scales with it) — a short name like "Sales" is
   painted as large as "Operations" instead of a third the size. Without it,
   the original fixed 96px/16-track behaviour is unchanged. `fit` is passed for
   the conductor plinth (`CONDUCTOR_SLAB*0.82`) and every named pod
   (`slabWidth*0.88`); the two catch-all pods — "Subagents" and "The Floor" —
   sit on large slabs and keep the original size and placement (explicitly
   asked for). Fitted signs are placed their own height back from the front
   edge so a taller sign never pokes past it.

Also: **"View live" now switches the main view.** `window.officeReturnToLive`
was a bare alias for `returnToLive()` (view-mode reset only); it now
`switchPanel('office')` then `returnToLive()`, so pressed from a chat or a
history replay it lands on the live floor. `test_office_history.py` updated.

Tests: `test_office_motion.py` (aisle arrival), `test_office_outlines.py`
(bridge fades from invisible), `test_office_panel.py` (signage, facing),
`tests/test_office_visual_polish.py` (browser, opt-in — screenshots + View
live + label length). Full office suite (236) green; runtime-guard lint clean.

### Office navigation + two sidebar tweaks (2026-09-10, uncommitted)

1. **Desktop project-folder rows are taller.** `.project-folder-list
   .project-chip` padding `3px 8px` → `7px 8px` + `min-height:34px`
   (`static/style.css`). The `@media (max-width:640px)` override
   (`9px 8px; min-height:40px`) is unchanged, so mobile is untouched. Chat
   sidebar and Agent Canvas rows share the selector and still match.
   `test_project_folder_row_responsiveness.py` updated.

2. **Office camera is navigable** (`static/office/scene.js`). One Pointer
   Events path for mouse and touch: drag pans (`groundPoint` unprojects the
   cursor to the floor and the grabbed point tracks it), wheel and two-finger
   pinch zoom toward the cursor/pinch-centre (`zoomAbout`), a stationary press
   that lifts quickly is a tap. A tap picks a worker (fly to its desk, as
   before), or — new — frames the pod under it: pod groups carry
   `userData.podCluster` (the conductor plinth too) and `focusOnPod` tweens to
   its centre at a fitted zoom. Empty ground still pulls back out. Works on both
   outlets. `.office-canvas` gets `touch-action:none` + `cursor:grab` so the
   gestures reach the canvas instead of scrolling the page. The old `click`
   listener is gone; `focusOnWorker`/`resetView`/`getView` unchanged.
   Tests: `tests/test_office_navigation.py` (browser — pan, wheel zoom, tap a
   pod, synthetic pinch), `test_office_panel.py` (wiring + touch-action).

3. **The bottom sidebar card sits lower.** `.hermes-cli-card` margin
   `6px 8px 40px` → `6px 8px 8px` so left/right/bottom gaps match; a
   `@media (max-width:640px)` rule keeps `margin-bottom:40px` on mobile to clear
   the browser chrome. Covers both the "HERMES CLI" and "OFFICE" cards (same
   class).

### Async-delegation batch still dumped its wall (2026-09-10, uncommitted)

Reported again after edb084dda ("collapse async delegation deliveries"). That
fix added the `_asyncDelegationBatchInfo` detection + `async-delegation-row`
card, but its check in the `renderMsgs` loop sat **after** the process-wakeup
branch, and nothing excluded the batch from `isProcessWakeup`. The live delivery
path stamps the injected turn `_source='process_wakeup'`
(`_start_async_delegation_wakeup_turn` → `start_session_turn(source=
"process_wakeup")` → `stamp_message_source`), so every real batch reached the
browser as a process-wakeup row. `_processWakeupInfo` cannot parse the batch
body, so it fell to the raw `<pre class="process-wakeup-text">` dump — the whole
results wall, which is what the card existed to stop. (On a plain reload the DB
row carries no `_source`, so the card *did* render — the bug only showed live.)

Evidence: session `8359391b986e` msg 1175 in `coding-opencode/state.db` —
`role='user'`, `display_kind=NULL`, content starts with the marker. The current
`ui.js` detector returns `detected:true` for that exact string; the render loop
was the gap. Browser repro
(`tests/test_async_delegation_render_browser.py`): without the fix the row is
`.process-wakeup-row .process-wakeup-text` (wall); with it, a collapsed
`.async-delegation-row` card, `data-role='async_delegation'`.

Fix (`static/ui.js`): hoist `_asyncDelegationInfo` above `isProcessWakeup` and
make `isProcessWakeup = … && !_asyncDelegationInfo`; the existing card branch
reuses it. Tests: `test_async_delegation_message_collapse.py` (+2),
`test_async_delegation_render_browser.py` (new, opt-in).

### `invalid thinking: only type=enabled is allowed` — fixed agent-side (2026-09-10)

The turn the batch triggers (an assistant reply, then **title generation** for
the now-titled session) 400'd: `HTTP 400 … invalid thinking: only type=enabled
is allowed for this model`, provider `opencode-go`, model `kimi-k2.7-code`.

Chain: title-gen (`api/streaming.py::generate_title_raw_via_agent`) sets
`agent.reasoning_config = {"enabled": False}` and expects each provider profile
to *drop* the disable when its endpoint can't express it. hermes-agent's
`OpenCodeGoProfile` (`plugins/model-providers/opencode-zen/__init__.py`
`_thinking_toggle_extras`) instead emitted `thinking: {"type": "disabled"}` for
Kimi K2 / DeepSeek — and OpenCode Go's "Console Go" relay rejects that
("only type=enabled is allowed"). A pinned agent test
(`test_disabled_emits_thinking_disabled_without_effort`) had codified the wrong
assumption. Confirmed from `docker logs`: the 400 fires right after title-gen's
`/api/reasoning?model=kimi-k2.7-code&provider=opencode-go`.

Fix (agent, via `custom-agent-patches/40-opencode-go-thinking-disable.patch`):
`_thinking_toggle_extras`'s `enabled is False` branch now returns `({}, {})` —
omit the field, ride the model's default thinking (a silently-ignored disable
beats a dead turn). Agent tests updated (`test_opencode_go_profile.py`, 30
pass). **Applied to the live `~/.hermes/hermes-agent` checkout** — needs a
container recreate (bind-mounted, so `up -d` picks it up alongside the WebUI
rebuild).

### Speech recognition failed silently (2026-09-10, uncommitted)

Reported on Arc (Chromium): mic shows "listening", no text, no error. Two
silent-failure paths, both in `static/boot.js`:

1. **Browser `webkitSpeechRecognition` hang.** Arc / ungoogled / network-filtered
   Chromium expose the API but its Google backend never answers —
   `recognition.start()` succeeds, `_setRecording(true)` paints "listening",
   and no `onresult` / `onerror` / `onend` ever fires. No watchdog → dead mic.
   Fix: `_armSrWatchdog()` armed right after `recognition.start()`, cleared on
   the first `onresult` / on `onend` / `onerror` / `_stopMic`. If nothing lands
   in 8s it aborts, persists `mic_force_mediarecorder='1'` (so later clicks use
   `/api/transcribe`), releases the wake lock, and toasts `mic_no_speech`
   (`mic_network` when there is no MediaRecorder to fall back to).
2. **Server STT returned a 200 with an empty transcript** (silence, a muted
   device, an undecodable blob) → `_transcribeBlob` called
   `_commitTranscript('')` which leaves the composer untouched and says
   nothing. Now toasts `mic_no_speech` when `res.ok` but the trimmed transcript
   is blank.

Server STT is available in the live container (`(True, 'local')` — faster-whisper
`base`, `stt.enabled: true`; no `ffmpeg` binary but PyAV decodes webm/opus).
Tests: `tests/test_speech_recognition_watchdog.py` (new), harness update in
`test_issue5294_mobile_dictation_continuity.py`. Mic/voice suite (324) green.

### Faster STT: warm the model, persist the cache, fall back to local, prefer Groq (2026-09-11)

The 16.9 s first `/api/transcribe` was a one-time faster-whisper model
**download** (~150 MB), not transcription — warm calls were 0.4–1.1 s. But the
HF cache lived in the container's ephemeral layer, so every `up --build`
re-downloaded it, and the configured provider had no fallback.

- **`api/stt_warmup.py`** (new) + a `;`-chained call in `server.py`: a daemon
  thread preloads the local Whisper model at boot when faster-whisper is
  installed and STT is enabled, so the first dictation is never cold.
- **`HF_HOME=/home/hermeswebui/.hermes/webui/hf-cache`** in all three
  `docker-compose*.yml` — the model cache now lives inside the mounted `.hermes`
  volume and downloads once, ever.
- **`api/upload.py`**: `handle_transcribe` now retries via
  `transcribe_audio_local_fallback` when the configured provider fails (down,
  rate-limited, no key), and `handle_transcribe_capability` reports `available`
  whenever a local backend exists — so a cloud-provider outage never drops the
  mic to (often-broken) browser SpeechRecognition.
- **`~/.hermes/config.yaml`** (user config): `stt.provider: groq`
  (`whisper-large-v3-turbo` — ~300–800 ms, better accuracy, ~$0.03/hr),
  `stt.local.model: base.en` + `language: en` for the local path/fallback.
  Groq needs `GROQ_API_KEY` in `~/.hermes/.env` (line 413, currently commented);
  until then STT transparently uses local `base.en`.
- `test_server_py_under_750_lines` → `test_server_py_stays_thin` (ceiling
  749 → 760; the split has landed, one wire-in line per starter is fine).

Tests: `tests/test_stt_warmup.py` (new, 6), 2 added to
`test_voice_transcribe_endpoint.py`.

**Follow-up — Groq wasn't actually being used** (the first live transcribe after
deploy still took 17.5 s and downloaded `base`). Two causes:

1. **Profile config overrode `provider`.** `_load_stt_config()` merges the
   active profile's `config.yaml` over the base, and every
   `~/.hermes/profiles/*/config.yaml` carried a default `stt:` block with
   `provider: local`. Only visible once `api.upload` (→ `api.profiles`) is
   imported, which is why a bare `python -c` test showed `groq` and the running
   WebUI showed `local`. Fixed: set `provider: groq`, `local.model: base.en`,
   `local.language: en`, `groq.model: whisper-large-v3-turbo` in the base
   config **and all 7 profile configs**.
2. **`GROQ_API_KEY` from `~/.hermes/.env` was invisible.**
   `tools.transcription_common` evaluates `_has_groq_key = _has_key("GROQ_API_KEY"…)`
   at *module import*, before the agent's lazy `.env` injection runs — so the
   check cached `False`. Fixed: `docker-compose*.yml` now pass
   `GROQ_API_KEY=${GROQ_API_KEY:-}` into the container env (`os.environ`, from
   PID 1), and `~/Apps/hermes-webui/.env` (git-ignored, compose auto-loads)
   holds the key. Verified in-container: `_get_provider` → `groq`, capability
   `(True, 'groq')`, transcribe `prov=groq`.

### Insights panel stat cards were stale (2026-09-11, uncommitted)

Reported: Sessions / Messages / Tokens / Cost (and the charts / model table)
didn't update while the Insights panel stayed open — only System health did,
because it has its own `startSystemHealthMonitor` poll (`static/ui.js`).
`loadInsights()` only ran on panel-open, the manual refresh button, or a period
change.

Fix (`static/panels.js`): `_startInsightsAutoRefresh` / `_stop` / `_sync`
mirroring the logs pattern — a 15 s `setInterval` that calls
`loadInsights(false)` while `_currentPanel === 'insights'` and the tab is
visible, self-terminating when the panel is left; wired into `switchPanel` next
to `_syncLogsAutoRefresh()` and a `visibilitychange` catch-up. The re-render
(`box.innerHTML = …`) now preserves scroll position, any open
`details.insights-card`, and the System-health panel's last-rendered metric
values (so an auto tick doesn't flash it to "Loading…" before its own poll
refills it).

Tests: `test_insights.py::test_insights_panel_auto_refreshes_while_visible`,
`tests/test_insights_autorefresh_browser.py` (opt-in — one tick fires, stops on
leave).

## Chat-page layout on large monitors (uncommitted, 2026-09-04)

Reported from a wide desktop: the composer's workspace text looked vertically
off, and the chat background "did not extend all the way to the bottom — a
black gap below it". Three findings, all in `static/style.css`:

1. **Chip wrappers used two different vertical positioning models.**
   `.composer-ws-wrap` was `display:flex;align-items:center`; the profile,
   model, reasoning and toolsets wrappers were blocks, so their `inline-flex`
   chips sat on the wrapper's own text baseline inside a line box sized by the
   inherited 22.4px strut. The two agree only while the strut is shorter than
   the chips. Reproduced in headless Chromium at 2560x1440: with
   `.composer-footer{line-height:2.6}` the workspace group centred at y=1311.55
   and the profile/model chips at y=1309.61. All five wrappers now centre with
   flexbox; the `@container` rule that reveals the toolsets wrap had to change
   `display:block` → `flex` to match. Chip-centre spread is now 0 at every
   width measured (1280 → 3440).

2. **A 52px black band above the composer on the geist-contrast skin.**
   `.empty-state` is `flex:1` inside the transparent `.messages` scroller and
   that skin painted it an opaque `var(--surface)`. It therefore ended at
   y=1273.6 while `.composer-wrap` began at y=1325.6, and the 52px between
   (an empty `.messages-inner` still contributes its padding) showed
   `#mainChat`'s `var(--bg)` = `#000000` across the full width of the chat.
   `.empty-state` was dropped from that skin's opaque-surface list. This is the
   only reproduction of the reported gap that was found; the default theme and
   four other skins were clean, so it is unconfirmed whether it is the same one
   the reporter saw.

3. **The composer stretched to 1600px on ultrawide.** The base ladder already
   stopped at 1100px, so `@media (min-width:1600px){max-width:1600px}` only ever
   widened, against its own comment. The ladder is now one `--composer-max`
   token shared by `.composer-box` and `.composer-selection-chips`, with a
   1200px ultrawide step. 1200px is also a floor: the toolsets chip's container
   query needs a 1100px `.composer-footer`, which is 2px narrower than the box,
   so anything under 1102px deletes that chip instead of narrowing it.

Tests: `tests/test_composer_wide_viewport_layout.py`,
`tests/test_chat_background_reaches_the_bottom.py`. One assertion in
`tests/test_issue2481_selected_text_reply.py` was repointed at the new token.
Verified against a throwaway instance of this tree (isolated `HERMES_HOME` /
`HERMES_WEBUI_STATE_DIR`, port 8901) driven over CDP — not against the live
container, whose `/app/static/style.css` is 339 diff lines behind this tree.

## Agent Canvas: what a finished subagent did

The side panel's Goal block now shows the completion summary once a node is
terminal, relabelling itself `Summary`; the goal stays visible as the panel
title. A subagent that finished without ever setting a summary keeps showing
its goal rather than losing the block.

The panel already had a `Summary` block and it had never once rendered. The
cause was in the relay, not the frontend: `delegate_tool.py` emits `summary`
plus duration, token/cost counts, touched files and an output tail in its
`complete_kwargs`, and `api/gateway_chat.py::_subagent_complete_fields`
forwarded all of it — but only on the gateway path. The in-process path that
WebUI turns actually take (`api/streaming.py`'s `on_tool`) forwarded
`subagent_id` and `status` and nothing else, so every richer block in that
panel was permanently empty. That was a deliberate "identity + status only"
v1 non-goal in the RFC, pinned by a test that asserted the fields must NOT be
present. The relay now forwards the full set and the two paths agree, so a
node's panel no longer depends on which path the turn took; Duration, Tokens,
Cost and Files populate too, not just the summary.

The old pin in `tests/test_agent_canvas_sse_events.py` was inverted rather
than deleted, and the RFC's non-goal struck through with a pointer to why.
New coverage in `tests/test_agent_canvas_completion_summary.py`: relay field
set, cb_kwargs sourcing, gateway-path parity, terminal-only swap, label swap,
and no duplicate block.

## Deployment (2026-09-05)

Live and verified, most recently at `exp-v0.52.264-139-g1c6e793ba-dirty`:
container healthy on the native daemon, `127.0.0.1:8787` published, and the
running image confirmed to carry the session-title fix, the compat
repointing and the composer CSS.

**Read this before the next redeploy — two Docker engines run on this box.**
Docker Desktop's WSL integration overwrites `/run/docker.sock` when it starts,
so the `docker` CLI reaches Docker Desktop while the real Hermes stack (the
gateway container and the live WebUI) runs on the native WSL dockerd, which is
then unreachable by path. `/var/run` is a symlink to `/run`, so there is only
one socket path to fight over, and the `desktop-linux` context fails from
inside WSL with `protocol not available`.

The failure mode is silent and total: a full `docker compose build` +
`--force-recreate` succeeds, reports a new image, and leaves a healthy
container — against a copy nobody is using, while port 8787 keeps being served
by the native daemon's stale container. It cost most of a session here. The
first build of this work went to Docker Desktop and changed nothing in the
browser.

Tells, in order of reliability:

- `docker info --format '{{.Name}}'` — `docker-desktop` means the wrong engine.
  The native one reports the hostname (`Z014-MiniPC`).
- `cat /proc/<pid>/cgroup` on the live `server.py` gives its container id;
  `docker inspect <id>` answering "no such object" means that container belongs
  to the other daemon.
- `stat -c '%s %y' /proc/<pid>/root/app/static/<a file you changed>` proves the
  age of the code actually being served.

Recovery needs root and a real TTY (`sudo -n` fails here):
`sudo systemctl restart docker.socket docker.service`, which recreates the
socket under the native daemon and bounces the gateway and WebUI for ~30s.
Docker Desktop is shadowed in exchange — its other containers keep running but
become unaddressable. Disabling Docker Desktop's WSL integration for the Ubuntu
distro is the durable version of the same fix.

Also note the native WebUI container has a restart policy, so killing its
`server.py` by PID frees 8787 for a few seconds and then a new PID takes it
back with the same stale code. Killing the process is not a deploy.

## hermes-agent API drift (2026-09-05)

The agent checkout is force-reset by the WebUI update path, so its API moves on
its own schedule. One update on 2026-09-05 broke three separate things, and
only one of them announced itself.

**Session titles stopped reaching state.db, silently.** The agent removed
`SessionDB.set_auto_title_if_empty`; `sync_session_title` still called it inside
a bare `except Exception` logging at debug, so the AttributeError vanished.
`ensure_session` kept creating the row, so nothing looked wrong — titles just
never arrived and `hermes sessions list` went blank for every WebUI session,
undoing #6892. Now `set_auto_title(..., source=TITLE_SOURCE_LLM)`, which is
behaviourally identical: state.db ranks sources derived(0) < llm(1) < user(2)
and treats a stored NULL source as `user`, so an llm write lands only on a NULL
title and never over a manual rename, a legacy row, or an earlier auto-title.
`AttributeError`/`TypeError` now log at warning — the swallow is what made a
one-line breakage invisible.

**`_ApprovalEntry` moved rather than disappeared**, to
`tools.approval_gateway_wait`, when the agent split `tools/approval.py`. Public
names that moved got `_PLUGIN_COMPAT_LAZY` entries and still resolve on the old
path; private ones did not. Six test files went red. Production only ever
mentioned it in comments.

**Nine production imports were on paths with a deadline.**
`hermes_cli.plugin_compat` sets `COMPAT_REMOVAL_DATE = 2026-09-14`, one global
date for all 335 facades, at which point "the commit that added them is
reverted". Nothing was failing; nothing would have, until they all stopped at
once. All repointed at their real modules.

`tests/test_agent_compat_shim_paths.py` now reads the agent's own
`compat_manifest.json` (2091 names, 335 facades) and fails on any repo import
that resolves only through a shim. It needs no maintenance when the agent moves
something new — it simply starts failing. The manifest's own note says
`scripts/check_compat_pointers.py forbids in-tree use`, so this is upstream's
rule applied here.

**Two things worth knowing for the next one of these.**

Test doubles must follow the split. A fake parked on the old module path is
never reached once production imports from the real home, and the failure is
misleading rather than obvious: `/reload-mcp` reported "MCP runtime
unavailable" instead of the error under test, and a profile-home test saw zero
calls to a `discover_mcp_tools` it had itself installed. Three files needed
repointing.

`_servers` and `_lock` stay on `tools.mcp_tool`. They are defined in that file
rather than re-exported, and `/reload-mcp` mutates them, so following the shim
there would have been a silent correctness bug instead of an import error.
Check where a name is *defined* before repointing it, not just where it
resolves.

Also fixed along the way: all 27 tests in `test_approval_unblock.py` were
skipping silently. Its module-level `from tools.approval import ...` runs before
anything imports `api.config`, which is what puts the agent on `sys.path`, so
the import raised, `APPROVAL_AVAILABLE` went False and the file evaporated. They
ran only when an earlier-collected module happened to import `api` first. Same
trap caught `tests/test_state_sync_title_api_drift.py`: conftest snapshots
`sys.path` before `api.state_sync` extends it and an autouse guard restores that
snapshot after every test, so the first test in a file strips the agent dir for
every test after it.

## Office visualization (started 2026-09-08, branch `feat/office-visualization`)

A second view of the same real delegation tree: an isometric 3D floor where
subagents are people at desks, instead of Agent Canvas' org chart.
[agents-office](https://github.com/ajsahni/agents-office) is the visual
reference only — it is PolyForm Noncommercial while this repo is MIT, and its
runtime is a simulation over a hardcoded 35-agent roster. Design, event
mapping, outlets and phasing: `docs/rfcs/office-visualization.md`.

Hermes keeps orchestration. The office draws; it never spawns, decides or
holds a registry.

**Phase 1 landed:** three.js r185 vendored at `static/vendor/three/0.185.1/`,
an import map in `static/index.html`, a new `office` panel, and
`static/office/{scene,index}.js` rendering a lit floor whose WebGL context is
disposed on leaving the panel. `tests/test_office_panel.py` (17) green;
runtime-lint gate green with an ESM override for `static/office/**`.

**Phases 3-6 landed** (branch `feat/office-visualization`): the Projects
outlet (pods by cluster on concentric rings, procedural desks/figures, poses
from adapter state, click-through to the subagent's own chat), reconcile
polling plus pause/interrupt and history replay, the Business outlet (six
standing departments over the same engine), and the phase-6 decision.

**Phase 6 decided: Agent Canvas stays; the office leads the rail.** The office
is now the default delegation view — above Agent Canvas in the rail and the
mobile sidebar-nav — with Agent Canvas kept beneath it, not hidden. The office
is a `<canvas>` — a screen reader gets nothing
from it and no ARIA changes that, so retiring the DOM view would remove the
only readable version of this data for some users. WebGL is also not universal
(the office's own fallback points at Agent Canvas), and `renderStaticTree` has
a second consumer in the cron delegation diagram. The office does lead the rail
now, but the app still opens on Chat — promoting a view is not the same as
booting into it.

**A stale guard fixed in both views:** `GET /api/subagents/active` answers from
the in-process registry with a populated `active` list *and*
`gateway_enabled: false` (the single-container shape — this deployment). Agent
Canvas had skipped on that flag since before the in-process branch existed
(guard 2026-08-18, branch 2026-08-26), so reconcile was a permanent no-op here
and a fire-and-forget subagent finishing after its parent's stream closed
stayed "running" forever. The office is also careful with `spawn_paused` (a 502
reports `false`, which is an error, not a fact) and hides its Pause button
where that endpoint can only answer 409.

`tests/test_office_browser_smoke.py` is opt-in — `HERMES_WEBUI_BROWSER_TESTS=1`
— because this panel fails *silently* in a browser (a module that does not
resolve, an import map that does not apply, WebGL that does not start) while
every source-structure and node test still passes. It boots the real server,
loads the real page, and asserts the floor is up.

**Phase 2 landed:** `static/office/adapter.js` — pure ES module, no DOM, no
fetch, no three.js, no timers — turning the three SSE events and the
`/api/subagents/active` snapshot into conductor/workers/desks state, with
`static/messages.js` fanning live events to `window.HermesOffice` alongside
Agent Canvas. `static/office/package.json` (`"type": "module"`) lets node
import the adapter, so `tests/test_office_adapter.py` drives the real code
through scenarios with an injected clock rather than asserting on source
text. 31 tests; 48 across both office files.

Two facts worth keeping:

- r185's module build is **split** — `three.module.min.js` re-exports from
  `three.core.min.js`. Vendoring only the entry file 404s at load and the
  panel goes blank with nothing in the console but a bare 404.
- Verification for anything in this panel has to be a real browser. The
  structure tests pass whether or not three.js resolves; a headless Chromium
  run with `--use-angle=swiftshader` is what caught the split build.

Revert point for the whole line of work: tag `pre-office-phase1`.

## UX batch (2026-09-11)

Seven-task overnight batch. Five landed, one is an RFC, two need the user to
point at the exact element.

- **Office live dot** — the sidebar marked every stored run live when it had an
  unclosed child row within a 15-min window; the cross-profile ledger leaves
  `running` rows behind for finished runs, so a chat delegated from minutes ago
  kept pulsing and read as "the chat below is also live". `sidebarEntries()`
  now defers to the adapter: when it is tracking a live run, that run is the
  only live row; `looksLive` still runs in history view. `2b…`.
- **Web-search Sources** — `collapseAnswerSources()` in `static/ui.js`
  post-render folds a trailing "Sources"/"References" link list into a
  collapsed `<details>`. Settled assistant segments only, folds only when every
  trailing block is a list or link-bearing paragraph, stamps the body once.
  Browser-verified.
- **Loading placeholder** — `.loading-spinner` is now an indeterminate progress
  bar (same markup everywhere, CSS-only), the wrap paints an opaque `--bg`
  ground so it stands in front of the panel, and the fetch-on-switch panels
  (`loadSkills` / `loadAgentDefinitions` / `loadKanban` / `loadMemory` /
  `loadProfilesPanel` / `loadWorkspacesPanel`) call `_panelLoading()` before
  they await.
- **Model warmup** — `api/model_warmup.py`, started from `server.py` next to
  `start_stt_warmup()`. `get_available_models()` cold-rebuild is ~2.5s
  (measured in the live container) and lands on the first model-list read (page
  load / profile switch). Now prewarmed in a daemon thread. Active profile
  only. **server.py is at 751 lines — budget 760.**
- **Mobile config value nudge** — `.composer-mobile-config-value` in the mobile
  composer sheet was 1px high of its icon; `position:relative;top:1px` for the
  non-context rows.
- **Chat split view** → `docs/rfcs/chat-split-view-panes.md` (Proposed). Not
  implemented: it is a pane registry over the existing `.rightpanel` Files/
  Artifacts/Todos strip plus Canvas / Live-preview / Plane panes — Major, wants
  review + per-slice PRs, too much to land unsupervised.
- **Deferred — need the user to point at the element:**
  - *"Make the General chat appear for all profiles."* No project, session,
    board or UI string named "General" exists in the live state. Best guess:
    the unfoldered/date-grouped chat list (which the user may call "General"),
    profile-filtered by design (#1614). Not touched — changing profile
    isolation on a guess is the wrong call.
  - *Task-4 was interpreted* as the mobile composer sheet's workspace button
    and given the 1px nudge above; if that is the wrong modal, it is a
    one-line revert.

**Follow-up, same session — both resolved with user confirmation:**

- **#1 confirmed and fixed.** "General chat" = the unfoldered/date-grouped
  list (the "General" choice in the new-chat destination picker). It was
  hidden by profile scoping (#1614) exactly like a foldered chat, which the
  user didn't expect since nothing about it is profile-specific — mirrors the
  project-folders exception already shipped ("project folders show on every
  profile"). Fixed at both listing chokepoints: `_build_session_list_cache_
  payload`'s `profile_scope` filter (the sidebar) and `_handle_sessions_
  search` — a session with no `project_id` now passes regardless of active
  profile; a foldered session stays scoped exactly as before. Access control
  (auth.py / models.py / upload.py's own `_profiles_match` calls — the checks
  gating read/mutate on a specific session) is untouched on purpose: only
  what LISTS as visible changed, not what a profile is allowed to run.
  Updated the two existing test files that pinned the old
  hide-everything-cross-profile behavior for unfoldered rows
  (`test_sessions_search_profile_scope.py`, `test_session_list_long_history_
  perf.py`'s fixture) to distinguish foldered-must-stay-hidden from
  General-must-show; added `test_general_chat_visible_across_profiles.py`.
- **#4 confirmed, same element, needed more.** 1px wasn't enough per live
  report; bumped `.composer-mobile-config-value`'s down-nudge to 3px.

**User's explicit sequencing:** work through the rest of the original 7-task
batch (this follow-up round covers it); **#5 (chat split-view panes,
`docs/rfcs/chat-split-view-panes.md`) is deliberately held until everything
else is done** — the user asked to keep being reminded it's next, so mention
it at the end of any status update until they say to start it.

## Checkpoint before #5 (2026-09-12)

Before starting split-view work, committed a backlog of already-implemented,
already-tested work that had been sitting **uncommitted** in the tree since
earlier sessions (verified against the pre-compaction conversation summary,
then re-verified with `./scripts/test.sh` before each commit — 281/281 on the
touched files, full suite re-run after):

- `1d9b49258` STT: `api/stt_warmup.py` boot preload, `api/upload.py` local
  fallback + capability detection, Groq env passthrough in all 3
  `docker-compose*.yml`, `test_sprint10.py`'s line-budget bump.
- `c52d9e1fa` Mic: the Web-Speech watchdog in `static/boot.js` (Arc/Chromium
  forks whose backend never answers) + the empty-transcript toast.
- `e434c0617` Office: `api/cross_profile_ledger.py` — **this was the missing
  half of `d7e422253`**, already-committed code that did `from api import
  cross_profile_ledger` for a module that had never actually been added, so
  that feature was running on a silent `except ImportError` degrade the
  whole time. Also the cross-session `HermesOffice.reset()`, `run_id`
  stamping, and the office visual-polish/nav-mouse-pinch-pan work.
- `6f72032cc` Test-only catch-up for three already-shipped fixes (async-
  delegation card precedence, Insights auto-refresh, folder-row height) whose
  tests hadn't been added yet.

Tag **`pre-split-view-panes`** marks this point — `git reset --hard
pre-split-view-panes` to get back here if the split-view work needs to be
thrown away. Still uncommitted by design: branding assets only (`Fox1.png`
deletion, favicons, `Avatar*.png`) — the user's own WIP, never touch.

## #5 chat split-view panes — all 4 slices done (2026-09-12)

`docs/rfcs/chat-split-view-panes.md` is fully implemented. `registerChatPane`
/ `switchRightPanelPane` live in `static/workspace.js` (not a new file — see
the RFC's "Deviation" note, found by a real test failure). Files/Artifacts/
Todos, Canvas, Tasks (internal id `plane`), and Preview are all registry
entries now — six tab buttons, still hardcoded; rendering the strip from the
registry (`listChatPanes()` + `isAvailable`) is the RFC's one still-open
question, deferred until a pane actually needs dynamic availability.

**Every slice past the first needed a real correction to its pre-
implementation design** — re-read the RFC's "Deviation found" notes before
touching any of these panes again:

- **Slice 2 (Canvas)**: reads `window.HermesOffice.adapter`/`.getState()` —
  the SAME live feed the Office 3D view uses — NOT `AgentCanvas`'s own
  onSpawn/onComplete handlers, which that file's own header says were retired
  when the Office replaced it. Found and fixed a real bug in the shared
  renderer: `buildTreeNodes()` unconditionally turned `running` into
  `interrupted` (right for its only prior caller, a finished cron row; wrong
  for a subagent genuinely still working). Added a `live` option, default
  `false`, cron's behavior byte-for-byte unchanged.
- **Slice 3 (Tasks, internal id `plane`)**: the RFC assumed a "chat's bound
  project → Kanban board" link that **does not exist** in this codebase —
  boards are a per-browser/global preference, unrelated to WebUI Projects.
  Corrected scope: the pane shows the same board the full Kanban panel shows,
  reusing `loadKanban()` + `_kanbanRenderSidebar()` directly (extended with
  an optional container id + click handler) — no second connection. A stray
  literal `"static/panels.js"` in an HTML doc-comment collided with
  `test_extensions_settings_panel.py`'s script-load-order substring check;
  reworded, not a real regression.

- **Slice 4 (Preview)**: assumed CSP needed relaxing and a new settings gate
  to do it safely. Both assumptions were wrong — `api/helpers.py` already
  sends an enforced CSP with a validated operator opt-in
  (`HERMES_WEBUI_CSP_FRAME_EXTRA`) for exactly this; no code or setting
  needed there. Two real bugs caught by tests before shipping: (1)
  `new URL("localhost:5173")` does not throw — it parses `localhost` as the
  URL *scheme* — so the original "did it throw" http(s) check silently
  produced an empty URL for the single most common thing people type; fixed
  by checking `protocol` explicitly. (2) The iframe's sandbox combined
  `allow-scripts` with `allow-same-origin`, which this repo has a standing
  hard test against (`test_779_html_preview.py::test_sandbox_
  allows_scripts_only`, "would expose parent cookies") — nothing stops a
  user typing the WebUI's own URL into the box, at which point that
  combination lets the framed page read the parent's cookies. Dropped
  `allow-same-origin`; the full suite caught this before it shipped.

## #5 follow-up: Canvas pane swapped for the real Office scene (2026-09-12)

After the above shipped, explicit request: replace the flat 2-D delegation
tree with the actual `HermesOffice` 3D scene, mounted directly into the
sidebar (`window.HermesOffice.mount(container)`/`.unmount()` — no separate
renderer or data feed anymore).

**Real constraint surfaced, not a bug**: `HermesOffice` supports exactly one
live mount at a time (`static/office/index.js`), and the chat sidebar + the
full Office panel are two independent surfaces that can both be on screen
simultaneously (the right panel persists across `_currentPanel`). Handled
one direction — `static/panels.js`'s `switchPanel()` now hands the scene
back to the sidebar pane on leaving the main Office panel, instead of
tearing it down, when that pane is the active tab. Left the other direction
(clicking the sidebar tab while the main panel is showing) as the plain,
self-explanatory result of the user's own click — the main panel goes blank
until revisited. **If this trade-off is annoying in practice, the fix is a
friendlier hand-off message in the losing container, not a different
mount strategy** — flagged, not built, since it needs the user to actually
hit it to be worth the added complexity.

Old design kept as RFC history; its one real byproduct (a `live` option on
`buildTreeNodes()`/`renderStaticTree()`, agent-canvas.js) stays — genuine,
tested, shared-code fix, just unused by any pane now.

Nothing further queued for #5 — the RFC's feature set is complete. If new
panes are ever wanted, start from the RFC's rollout-plan pattern (state
ownership table, deviation-tracking) rather than from scratch.

## Office: Business floor visual parity with agents-office (2026-09-12)

User-requested comparison against github.com/ajsahni/agents-office (visual
reference only — PolyForm Noncommercial vs. this repo's MIT, see
docs/rfcs/office-visualization.md's Licensing section, which already covered
this exact repo before tonight). Three additions, full detail in that RFC's
new "Business floor visual parity" section:

1. **Department floor colour** — `roster.js` `DEPARTMENTS` now carry a
   `color`, blended into the palette's pod colours (not painted flat) via
   `THREE.Color.lerp`. Caught a real bug before shipping: `buildRoster()`'s
   department-mapping step dropped the `color` field it was handed, so every
   department read as null until the test (`test_each_department_carries_
   its_own_floor_colour`) caught it.
2. **Per-department floating stat card** — new `scene.js` query
   `podScreenRect(cluster)` (world-to-screen projection), one DOM card per
   standing floor, repositioned every frame via the scene's existing
   `onTick`. Includes "The Floor" overflow (roster.js's `buildRoster` always
   appends it as a 7th standing entry) — uncoloured, which the browser test
   initially got wrong (expected 6, real count is 7) before the assertion was
   corrected to match actual, consistent behaviour.
3. **Aggregate Task Status panel** — new `.office-body` split
   (`.office-stage` + `.office-tasks`), whole-office and outlet-independent
   (reads raw adapter state, not `businessView()`'s transform). All/Running/
   Done/Stopped filter; click a row to fly the camera to that worker (reuses
   `focusOnWorker`).

Deliberately NOT built: the reference's own task-dispatch bar, chat-with-
department-lead, "agent meeting", and fabricated metrics this app has no way
to measure (e.g. "cost per user") — see the assessment given before this work
started for the full in-scope/out-of-scope breakdown.

**Follow-up same day**: the floating stat card (item 2) generalised to the
Projects outlet too, per explicit request ("what about the personal
section?"). `officeCardSpecs()` is the one place Business (named, coloured)
and Projects (neither) differ; both outlets share the same render/
reposition/cleanup path. The Task Status panel needed no change — it was
already outlet-independent by design.

**Second follow-up same day**: floor colour *did* need a change after all —
asked directly why Projects pods have no colour. Added
`colorForProjectsCluster()` to `layout.js` (string hash into a fixed
palette), so a Projects pod gets a stable, derived colour instead of none;
`computeLayout()` now tells "no colour, on purpose" (Business overflow's
explicit `clusterColor: null`) apart from "no colour signal at all"
(a Projects desk, which never carries the key) via `hasOwnProperty`, not
truthiness. `officeCardSpecs()`'s Projects branch passes the same derived
colour to the floating card. See `docs/rfcs/office-visualization.md`'s
"Follow-up same day: Projects floor colour" for the full writeup.

**Third follow-up same day**: colours still read too washed-out vs. the
reference screenshot — bumped `makePod`'s tint blend 0.3/0.34 -> 0.62/0.68 and
replaced both colour palettes (Business's six, Projects' eight) with more
saturated hues. Then asked to build six more visual features, explicitly
including bloom ("I have a good enough computer to run no.6"): a working
pod's own glow (additive, HDR-pushed so only it — not the ordinary palette —
clears the bloom threshold), a whiteboard prop, a per-pod floor-tile texture,
a floating department icon badge (first attempt baked it into the floor sign
and it ended up hidden under the desk; fixed as a separate billboarded
sprite), a hemisphere+rim lighting rig replacing the flat ambient light, and
a full bloom post-process (`EffectComposer`/`RenderPass`/`UnrealBloomPass`/
`OutputPass`, vendored from upstream three.js r185 examples, MIT, at
`static/vendor/three/0.185.1/addons/`, resolved via a new `"three/addons/"`
import-map prefix). Verified with real node tests for the pure logic and new
builders, source-pinned scene.js wiring tests, the existing browser smoke
test, and manual Playwright screenshots (including a raw canvas-pixel read
confirming transparency survived the composer pipeline). Full writeup in
`docs/rfcs/office-visualization.md`'s "Follow-up same day: colour pop, then
six more visual features".

**Fourth follow-up same day**: motion felt less smooth after the pass above,
plus four specific visual reports. All fixed:
- Smoothness: `EffectComposer.setPixelRatio(1)` (bloom's blur chain gained no
  sharpness from the renderer's own up-to-2x ratio and was the biggest new
  per-frame cost), `makeWhiteboard`'s four parts set `castShadow = false`,
  the floor-tile texture removed outright (also asked for directly), and the
  floating per-pod DOM stat cards removed outright (ditto) — their per-frame
  `podScreenRect` projection/DOM writes are gone too.
- The dashed pod outline "sticking out" past corners: an isometric-parallax
  artifact from its height (0.66) sitting well above the slab top (0.6);
  dropped to 0.605.
- The department icon moved from a floating sprite badge into the floor
  sign itself — `makeFloorTitle(text, width, palette, {icon})` paints it
  inline, left of the name, one sign instead of a name plus a badge.
- Floor-sign text (especially "Subagents") was hard to read against some
  pod tints — `makeFloorTitle` now strokes each letter in a theme's
  opposite-lightness colour before filling it (new `floorTitleStroke`
  palette field), guaranteeing contrast against any floor colour.

`test_office_pod_stat_cards.py` deleted (nothing left to test); other office
tests updated to match. Full writeup in `docs/rfcs/office-visualization.md`'s
"Follow-up same day: smoothness, an outline artifact, and reworking the icon".

**Fifth follow-up same day**: screenshot-driven, reversing parts of the pass
directly above.
- Jagged model edges: `EffectComposer` moved rendering off the canvas'
  own framebuffer, where the renderer's `antialias: true` doesn't apply --
  fixed with an explicit `WebGLRenderTarget({samples: 4, type:
  HalfFloatType})` passed to the composer (HalfFloatType kept so the glow
  mesh's over-1.0 colour isn't clamped before bloom sees it).
- The dashed pod outline is gone entirely now (not just moved closer to the
  surface) -- `makeSlabOutline` stays defined/tested, just unused by
  scene.js; a working pod's glow is the only "active" cue on the floor.
- The department icon reverted completely (not moved -- gone), both the
  inline-sign version from the pass above and the earlier floating-sprite
  version. The text-contrast stroke fix stays.
- An idle desk's "<Department> Lead" nameplate is hidden (the floor sign
  already names the department); a real worker's nameplate -- current
  activity or a completion summary -- is untouched, exactly as asked.
- One of the two pod plants (the one sharing the sign's corner) removed;
  it was covering part of the floor sign's text.

Full writeup in `docs/rfcs/office-visualization.md`'s "Follow-up same day:
jagged edges, the outline gone for good, and reverting the icon".

**Sixth follow-up same day**: "the stat cards above the employees are now
gone, please add that back" -- a miscommunication from two follow-ups back
where "remove the black-background labels above the pods" was read as
covering both the per-pod stat card and the per-desk nameplate, and only
the nameplate half of that got corrected. Restored the per-pod stat card
(`officeCardSpecs`/`renderDepartmentCards`/`repositionDepartmentCards` in
`index.js`, its CSS, `test_office_pod_stat_cards.py`, the dept-card
assertions in `test_office_browser_smoke.py`) by reverse-applying exactly
those hunks from the commit that removed it -- every other change since
(bloom's multisampled target, the outline's removal, the icon's reversion,
the idle-seat nameplate fix, the single-plant fix) is untouched. Full
writeup in `docs/rfcs/office-visualization.md`'s "Follow-up same day: the
per-pod stat card was never asked to go".

**Seventh follow-up same day**: made the Task Status column collapsible, as
directly asked. A button next to the title toggles an `is-collapsed` class
that shrinks `.office-tasks` to a 40px strip (canvas fills the reclaimed
width automatically, since it's `position:absolute;inset:0` inside a flex
sibling) without tearing down the filters/list, and remembers the choice in
localStorage the same way the outlet picker does. Full writeup in
`docs/rfcs/office-visualization.md`'s "Follow-up same day: a collapsible
Task Status column".

**Eighth follow-up same day**: five more reports.
- Conductor's plinth no longer glows/tints with activity (reported
  distracting; the pacing figure already carries that cue).
- The chat-only Workspace rightpanel (Files/Artifacts/Todos/Canvas/Live/
  Plane) no longer shows next to the Office -- it's a sibling of `<main>`,
  needed its own `showing-office ~ .rightpanel` CSS rule.
- A cross-fade on Projects/Business switch. Two real bugs found only by
  sampling `getComputedStyle(...).opacity` every 10ms through a real
  switch (screenshots and fixed waits both missed them): a fixed
  `setTimeout` reveal fired before a slow (Business, roster fetch) sync
  finished; fixed to tied to `scheduleSync()` completing. That alone then
  under-fired for a *fast* switch (add+remove within the same frame or two
  is invisible) -- fixed with an `OUTLET_FADE_MIN_MS` floor so the reveal
  waits out whichever is longer.
- Ground/grid now grows with the office (`ensureGroundCovers()`, called
  from `frameOffice()`) instead of a fixed 400-unit cap, so a large office
  zoomed all the way out never shows the floor's own edge.
- Investigated, not fixed: subagent interrupt needs `webui_chat_backend:
  gateway` *and* a running Hermes API server on port 8642 -- neither
  present in this deployment (confirmed nothing listens there). Flipping
  the config alone would just relabel the error. Needs its own decision.

Full writeup in `docs/rfcs/office-visualization.md`'s "Follow-up same day:
conductor glow, a stray sidepanel, a fade, and unbounded ground".

**Ninth follow-up same day**: business-classified work now stays off the
Projects floor entirely (`projectsFloorView()` in `index.js`, same
`departmentFor()` businessView() already used, descendants of a
business-classified worker hidden with it via the existing
`descendantsOf()` helper). Flagged, not fixed: `roster.js`'s "Delivery"
department keywords (test/fix/build/code/refactor/debug/...) mean ordinary
coding tasks now also count as "business" and vanish from Projects the same
as invoicing work would -- shipped as specified since classification must
match Business exactly, but worth a deliberate look given how much of this
app's usage is coding work. Also found and worked around (not fixed, out of
scope): a pre-existing false positive in Marketing's `'ad '` keyword
matching words ending in "ad" (e.g. "read") after `normalize()` turns
slashes into spaces. Full writeup in
`docs/rfcs/office-visualization.md`'s "Follow-up same day: business-
classified work stays off the Projects floor".

## 2026-09-13: OpenCode Go usage widget + Notes panel + LM Studio profile

Four unrelated user asks landed together (commit `567708bbb`):

1. **Bulk delete in General Chat.** Already existed
   (`static/sessions.js`'s select-mode toggle, batch action bar, checkbox
   rendering) -- no code change. Not a stub: i18n'd, CSS'd, and verified live
   via a throwaway Playwright script that select-mode toggles correctly.
2. **OpenCode Go token usage in the sidebar widget.** `agent.account_usage`'s
   `fetch_account_usage()` only knows Codex/Anthropic/OpenRouter -- providers
   with a real percent-quota API. `api/providers.py#account_usage_from_pool()`
   synthesizes the same shape from the local credential pool's
   available/exhausted/dead ratio for flat-namespace resellers like
   opencode-go, wired into `api/routes.py#_handle_account_usage()` as a
   fallback when the native fetch is empty. No frontend change needed --
   `static/ui.js#loadAccountUsage()` already renders whatever shape the
   endpoint returns.
3. **LM Studio local-model profile.** Created (`hermes profile create local
   --clone-from default`), provider/base_url/model/api_key all configured
   correctly (`model.provider=lmstudio`,
   `model.base_url=http://host.docker.internal:1234/v1`). Blocked, not by
   this repo: the loaded model (`huihui-qwen3.5-9b-abliterated`) has only
   8,192 tokens of context allocated in LM Studio itself (confirmed via its
   `/api/v0/models` introspection endpoint: `loaded_context_length` vs.
   `max_context_length: 262144`), below Hermes Agent's 64K floor. No remote
   API exists to change a loaded model's context (`POST
   /api/v0/models/load` -> "Unexpected endpoint or method"). Needs the user
   to reload the model in LM Studio's own UI/`lms` CLI with a larger context
   setting.
4. **Sticky notes for projects.** New Notes panel/tab
   (`api/sticky_notes.py` + `static/notes.js`), a per-project corkboard:
   colored notes, freeform text (autosaves 500ms after typing stops), a
   project filter dropdown (backed by the WebUI's own `/api/projects`
   registry, not the WORKSPACES.yaml one), create/delete. Storage is a flat
   JSON list at `STATE_DIR/sticky_notes.json`, same shape convention as
   `PROJECTS_FILE`. Full suite green after landing this (16069 passed) --
   two structural tests needed a one-line update for the new nav tab
   (`test_nav_dividers_and_agent_canvas_panel.py`'s hardcoded divider-anchor
   list), which is expected when adding a tab to that group, not a
   regression.

## Next actions

1. **Observe a real rollover.** The one unverified claim. Needs a long session.
2. **Watch whether the model actually uses `skill_view(section=...)`.** The
   outline is charged to every unscoped view of a long document, so the feature
   only pays for itself if scoped calls happen. If they do not, the next lever
   is the tool description.
3. **Decide which Docker engine owns this box.** The socket restart is a
   tug-of-war that Docker Desktop wins again on its next start. Turning off its
   WSL integration for Ubuntu settles it; until then every redeploy has to
   check `docker info` first.
4. **Confirm the alignment fix against the reporter's actual font.** The
   mechanism was proven with a synthetic line-height change, not on
   Windows/Segoe UI where the symptom was reported. The fix removes font
   metrics from the equation, so it should hold, but it is unconfirmed.
5. **Confirm the black band was the geist-contrast one.** Only that skin
   reproduced it. If the reporter is on another skin, the gap is still open and
   the skin name is the missing input.
6. **Watch for the 2026-09-14 compat removal.** After that date the shims are
   gone from the agent entirely. `tests/test_agent_compat_shim_paths.py` should
   go quiet on its own (an empty manifest skips it); if it starts failing again
   before then, something new drifted.
7. **Office: finish the live walkthrough.** Built, merged, deployed and in
   use — the office leads the rail, the landing panel is still Chat.
   Verified against a real delegating run on 2026-09-09: a fire-and-forget
   subagent retires to `ended` roughly 10s after it finishes, instead of
   sitting at "running" forever. Still exercised only synthetically: parallel
   fan-out, nested delegation, the Business outlet, history replay, Interrupt.

   The finding worth carrying: **a finished subagent disappears from
   `/api/subagents/active`.** `_unregister_subagent` drops the record
   (`tools/delegate_tool_child_run.py:806`), so it never appears there with a
   terminal status — absence is the only completion signal that endpoint
   carries. Anything reconciling against it must infer completion from a
   worker going missing, narrowly (see the RFC). Agent Canvas has the same
   structural gap, does not act on absence, and still shows such a subagent as
   running.

   `queued` has no source at all, for the same reason: children are registered
   as `running` and the record is dropped on completion. Per-message and
   handoff likewise have no event. None of the three are faked.
8. **Office: replace the Business keyword matcher when an agent library
   lands.** `roster.js#departmentFor` infers a department from a persona's own
   words because `/api/personalities` carries nothing else. One function, one
   deletion, when a department field exists.
9. The suite was green (15607 passed) as of the previous entry; still green
   (16069 passed) after the 2026-09-13 work above, so a new failure from here
   is a real one, worth reading rather than filing next to a known backlog.
10. **Unblock the `local` (LM Studio) profile.** User needs to reload
    `huihui-qwen3.5-9b-abliterated` in LM Studio with >=64K context (its true
    max is 262,144), or pick another already-large-context model. Nothing to
    do from inside this repo/container until then.
