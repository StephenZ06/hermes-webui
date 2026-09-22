# Performance and Minimal Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Hermes interactions measurably faster while defaulting new sessions to the smallest safely enforceable optional-tool set.

**Architecture:** Browser-owned primitives provide generation guards, profile-scoped cache keys, and in-memory timings. A server policy resolver persists requested policy separately from resolved toolsets, sends the exact resolved list through `StartRunRequest`, and fails closed if minimal mode cannot be enforced.

**Tech Stack:** Python 3.11–3.13, vanilla JavaScript, existing MotionUI/CSS, pytest, Node syntax checks.

**Spec:** `docs/superpowers/specs/2026-09-22-performance-and-minimal-tools-design.md`

## Global Constraints

- Do not add frameworks, build tools, dependencies, or telemetry.
- Key every browser cache by complete active-profile and panel identity.
- Preserve per-client profile isolation and reduced-motion behavior.
- Never label a policy Minimal unless the runtime receives a restrictive exact toolset list.

## Review Focus

- Rapid A→B→A panel transitions: only the final intent may change the visible DOM.
- Two profile tabs: cache data and late responses cannot cross profile boundaries.
- Empty toolset semantics: `[]` cannot silently fall back to inherited global tools.
- Existing/branched sessions retain their historical override unless a policy is selected.
- Delegated/background work receives its own resolved policy, never an accidental parent expansion.

---

### Task 1: Add client interaction primitives

**Files:** Create `static/performance.js`; modify `static/index.html`; create `tests/test_client_performance_primitives.py`.

**Interfaces:** Export `window.HermesPerformance.begin(surface, identity)`, `isCurrent(ticket)`, `mark(ticket, phase)`, and `cacheKey(surface, profile)`. A ticket is `{surface, identity, generation, startedAt}`.

- [ ] **Step 1: Write the failing test.** Add `test_performance_helper_has_profile_scoped_generation_and_marks`, asserting that `static/performance.js` defines `begin(surface, identity)`, `isCurrent(ticket)`, `performance.mark`, and `surface + ':' + profile`.
- [ ] **Step 2: Verify red.** Run `./scripts/test.sh tests/test_client_performance_primitives.py -q`. Expected: FAIL because the helper does not exist.
- [ ] **Step 3: Implement minimal code.** Store generations in a `Map`; `begin` increments the exact `surface:identity` key and emits the intent mark; `isCurrent` compares only that key; `mark` no-ops without Performance API; `cacheKey` returns the full `surface:profile` key. Load the script before `panels.js`.
- [ ] **Step 4: Verify green.** Run `./scripts/test.sh tests/test_client_performance_primitives.py -q && node --check static/performance.js`. Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add static/performance.js static/index.html tests/test_client_performance_primitives.py && git commit -m "perf: add client interaction primitives"`.

### Task 2: Prevent stale panel work and mark readiness

**Files:** Modify `static/panels.js`; create `tests/test_panel_switch_generation.py`.

**Interfaces:** Consume Task 1 helpers. `switchPanel()` must create `panelTicket = HermesPerformance.begin('panel', nextPanel)`, mark `usable` after synchronous class/DOM selection, and stop post-await finalization if `!HermesPerformance.isCurrent(panelTicket)`.

- [ ] **Step 1: Write failing tests.** Assert `HermesPerformance.begin('panel', nextPanel)`, `HermesPerformance.mark(panelTicket, 'usable')`, and `if (!HermesPerformance.isCurrent(panelTicket)) return false` occur in `switchPanel`.
- [ ] **Step 2: Verify red.** Run `./scripts/test.sh tests/test_panel_switch_generation.py -q`. Expected: FAIL because the guard is absent.
- [ ] **Step 3: Implement minimal code.** Create the ticket after `_currentPanel` and synchronous selected-panel classes are committed. Mark usable before lazy loading. After every awaited loader, return before later surface-mutating calls when the ticket is stale. Do not remove loaders' own generation guards.
- [ ] **Step 4: Verify green.** Run `./scripts/test.sh tests/test_panel_switch_generation.py tests/test_work_hub_panel.py tests/test_office_panel.py -q`. Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add static/panels.js tests/test_panel_switch_generation.py && git commit -m "perf: guard stale panel transitions"`.

### Task 3: Optimise the profile-switch interaction path and motion interruption

**Files:** Modify `static/panels.js`, `static/motion-ui.js`, `static/style.css`; create `tests/test_profile_switch_fast_path.py`, `tests/test_motion_budget.py`.

**Interfaces:** Use the existing `_profileSwitchGeneration` plus a Task 1 ticket. Produce `profile:usable` before noncritical catalog/quota refresh. Add `MotionUI.interrupt(name)` for named, superseded navigation/profile motion.

- [ ] **Step 1: Write failing tests.** Assert the usable mark occurs before `refreshModels`; assert interactive MotionUI transitions use `transform`/`opacity` and never animate `height`, `width`, `top`, `left`, or `margin`.
- [ ] **Step 2: Verify red.** Run `./scripts/test.sh tests/test_profile_switch_fast_path.py tests/test_motion_budget.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement minimal code.** Commit profile identity, composer defaults, title, and accessible state first; mark usable; schedule model/quota/inactive-panel refreshes in one generation-checked microtask. Cancel/restart only named navigation/profile transitions. Keep reduced-motion immediate and do not force layout to restart animations.
- [ ] **Step 4: Verify green.** Run `./scripts/test.sh tests/test_profile_switch_fast_path.py tests/test_motion_budget.py tests/test_issue803.py -q`. Expected: PASS, including multi-profile isolation.
- [ ] **Step 5: Commit.** Run `git add static/panels.js static/motion-ui.js static/style.css tests/test_profile_switch_fast_path.py tests/test_motion_budget.py && git commit -m "perf: prioritize profile interaction path"`.

### Task 4: Resolve, persist, and enforce minimal-tool policy

**Files:** Create `api/tool_policy.py`, `tests/test_tool_policy.py`, `tests/test_tool_policy_runtime_contract.py`; modify `api/models.py`, `api/routes.py`, `api/streaming.py`, `api/runtime_adapter.py`.

**Interfaces:** Implement `resolve_tool_policy(policy, explicit_toolsets, profile_toolsets, empty_means_restrictive) -> ResolvedToolPolicy`. `ResolvedToolPolicy` contains `requested`, `toolsets`, `enforced`, `reason`. Add nullable `Session.tool_policy`; `None` keeps historical behavior.

- [ ] **Step 1: Write failing resolver tests.** Cover: minimal returns `[]` and `enforced=True` only where `empty_means_restrictive=True`; minimal returns `enforced=False, reason='minimal_toolset_not_supported'` otherwise; explicit configured toolsets win; unknown toolsets raise `ValueError`; inherit preserves profile toolsets.
- [ ] **Step 2: Verify red.** Run `./scripts/test.sh tests/test_tool_policy.py -q`. Expected: FAIL because the resolver is absent.
- [ ] **Step 3: Implement minimal code.** Serialize `tool_policy` in every Session constructor, metadata load, new, duplicate, and branch path. Validate only `minimal`, `inherit-profile`, and `explicit`. Route every run through the resolver. Replace `if _override:` in `api/streaming.py` with `if _override is not None` so an intentionally empty list never falls back. Put resolved policy in `StartRunRequest.metadata` and pass its exact list to legacy/runner execution.
- [ ] **Step 4: Add the runtime semantic contract.** A fake executor records `enabled_toolsets`; the integration test must prove it receives `[]` for enforceable minimal. If the installed runtime treats `[]` as inheritance, endpoint responses must return the unavailable reason and must not broaden the set.
- [ ] **Step 5: Verify green.** Run `./scripts/test.sh tests/test_tool_policy.py tests/test_tool_policy_runtime_contract.py tests/test_issue803.py tests/test_session_active_profile_authorization.py -q`. Expected: PASS.
- [ ] **Step 6: Commit.** Run `git add api/tool_policy.py api/models.py api/routes.py api/streaming.py api/runtime_adapter.py tests/test_tool_policy.py tests/test_tool_policy_runtime_contract.py && git commit -m "feat: add enforceable minimal tool policy"`.

### Task 5: Expose the policy through the existing composer toolsets dropdown

**Files:** Modify `static/index.html`, `static/ui.js`, `static/style.css`, `api/routes.py`; create `tests/test_tool_policy_composer.py`.

**Interfaces:** Consume `session.tool_policy`, `enabled_toolsets`, and Task 4 response. Render `Minimal`, `Profile tools`, or explicit names. Show the unavailable reason rather than a false Minimal label.

- [ ] **Step 1: Write failing UI contract tests.** Assert `toolPolicy`, `minimal_toolset_not_supported`, and `Minimal` exist in the relevant client/template source.
- [ ] **Step 2: Verify red.** Run `./scripts/test.sh tests/test_tool_policy_composer.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement minimal code.** Extend—not duplicate—the current toolsets dropdown with Minimal and Inherit-profile actions. Retain explicit server selection. Persist through the existing session endpoint. Never turn an unavailable or empty inherited policy into a Minimal label.
- [ ] **Step 4: Verify green.** Run `./scripts/test.sh tests/test_tool_policy_composer.py tests/test_work_hub_panel.py -q && node --check static/ui.js`. Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add static/index.html static/ui.js static/style.css api/routes.py tests/test_tool_policy_composer.py && git commit -m "feat: expose minimal session tools"`.

### Task 6: Verify, document, and update the graph

**Files:** Modify `ARCHITECTURE.md`, `TESTING.md`, `docs/CONTRACTS.md`.

- [ ] **Step 1: Document exact ownership and verification.** Add the browser cache/generation owner, session-policy owner, Agent-runtime enforcement boundary, focused command `./scripts/test.sh tests/test_client_performance_primitives.py tests/test_panel_switch_generation.py tests/test_profile_switch_fast_path.py tests/test_motion_budget.py tests/test_tool_policy.py tests/test_tool_policy_runtime_contract.py tests/test_tool_policy_composer.py -q`, and manual rapid A→B→A plus two-profile checks.
- [ ] **Step 2: Run focused tests.** Run that focused command. Expected: PASS.
- [ ] **Step 3: Run the full suite.** Run `./scripts/test.sh`. Expected: PASS, or report every pre-existing failure by test name.
- [ ] **Step 4: Validate the final state.** Run `graphify update . && git diff --check`. Expected: graph refreshed and no whitespace errors.
- [ ] **Step 5: Commit.** Run `git add ARCHITECTURE.md TESTING.md docs/CONTRACTS.md && git commit -m "docs: describe performance and tool policy contracts"`.
