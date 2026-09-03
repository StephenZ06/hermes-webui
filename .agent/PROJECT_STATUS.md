# Project status — hermes-webui

Last updated: 2026-09-03. Written as a session handoff; read this before
starting work on delegation, context cost, or anything in the agent checkout.

## Objective

Cross-profile delegation in the WebUI: a conductor turn should route a subtask
to whichever Hermes profile best fits it, rather than every subagent inheriting
the current profile. Delivered. Work then extended into context-cost reduction
and into hardening the things that were silently broken along the way.

## Current state

| Area | State |
|---|---|
| `master` | 126 commits ahead of `origin/master`, 0 behind. Rebased onto current upstream. |
| Deployment | Container `hermes-webui-hermes-webui-1`, healthy, built from `master`. |
| Test suite | 20 failures, against a 29-failure pre-rebase baseline. Net −9, zero new. |
| Fork | `master-rebased-onto-upstream` pushed to `StephenZ06/hermes-webui`. |

`origin` is `nesquena/hermes-webui` and rejects pushes (403). `fork` is the
writable remote. A stale `feature/plan-canvas` branch still sits on the fork
pointing at pre-rebase history; repointing it needs a force-push.

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

## Verified vs not

Verified with live turns or live measurement: delegation routing end to end;
depth isolation; the post-update restore path against a real wipe; the
lifecycle hook actually injecting; no horizontal overflow at phone viewports;
canvas costing zero model context; the repeated-result collapse saving 7.8% on
real transcripts.

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
`gateway/api_session_rollover.py`, their tests, and the rollover port's patch to
`agent/conversation_loop.py` and `hermes_cli/config_defaults.py`.

Full detail in `docs/architecture/agent-api-contract.md`.

## Next actions

1. **Observe a real rollover.** The one unverified claim. Needs a long session.
2. **`skill_view` section-scoping.** It is 36% of all model context. The cap
   makes truncation cheaper, not smarter; returning the relevant section is the
   real fix. Agent-side, so it needs patch protection.
3. **8 locale keys** (`session_fork*`, `cron_delegation_*`) missing across ~6
   languages. Deliberately left: user-facing copy needing review.
4. **Fork housekeeping.** Repoint or delete the stale `feature/plan-canvas`
   branch (force-push required).
5. Optional: 19 remaining pre-existing test failures, all failing before this
   work started. `test_static_asset_resolver` is order-dependent and passes
   standalone.
