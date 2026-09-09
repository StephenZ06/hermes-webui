# Project status — hermes-webui

Last updated: 2026-09-08. Written as a session handoff; read this before
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
   endpoint makes a delegated child block on its own parent until timeout.

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
nothing. And the child runs behind a synchronous `POST /api/chat`, so there is
no progress stream: start and complete only, never `subagent.tool`. A desk
showing invented tool activity would be worse than one that says "working".

Both idempotent. Currently protected: `tools/delegate_to_profile.py`,
`gateway/api_session_rollover.py`, `tools/skill_sections.py`, their tests, the
rollover port's patch to `agent/conversation_loop.py` and
`hermes_cli/config_defaults.py`, and section scoping's patch to
`tools/skills_tool.py`.

Full detail in `docs/architecture/agent-api-contract.md`.

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
9. Nothing else queued. The suite is green (15607 passed, 91 skipped — down
   from 118 because 27 previously-invisible tests now run), so a new failure
   from here is a real one, worth reading rather than filing next to a known
   backlog.
