# Project status — hermes-webui

Last updated: 2026-09-04. Written as a session handoff; read this before
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

Both idempotent. Currently protected: `tools/delegate_to_profile.py`,
`gateway/api_session_rollover.py`, `tools/skill_sections.py`, their tests, the
rollover port's patch to `agent/conversation_loop.py` and
`hermes_cli/config_defaults.py`, and section scoping's patch to
`tools/skills_tool.py`.

Full detail in `docs/architecture/agent-api-contract.md`.

## Next actions

1. **Observe a real rollover.** The one unverified claim. Needs a long session.
2. **Watch whether the model actually uses `skill_view(section=...)`.** The
   outline is charged to every unscoped view of a long document, so the feature
   only pays for itself if scoped calls happen. If they do not, the next lever
   is the tool description.
3. Nothing else queued. The suite is green, so a new failure from here is a
   real one — worth reading rather than filing next to a known backlog.
