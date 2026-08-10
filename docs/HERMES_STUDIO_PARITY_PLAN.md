# Hermes-Studio parity plan

> Source comparison: [github.com/JPeetz/Hermes-Studio](https://github.com/JPeetz/Hermes-Studio)
> (React 19 + TanStack Start/Vite, 303 stars — reviewed via its
> `FEATURES-INVENTORY.md`, full repo file tree, and spot-checked source files
> including `patterns-corrections-screen.tsx`, `agent-library-screen.tsx`,
> `skills-screen.tsx`, `SECURITY.md`, `.github/workflows/security.yml`).
>
> Goal: move hermes-webui toward being more of an **agentic OS**, not just a
> chat client. This doc is the working list of what that requires, prioritized
> by what was already planned before this comparison (Agent Library, Security
> scanner, Patterns/memory vault cleaner) plus what the comparison surfaced as
> the bigger structural gap (multi-agent orchestration).

---

## Current status (as of 2026-08-10) — read this first if picking up cold

**Done, COMMITTED, and PUSHED — but to a fork, not upstream.** `origin`
(`nesquena/hermes-webui`) does not grant this GitHub account push access;
forked to `StephenZ06/hermes-webui` (remote name `fork`) and pushed
`feature/plan-canvas` there. **No PR opened yet** against
`nesquena/hermes-webui` — that's the next action if/when wanted:
`gh pr create --repo nesquena/hermes-webui --head StephenZ06:feature/plan-canvas`.
`git log --oneline 33a08de77..HEAD` to see the exact commit list;
`git status` should be clean on this branch.
- Priority 1, all four items: Personas (+ apply-to-session v1.1), Security
  scanner, Patterns/memory vault cleaner, and Audit Trail UI (technically
  Priority 3, shipped alongside these — see its own section below).
- Priority 2, Phases 1, 1.2, 2, **and 3** of Multi-agent orchestration
  ("Crews"): crew templates + bulk dispatch (plus its dispatch-variables-
  dialog follow-up), office-view crew grouping, a scoped-down "templates
  gallery" slice (search/filter + last-dispatched recency sort), and a
  labeled-approximation cost estimate (option 2 of the three originally
  proposed — see Phase 3's section for the full "why option 2, not 1 or 3"
  reasoning). **All of Priority 2 that was ever going to get a conservative
  slice is now shipped** — the only remaining unstarted piece
  (workflow-builder/step-graph engine) stays deliberately out of scope, see
  "Investigated and rejected" in that section.
- Priority 3, all items: **Knowledge Browser**, **Analytics/cost
  dashboard**, **Command palette**, **Chat export**, **Sound notification
  system** (three new chime kinds layered onto the pre-existing chime
  mechanism), and **Onboarding tour** (new guided walkthrough — the wizard
  alone was confirmed not to be one). **Voice input** was investigated and
  found **already fully covered** by existing dictation code — nothing was
  built for it; see its own "already covered, don't rebuild" note below.
  **All of Priority 3 is done.**

Verified 2026-08-10: full suite green after Phase 3 landed (Crews cost
estimate: 9 new unit tests in `tests/test_crew_cost_estimate.py` + 6 new
structural guards in `tests/test_crews_ui.py`, full locale-parity suite
re-run clean). Prior full-suite baseline (before Phase 3): 14,162 passed,
94 skipped, 0 failures (the only 2 deselected tests are a pre-existing,
unrelated TLS health-probe flake in the sandbox,
`tests/test_tls_aware_probe.py`, not touched by any of this work).

**Session closed out 2026-08-10 — marked done, not picking this back up
automatically.** Explicitly declined, not forgotten: opening a PR against
`nesquena/hermes-webui` (branch is pushed and ready — `gh pr create
--repo nesquena/hermes-webui --head StephenZ06:feature/plan-canvas` —
whenever a human decides to) and starting Priority 4 (Skills marketplace
discovery). Both were offered and both were turned down for *this*
session; treat this doc's roadmap as accurate but not something to
auto-continue without being asked again.

**Immediate next steps (housekeeping):**
1. ~~Push `feature/plan-canvas`~~ — **done 2026-08-10**, to the fork (see
   above). Opening the actual PR against `nesquena/hermes-webui` is still
   pending — a deliberate choice not to do it silently, since that's a
   visible action against someone else's repo.
2. ~~Clean up 5 leftover agent worktrees~~ — **done 2026-08-10.** All 5
   (`agent-a4a717bf7ccd9a8dc`, `agent-aeae197db12d71563`,
   `agent-a77e78b142872ce8b`, `agent-ade7eb7fdf6e354ed`,
   `agent-a495f4b400fa37119`) and their branches were removed after their
   commits were confirmed cherry-picked. Note: a 6th worktree
   (`agent-a5aa110d9780cb643`) exists under `.claude/worktrees/` but
   belongs to a **separate, unrelated peer session** on this machine — it
   was deliberately left untouched and should stay that way; it is not
   part of this parity-plan work.

**How this landed (context if continuing the parallel-agent approach
again):** shipped via 5 parallel subagents in isolated git worktrees, then
manually reconciled one at a time back onto this branch. Two real snags
worth knowing about before repeating this pattern:
- Worktree agents branch from committed history only — they do **not** see
  a repo's uncommitted working-tree changes. One agent was given a task
  ("build the Crews dispatch-variables UI") that had *already been done* in
  the uncommitted tree at the time — the coordinating session mis-read a
  truncated `git diff | head -N` and thought the gap was still open. That
  agent's entire run was wasted (it silently re-derived already-existing
  code). **Lesson: read a diff to completion, or grep for a "Shipped"/
  "Resolved" follow-up paragraph, before trusting that a truncated diff
  shows an open gap.**
- One agent hung after kicking off its own background test run and never
  receiving that run's completion notification — it sat idle for over an
  hour with no progress. Caught by noticing `ListAgents` had gone from
  "running" to unreachable; its work was ~95% done and solid in its
  worktree, so it was finished and merged manually rather than re-run.
  **Lesson: if a background agent goes quiet for a long time, check
  `ListAgents` and inspect its worktree directly rather than assuming it's
  still making progress.**
- Merging worktree branches back is not a plain `git merge` — commit a
  checkpoint of the real uncommitted baseline first, then cherry-pick each
  agent's isolated new-work commit onto it one at a time, running tests
  after each. Conflicts were almost entirely in `docs/
  HERMES_STUDIO_PARITY_PLAN.md` (multiple agents editing the same "Current
  status" preamble and appending sections near the same insertion point)
  and `static/i18n.js` (multiple agents adding new locale keys to the same
  15 per-locale blocks) — both resolved as pure keep-both-sides additions,
  no real semantic conflicts, but git couldn't auto-merge them without
  guidance.

**No longer deferred:** Priority 2 Phase 3 (cost panel) shipped 2026-08-10
as a labeled approximation (option 2) — see its section for the full
decision record, including the still-open question of migrating to a real
upstream fix (option 1) later.

**Not started, no written plan yet:** the workflow-builder/step-graph-editor
part of Priority 2 remains explicitly out of scope (see "Investigated and
rejected" below — unchanged); all of Priority 4 (Skills marketplace
discovery is flagged as the natural next pick — it's the gate the Security
scanner was explicitly built for).

**Suggested next pick:** Priority 4's Skills marketplace discovery — every
Priority 1/2/3 item that had a real, scoped gap is now shipped; the
workflow-builder/step-graph part of Priority 2 stays explicitly out of
scope (revisit only if a genuinely new, concrete gap surfaces, not "build
the gallery bigger just because"). Before starting *anything*, read the
"Shipped" notes for whichever area you're touching — they carry the actual
design reasoning (why a decision was made a certain way), not just what
shipped.

---

## Priority 1 — already planned, confirmed as real gaps

### Personas (internal name: Agent Library / `agent_definitions`) — STATUS: DONE (shipped 2026-08-08)

**Decided 2026-08-08:** user-facing name is **"Personas"** (resolves open
question #1 below — avoids collision with this codebase's existing use of
"agent" for the running Hermes process). Internal module/route/data names
stay `agent_definitions`/`/api/agent-definitions` as already planned; only
UI-visible strings (nav label, panel title, slash command, i18n keys) say
"Personas". **v1 ships with no apply-to-session** (resolves open question
#2 below) — pure browsable/editable library, no `streaming.py` chokepoint
changes.

**Shipped 2026-08-08:** full CRUD implementation landed exactly per the plan
below — `api/agent_definitions.py`, four `/api/agent-definitions/*`
endpoints in `api/routes.py`, a Personas nav tab + sidebar list + detail/form
pane in `static/index.html`/`panels.js`/`style.css`, a `/personas` slash
command in `static/commands.js`, and 29 new i18n keys across all 15 locale
blocks in `static/i18n.js`. Tests: `tests/test_agent_definitions_api.py` (18
cases — CRUD, builtin protection, duplicate, caps, profile isolation) and
`tests/test_agent_definitions_ui.py` (7 structural wiring guards). Full
verification run: 339 tests across the i18n/locale suite, panel-navigation
suite, saved-prompts/projects suite, and the new test files — all passing,
zero regressions. `ruff check` clean on the new/touched Python.
**Apply-to-session shipped 2026-08-08 (v1.1):** a persisted
`Session.agent_definition_id` field (mirrors `Session.personality`) plus a
new `POST /api/agent-definitions/apply` endpoint (mirrors
`/api/personality/set`: `{session_id, id}`, empty `id` clears, 404 on
unknown session/persona, subagent-view-only guard, `_get_session_agent_lock`
+ `s.save()`). Resolution extends the existing `_webui_ephemeral_system_prompt()`
chokepoint exactly as planned below — no parallel prompt-injection path:
`api/streaming.py`'s direct chat path and `api/gateway_chat.py`'s
gateway-routed path both resolve the applied persona's `system_prompt` and
combine it with any config.yaml personality (persona text first) before
building the ephemeral prompt. UI: an Apply/Clear button pair in the
Persona detail-pane header (shown based on whether the open persona matches
the active session's `agent_definition_id`), plus an "Applied to this
session" badge row. Slash command: `/personas apply <name-or-id>` and
`/personas clear` (the read-only `/personas` list keeps its v1 behavior).
Tests: 7 new API round-trip cases in `tests/test_agent_definitions_api.py`
(builtin/custom apply, persistence via `GET /api/session`, clear, 404s,
missing `session_id`) and 3 new structural guards in
`tests/test_agent_definitions_ui.py` (button wiring, visibility logic,
chokepoint wiring) — 34/34 passing, no regressions in the original 27.

Hermes-Studio (`src/screens/agents/agent-library-screen.tsx`,
`src/lib/agents-api.ts`, `src/server/agent-definitions-store.ts`) has a full
CRUD gallery of named agent personas: emoji + color icon, role label, tags,
editable system prompt, built-in-vs-custom flag, duplicate/edit/delete.

hermes-webui has **no** agent-definition/roster concept anywhere in `api/` or
`static/` today.

A full implementation plan was designed against hermes-webui's *actual*
architecture (Python + vanilla JS, no frameworks — this is NOT a port of
Hermes-Studio's React/TanStack implementation). Read `AGENTS.md` and
`docs/GUIDELINES.md` before touching any of this.

#### Storage decision
New file `api/agent_definitions.py`, modeled on `api/routes.py`'s existing
`_saved_prompts_path()/_load_saved_prompts()/_save_saved_prompts()` pattern
(~line 11951), **not** on `api/kanban_bridge.py` (wrong owner — that
delegates to `hermes_cli`, which has no `agent_definitions` concept) or
`api/goals.py` (wrong shape — that's per-session ephemeral `state.db` meta,
not a named user-owned collection). Storage path:

```
{profile_home}/webui/agent_definitions.json
```

This makes definitions automatically profile-scoped for free via the
existing profile-switch cookie/thread-local mechanism — no `profile` field
or `_profiles_match()` ownership-check machinery needed (unlike
`projects.json`, which needs that complexity because projects are
denormalized onto `session.project_id` across profiles; agent definitions
have no cross-profile reference).

Use `webui_session_db.py`'s atomic tmp-file + `os.replace` + fsync write
helper (not the simpler `saved_prompts.json` write) since this file holds
larger free-text `system_prompt` blobs where a torn write matters more.

#### Built-in vs custom
Ship built-ins as an in-memory Python constant, `BUILTIN_DEFINITIONS`
(fixed ids like `"builtin:default"`), merged with the user's JSON file at
read time and **never written into it** — avoids a seed-file that drifts
from repo updates. Mutation endpoints reject edit/delete on `builtin:` ids
(400); duplicate works on builtins too and always produces a new custom row.

#### Data shape
```json
{
  "id": "a1b2c3d4e5f6",
  "name": "Code Reviewer",
  "emoji": "🔍",
  "color": "#7cb9ff",
  "role": "Reviews diffs for bugs and style issues",
  "tags": ["review", "quality"],
  "system_prompt": "You are a meticulous code reviewer...",
  "builtin": false,
  "created_at": 1754656800.0,
  "updated_at": 1754656800.0
}
```
Caps (mirroring `/api/prompts`'s existing cap pattern): `name` ≤128 chars,
`role` ≤256, `system_prompt` ≤8000 (matches saved-prompt cap), `tags` ≤10
items × ≤32 chars each, `emoji` ≤8 chars (opaque, not grapheme-validated),
≤100 custom definitions per profile. Color validated against
`^#[0-9a-fA-F]{3,8}$` (same regex `/api/projects/create` already uses).

#### API endpoints (`api/routes.py`, next to the `/api/projects`/`/api/prompts` blocks)
- `GET /api/agent-definitions` → `{"definitions": [...], "builtin_count": N}`
- `POST /api/agent-definitions/create` → body `{name, emoji?, color?, role?, tags?, system_prompt}` → `{"ok": true, "definition": {...}}`
- `POST /api/agent-definitions/update` → body `{id, ...fields}` → `{"ok": true, "definition": {...}}`; 404 if missing, 400 `"Built-in agent definitions cannot be edited"` if builtin
- `POST /api/agent-definitions/delete` → body `{id}` → `{"ok": true}`; 404 if missing, 400 if builtin
- `POST /api/agent-definitions/duplicate` → body `{id}` → `{"ok": true, "definition": {...}}`; source may be builtin or custom, result always `builtin: false`, name gets `" (copy)"` suffix (matches `/api/session/duplicate`'s convention)

#### Frontend hook-in
- `static/index.html`: new nav tab (`data-panel="agents"` internally,
  label text **"Personas"**, rail + mobile sidebar-nav, inline `<svg>` icon)
  next to the `skills` tab; new `<div class="panel-view" id="panelAgents">`
  with search box `#agentsSearch`, list `#agentsList`, detail pane
  `#agentDefDetailTitle/Body/Empty` — same skeleton as the skill-detail
  block (~line 785-797).
- `static/panels.js`: add `'agents'` to `MAIN_VIEW_PANELS` (line 47) and
  `APP_TITLEBAR_KEYS`; add `loadAgentDefinitions`, `renderAgentDefinitions`,
  `filterAgentDefinitions`, `openAgentDefDetail`/`_renderAgentDefDetail`,
  `openAgentDefCreate`/`editCurrentAgentDef`/`_renderAgentDefForm`,
  `saveAgentDefForm`, `duplicateAgentDef`, `deleteAgentDef` (via
  `showConfirmDialog`), `_setAgentDefHeaderButtons` — directly parallel to
  the existing skills/profiles panel functions.
- `static/commands.js`: add `personas` slash command (mirrors `skills`),
  listing definitions in chat. **No apply-to-session command in v1 —
  decided, no longer open** (was open question #2).
- `static/i18n.js`: add every new key to **all 15 locale blocks**
  (`en, it, ja, ru, es, de, zh, zh-Hant, pt, ko, fr, cs, tr, pl, vi`), not
  just `en`. Locale key-parity is a strict, test-enforced contract
  (`tests/test_chinese_locale.py` and others) — adding only to `en` fails
  existing tests.
- Sidebar colors: reuse the existing fixed 8-hex `PROJECT_COLORS` swatch
  palette (`static/sessions.js:9071`) rather than building a color picker —
  no color-picker widget exists anywhere in this codebase.

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)
1. HTTP round-trip (`tests/test_agent_definitions_api.py`, shape from
   `tests/test_sprint15.py`): create → appears in list; update/delete reject
   builtin ids (400); delete removes a custom row; duplicate of builtin or
   custom produces new `builtin:false` row with `" (copy)"` suffix and
   independently-copied `tags` list; create requires `name`; caps enforced.
2. Profile isolation: two profiles never see each other's definitions.
3. Static UI-wiring guards (`tests/test_agent_definitions_ui.py`, shape from
   `tests/test_issue3571_saved_prompts.py`): nav tab + panel container
   present, JS functions wired, caps present in source.
4. Locale-parity: new keys present in all 15 locale blocks (reuse
   `test_chinese_locale.py`'s key-diff helper pattern).

#### Open questions — RESOLVED 2026-08-08
1. **Naming collision** — resolved: user-facing name is **"Personas"**.
   Internal module/route/data names stay `agent_definitions`/
   `/api/agent-definitions` (no collision risk there since those aren't
   user-visible).
2. **Relationship to `config.yaml`'s `agent.personalities`** — resolved:
   v1 shipped with no apply-to-session; **apply-to-session shipped
   2026-08-08 (v1.1)**, see "Shipped" note above. A Persona and a
   config.yaml personality can both be applied to the same session at once
   — the ephemeral prompt concatenates persona text then personality text,
   it does not force a choice between the two mechanisms.
3. Storage/built-ins decisions above are made, not open — flagged only so a
   future "view across all profiles" or "hide a builtin per-profile"
   feature request doesn't get surprised by the current design's limits.

#### Critical files
- `api/agent_definitions.py` (new)
- `api/routes.py`
- `static/panels.js`
- `static/index.html`
- `static/i18n.js`

### Security scanner — STATUS: DONE (shipped 2026-08-10, scan-only scope)
Hermes-Studio (`skills-screen.tsx` `SecurityScanCard`, `SecurityRisk` type:
`level: safe|low|medium|high`, `flags[]`, `score`) statically scans every
marketplace skill for risky patterns before install and shows a risk card.

hermes-webui's `skill_usage.py` only reads `.usage.json` for display stats —
no scanning, no risk level, no flags.

Ties directly into the **Skills marketplace gap** below — the scanner is the
natural gate on top of a marketplace browse/install flow hermes-webui doesn't
have yet either.

**Shipped 2026-08-10:** deliberately scan-only for already-installed skills —
no marketplace browse/install path (that's still the open gap above). Rather
than writing a second scanner, `api/skills_hub_bridge.py` (new) imports
hermes-agent's existing in-process scanner (`tools/skills_guard.py`, the same
way `api/routes.py` already imports `tools.skills_tool`/`agent.skill_utils`
since the agent source tree is mounted read-only into this container) and its
install-provenance ledger (`tools/skills_hub.py`'s `HubLockFile`, for a
best-effort trust-level lookup that falls back to the conservative
`"community"` default when a skill has no hub-install record). Feature-detects
`scan_skill_cached()` and falls back to the always-available `scan_skill()` so
it doesn't hard-pin to a newer agent-source API that a given deployment's
mounted tree might predate. New `GET /api/skills/scan?name=` endpoint in
`api/routes.py`, returns 404 for an unknown skill and a clear 501 (not a
crash) when the agent source tree isn't mounted. UI: a security-scan card in
the skill detail pane (`static/panels.js`'s `_loadSkillScan`/
`_renderSkillScan`, re-triggered from every code path that repaints the
detail pane) with verdict badges (safe/caution/dangerous) and a trust-level
label, themed via CSS variables (no hardcoded colors), plus 9 new i18n keys
across all 15 locales. Tests: `tests/test_skills_security_scan.py` (7 cases —
bridge module shape, route wiring/defensiveness, frontend wiring, CSS tokens,
locale-key parity, verdict-badge classes, and one behavioral round-trip
against the real scanner, skipped when hermes-agent isn't importable) — all
passing.

### Patterns / memory vault cleaner — STATUS: DONE (shipped 2026-08-10)
Hermes-Studio's "Patterns & Corrections" screen (`src/routes/patterns.tsx` →
`patterns-corrections-screen.tsx`) reads `§`-delimited entries from
`~/.hermes/memories/MEMORY.md`, splits into two tabs (Patterns vs.
`CORRECTION:`-prefixed entries), and lets you expand/delete entries and
append new corrections via a form, writing back through `POST
/api/memory/write`.

Alongside it, a broader **Memory Browser**
(`memory-browser-screen.tsx` + `MemoryFileList`/`MemorySearch`/
`MemoryEditor`/`MemoryPreview`) does general browse/search/edit of everything
under `~/.hermes/`, not just MEMORY.md.

hermes-webui has no memory-curation UI at all — memory is currently opaque to
the user.

**Shipped 2026-08-10:** per-entry delete/append layered on top of the
existing whole-file view/edit (`editCurrentMemory()`/`/api/memory/write`
stay reachable, unchanged), scoped strictly to the `'memory'` section — other
sections still use the generic whole-file renderer. Confirmed against real
profile data (not assumed) that `MEMORY.md` entries are delimited by
`\n§\n` with no leading/trailing delimiter; `_split_memory_entries()`/
`_join_memory_entries()` in `api/routes.py` round-trip on that exact pattern.
Two new endpoints: `POST /api/memory/entry/delete` (`{section, index}` —
addresses the entry by server-side index into the **raw** file, never takes
`content` from the request body) and `POST /api/memory/entry/append`
(`{section, content}` — appends fresh user-typed text, never a
client-reconstructed full file). This split matters because `GET /api/memory`
redacts secret-shaped text before sending it to the client (real profiles
have plaintext credentials in `MEMORY.md`); taking a whole-file payload back
from the client on delete would risk permanently burning a real secret to
`"[REDACTED]"` on disk. `_resolve_memory_entry_target()` also guards against
a symlinked target. UI: a two-tab entries view (Patterns / Corrections, by
`/^CORRECTION:/i` prefix — matched identically on backend and frontend) in
`static/panels.js`, add-entry form, delete-with-confirm, themed via CSS
variables, 11 new i18n keys across all 15 locales. Tests:
`tests/test_memory_entries.py` (11 cases, including a regression guard for a
tab that silently reverted to "Patterns" on its own click when corrections
were empty, caught via a live Playwright check) — all passing.

---

## Priority 2 — the bigger structural gap for "agentic OS"

### Multi-agent orchestration ("Crews" + "Conductor")
`src/routes/crews/`, `src/screens/crews/` (workflow-builder, templates
gallery, dispatch dialog, cost panel) and `src/screens/conductor/`
(office-view, mission-event-log, cost-tracker) let Hermes-Studio dispatch and
visually track several agents working in parallel — a "mission control" view
rather than a flat session list.

hermes-webui currently drives **one agent per session** with no
dispatch/coordination concept. Zero hits for `crew|conductor|multi-agent|
orchestrat` anywhere in the codebase.

**Design idea worth stealing specifically:** the Conductor's office-view —
each spawned agent shown as a visible "worker" with a status strip, live cost
tracker, and mission event log, instead of a plain list. This spatial/visual
metaphor is what makes their multi-agent view legible; worth adopting the
metaphor even if the implementation differs.

This is probably the single highest-leverage item if "agentic OS" is the
actual target, bigger in scope than the three Priority 1 items.

**Kanban office-view shipped 2026-08-10 — first slice only, not the full
gap.** Added an office-view toggle (`#btnKanbanOfficeView`, next to the
existing view-toggle/preview-dispatcher buttons) to the existing Kanban board
that renders running, dispatch-backed tasks as worker cards (status strip +
expandable live log, reusing the existing `/api/kanban/tasks/:id/log`
endpoint, cached per task to avoid flicker on routine poll/SSE re-renders)
instead of Kanban's flat column view. Scope is deliberately narrow and
pinned in-code, not just here: this visualizes **Kanban-dispatched workers
only** (`task.worker_pid`, set by `hermes_cli.kanban_db.dispatch_once`,
which runs in-process inside hermes-webui's own container). It does **not**
attempt live `delegate_task`/subagent status — that registry
(`tools/delegate_tool.py`'s `_active_subagents`) lives inside the separate
`hermes` container's process memory (a pre-built image, not the locally
mounted `hermes-agent-src`), so there is no reachable endpoint for it today.
No new backend endpoints — pure frontend, `static/panels.js`'s
`_kanbanRenderOfficeView()` hooks into the same `_kanbanRenderBoard()` call
site every existing refresh path already drives, so it can't drift out of
sync with the normal board. Themed via CSS variables, 4 new i18n keys across
all 15 locales. Tests: `tests/test_kanban_office_view.py` (11 cases,
including one that pins the scope decision as a source comment so a future
contributor doesn't "fix" this by trying to reach the cross-container
registry) — all passing.

**Already covered, don't rebuild:** Hermes-Studio's "mission-event-log" is
already present — `task_events` + `GET /api/kanban/events` +
`GET /api/kanban/events/stream` (`api/kanban_bridge.py:528-558`,
`:969-1145`) is a live per-task event log with SSE push. Any Crews UI should
consume this existing stream, not invent a second event log.

**What "dispatching multiple agents in parallel" means in this codebase,
concretely:** it is an **extension of Kanban's existing dispatch**
(`hermes_cli.kanban_db.dispatch_once`/`_default_spawn`), not a new
session-spawning mechanism. `dispatch_once` already spawns one
`hermes -p <assignee> chat -q ...` subprocess per claimed `ready` task, and
several tasks with distinct `assignee` values already run truly
concurrently today (bounded by `max_spawn`). What's missing is (a) a way to
author several related tasks in one action instead of the single-task
create modal N times, and (b) a way to see and (eventually) cost-account
those tasks as a named group afterward. Both are additive layers on top of
existing Kanban primitives — no new dispatch engine, no new process model.
Investigated and rejected: `hermes_cli.kanban_db.Task`'s
`workflow_template_id`/`current_step_key` columns exist in the schema
(`hermes_cli/kanban_db.py:807-808`, plumbed through `list_tasks` and the
CLI's `--workflow-template-id` filter) but nothing upstream populates
them — there is no step-graph execution engine behind `current_step_key` to
build a "workflow builder" against. Building that state machine from
scratch is out of scope here; the columns are reused below only as an
unused, already-plumbed *tagging* mechanism, not as evidence a workflow
engine exists.

**Why this is a Kanban-panel extension, not a new top-level nav tab:**
Kanban already owns "what's running" (poll/SSE-synced task state, the
dispatcher, the office view). A separate "Crews" nav tab would read the
same `task_events`/board state through a second, independently-synced UI —
doubling the poll/SSE wiring surface for zero new data. Crews should be
additive UI *inside* the Kanban panel (a new toolbar button + modal, plus
an office-view grouping upgrade), mirroring how the office-view toggle
itself shipped as an additive button inside Kanban rather than a new tab.

**Why a crew is tagged via `workflow_template_id`/`current_step_key`, not
`tenant` or a new board:** `tenant` is a real, user-visible taxonomy field
already used for the dispatcher's `HERMES_TENANT` env var and a board's
`default_tenant` config (`kanban_bridge.py:197-256`, `:582`) — repurposing
it as an internal crew-run id risks colliding with a deployment's actual
multi-tenant usage of that field. A new board (`_create_board_payload`) is
too heavy: boards are a global, cross-client active-pointer resource shared
with the CLI/gateway/dashboard, not a lightweight per-dispatch grouping.
`workflow_template_id`/`current_step_key` are unused schema columns that
already mean almost exactly "which template spawned this task, and which
run of it" — using them costs no new migration, and gets CLI (`kanban list
--workflow-template-id`) and the separate agent-dashboard plugin
compatibility for free, since both already understand these fields.

**Naming — resolved:** ships as **"Crews"** (matches the Hermes-Studio
parity goal and signals the strategic direction — future phases growing
toward real coordination — the same way "Personas" was chosen as the
approachable name over the more literal "Agent definitions"). v1's actual
feature (bulk-dispatch a named template of tagged tasks) is intentionally
more modest than the name's ambition; that gap is expected to close in
later phases, not a naming mismatch to fix now.

#### Phase 1 (v1) — Crew templates + bulk dispatch — STATUS: DONE (shipped 2026-08-10)

**Shipped 2026-08-10:** landed exactly per the plan below, with two small
deviations noted here. `api/crews.py` (profile-scoped `crew_templates.json`,
same `_atomic_write` tmp-file+fsync+`os.replace` pattern and uuid4-hex12 ids
as `api/agent_definitions.py`, no built-in/custom split needed since every
crew is user-owned); five `/api/crews*` endpoints in `api/routes.py` next to
the `/api/agent-definitions` block (`GET /api/crews`,
`POST /api/crews/{create,update,delete,duplicate}`,
`POST /api/crews/<id>/dispatch`); `_create_task_payload` in
`api/kanban_bridge.py` extended with the `inspect.signature(kb.create_task)`
feature-detect described below, falling back to the raw `UPDATE tasks SET
workflow_template_id = ?, current_step_key = ? WHERE id = ?`; `_board_payload`
extended with `?workflow_template_id=` (forwarded straight into `kb.list_tasks`
— that call already accepts the kwarg upstream, so no feature-detect was
needed on the read side, only on the `create_task` write side). Frontend:
`#btnKanbanCrews` toolbar button next to `#btnKanbanOfficeView`, a crew-list
modal and a create/edit modal (dynamic add/remove task-spec rows, each row's
assignee `<select>` populated via `_kanbanPopulateAssigneeSelect()` extended
with an optional target-element parameter rather than a parallel profile-fetch
copy), dispatch gated behind `showConfirmDialog` matching
`runKanbanDispatcher`'s cost-consuming-action pattern, and a
`kanbanWorkflowTemplateFilter` module variable (same UX slot as the existing
tenant/assignee filters, set by a successful dispatch) so the board scopes to
the just-created tasks. `/crews` slash command (list-only, per the plan's
explicit v1 scope cut). 36 new i18n keys across all 15 locale blocks.

Two deviations from the plan text: (1) the installed `hermes_cli.kanban_db`
in this dev/CI environment does **not** expose `workflow_template_id`/
`current_step_key` as `create_task` kwargs (verified against both the
mounted `hermes-agent-src` tree and the `~/.hermes/hermes-agent` checkout the
test harness runs against) — so only the raw-`UPDATE` fallback path has been
exercised against a real `hermes_cli` build; the kwarg path is exercised only
against a synthetic stub in `tests/test_crews_api.py` that deliberately
implements the newer signature, to prove the feature-detect takes that branch
when it becomes available upstream. (2) `/crews dispatch <name>` was cut from
v1 as the plan explicitly allowed ("optional, can slip to v1.1") to keep the
slash command additive-and-tight; dispatch is confirm-gated in the Crews
modal only.

**Known gap, not caught until implementation — flagging rather than silently
shipping:** the dispatch confirm flow always dispatches with `variables: {}`.
There is no UI step to collect per-dispatch variable values, so a template
whose task specs contain `{topic}`-style placeholders can only be usefully
dispatched with real substitutions via a direct API call today, not from the
Crews modal. The backend (`dispatch_crew`'s `variables` param,
`_substitute_variables`) fully supports it end-to-end; only the frontend
prompt step is missing. Left for a human to decide whether it belongs in a
v1.1 UI pass or is acceptable as-is for templates that don't use variables.

**Follow-up shipped 2026-08-10:** closed the gap above. Confirmed first
(reading `_substitute_variables`/`dispatch_crew`) that an unfilled `{name}`
placeholder raises `KeyError`, caught by `dispatch_crew`'s `except Exception`
and surfaced as that one task spec's `{ok: false, error: ...}` without
aborting sibling specs — not a silent literal-`{name}` leak. `dispatchKanbanCrew()`
now scans every task spec's title/body for `{variable}` placeholders
(`_kanbanCrewTemplateVariables()`, a simple regex mirroring the backend's own
"no templating engine" scope) after the existing dispatch confirm and before
the `/dispatch` call; zero placeholders dispatches immediately exactly as
before (explicit `variables: {}`, no behavior change); one or more distinct
names opens a new `kanbanCrewDispatchVarsModal` (same `.kanban-modal-overlay`
shell as the other Kanban modals, one text input per distinct variable name,
required-field validation) and only dispatches with the collected
`{name: value}` map after confirm; cancelling never reaches the dispatch
call. 5 new i18n keys across all 15 locale blocks.

Tests: `tests/test_crews_api.py` (27 cases — CRUD round-trip, caps, profile
isolation via direct function calls, and dispatch behavior via a fake
`hermes_cli.kanban_db` module injected into `sys.modules` mirroring
`tests/test_kanban_bridge.py`'s existing pattern: shared
`workflow_template_id`/`current_step_key` across a dispatch run, `{variable}`
substitution, a missing-variable per-item failure that doesn't abort sibling
tasks, one-bad-assignee partial failure, `board` param forwarding, the
create_task-kwarg-feature-detection fallback, and a behavioral regression
proving dispatch never calls `dispatch_once`) and `tests/test_crews_ui.py`
(19 cases — toolbar button placement, modal wiring, CSS theme-token guard,
locale-key parity, a source-level regression pinning that neither the
frontend `dispatchKanbanCrew()` nor the backend `/api/crews/*/dispatch`
route ever call `dispatch_once(` or hit `/api/kanban/dispatch`, and the 5
cases added for the variable-collection dialog follow-up: real node
execution of `_kanbanCrewTemplateVariables()` against title-only/body-only/
both/none/duplicate-across-specs inputs — not just a source-string proxy —
plus structural checks that zero-placeholder crews skip the dialog, that the
cancel path never reaches the dispatch call, the new modal markup, and the
new functions). Verified the new tests fail without the implementation
(reverting `api/crews.py` alone drops 27 of 41 from pass to fail; reverting
`static/panels.js`/`static/index.html`/`static/i18n.js` to the pre-follow-up
state drops all 6 new/updated Crews-UI cases from pass to fail). Full
verification run: all 46 Crews tests, the complete locale-parity suite (all
per-locale test files plus `test_issue3539_language_dropdown_all_locales.py`,
117 cases), the full
`test_kanban_bridge.py`/`test_kanban_office_view.py`/`test_kanban_ui_static.py`/
`test_kanban_view_toggle.py` suites, `test_agent_definitions_api.py`/
`test_agent_definitions_ui.py`, and a ~700-test sweep of slash-command/UI
structural tests — all passing, zero regressions. `ruff check` clean on
`api/crews.py` and both new test files; the only findings in the touched
`api/kanban_bridge.py`/`api/routes.py` are pre-existing issues outside the
diff (confirmed by line number against the pre-change file). `node -c` clean
on `static/panels.js` and `static/i18n.js` after the follow-up.

**Storage decision.** New file `api/crews.py`, modeled directly on
`api/agent_definitions.py`'s `_agent_definitions_path()`/`_atomic_write()`
pattern (same profile-scoped-for-free reasoning as Personas — no `profile`
field needed):

```
{profile_home}/webui/crew_templates.json
```

A crew template is a small, named, ordered list of task specs — a
"bulk-create N tagged tasks" primitive, not a step-graph engine (there is
nothing upstream to execute a graph against — see above). No dependency/
parent links between a template's own task specs in v1; all specs in a
template dispatch as siblings (`parents=()`), matching what `dispatch_once`
can actually run in parallel today. Cap at 50 templates/profile, 20
task-specs/template (mirrors Personas' `MAX_CUSTOM_DEFINITIONS` cap
pattern).

**Data shape:**
```json
{
  "id": "a1b2c3d4e5f6",
  "name": "Research crew",
  "icon": "🔬",
  "color": "#7cb9ff",
  "description": "Fan out a topic across three research angles",
  "tasks": [
    {"title": "Research: {topic} — market angle", "body": "", "assignee": "researcher-a", "skills": ["web"], "priority": 0},
    {"title": "Research: {topic} — technical angle", "body": "", "assignee": "researcher-b", "skills": ["web"], "priority": 0}
  ],
  "created_at": 1754656800.0,
  "updated_at": 1754656800.0
}
```
`{topic}`-style substitution is a single flat `str.format`-style pass over
a user-supplied `variables` dict at dispatch time — no templating engine,
no conditionals. Caps mirror Personas: `name` ≤128, `description` ≤512,
per-task `title` ≤200, `body` ≤4000 (kanban task body already has no hard
cap upstream, but bound it here the way saved prompts are bounded),
`skills` ≤10×≤32 chars.

**API endpoints** (`api/routes.py`, next to the `/api/kanban`/
`/api/agent-definitions` blocks; module imported lazily inside the
handler, same as `skills_hub_bridge`/`audit_trail`):
- `GET /api/crews` → `{"crews": [...]}`
- `POST /api/crews/create` → body `{name, icon?, color?, description?, tasks:[...]}`
- `POST /api/crews/update` → body `{id, ...fields}` → 404 if missing
- `POST /api/crews/delete` → body `{id}` → 404 if missing
- `POST /api/crews/duplicate` → body `{id}` → `" (copy)"` suffix (matches Personas/session-duplicate convention)
- `POST /api/crews/<id>/dispatch` → body `{variables?: {...}, board?}`. For
  each task spec: substitute `variables`, then call
  `api.kanban_bridge._create_task_payload` directly, reusing that
  function's validation (title-required, priority-int, status handling)
  rather than duplicating it. Extend `_create_task_payload`'s body handling
  to accept optional `workflow_template_id`/`current_step_key` and forward
  them into `kb.create_task(...)` if the installed `hermes_cli` version's
  `create_task` signature accepts those kwargs (`inspect.signature`
  feature-detect, same precedent as `skills_hub_bridge.py`'s
  `hasattr(skills_guard, "scan_skill_cached")` check); otherwise fall back
  to a raw `UPDATE tasks SET workflow_template_id=?, current_step_key=?
  WHERE id=?` immediately after creation, inside the same `_conn(board=
  ...)` — mirroring `_patch_task`'s existing precedent for writing fields
  the structured API doesn't expose (`api/kanban_bridge.py:390-400`).
  `workflow_template_id` = the crew template's id; `current_step_key` = an
  opaque per-dispatch run tag (ISO timestamp). Partial-success contract
  like `_bulk_tasks_payload` (`api/kanban_bridge.py:678-713`): per-spec
  `{ok, task_id|error}`, one bad assignee doesn't abort the rest. Response:
  `{"ok": true, "run_id": "<current_step_key>", "results": [...]}`. Does
  **not** auto-call `dispatch_once` — matches the existing
  `runKanbanDispatcher`'s explicit-confirm, cost-consuming-action pattern
  (`static/panels.js:2983-3014`); the user still clicks Run Dispatcher.
- `_board_payload` extended to accept `?workflow_template_id=` (forwarded
  into `kb.list_tasks`, mirrors the existing `?tenant=`/`?assignee=`
  handling at `api/kanban_bridge.py:193-256`) so the board/office view can
  filter to one crew's tasks.

**Frontend hook-in** (`static/panels.js`, `static/index.html` — no new nav
tab, no new entry in `MAIN_VIEW_PANELS`):
- New toolbar button `#btnKanbanCrews` next to `#btnKanbanOfficeView` (same
  header row, same `.kanban-modal-overlay` shell as
  `openKanbanCreateBoard()`/`openKanbanCreate()`) opening a crew list +
  create/edit form (dynamic add/remove task-spec rows, assignee `<select>`
  reusing `_kanbanPopulateAssigneeSelect()` verbatim — no new
  profile-lookup code).
- Dispatch button on a crew card → `showConfirmDialog` (same wording
  pattern as `runKanbanDispatcher`'s "this spawns worker subprocesses"
  confirm) → `POST /api/crews/<id>/dispatch` → toast with created-count →
  `loadKanban(true)` + set a new `kanbanWorkflowTemplateFilter` (same UX
  slot as the existing tenant/assignee filters) to the dispatched crew's id
  so the board immediately scopes to just-created tasks.
- `static/commands.js`: `/crews` slash command listing templates (mirrors
  `/personas`); `/crews dispatch <name>` optional, can slip to v1.1 if v1
  needs to stay tight.
- `static/i18n.js`: new keys across all 15 locale blocks.

**Tests to write:**
1. `tests/test_crews_api.py`: CRUD round-trip, caps, profile isolation
   (mirrors `test_agent_definitions_api.py`); dispatch creates N tasks
   sharing one `current_step_key`/`workflow_template_id`, variable
   substitution, partial-failure result shape (one bad assignee doesn't
   abort siblings), `board` param forwarding, `workflow_template_id`
   feature-detection fallback exercised with a stub `kanban_db` lacking
   the kwarg.
2. `tests/test_crews_ui.py`: toolbar button + modal wiring, locale-key
   parity, CSS theme-token guard (shape from `test_audit_trail_ui.py`).
3. Regression: dispatch must NOT call `dispatch_once` (assert the request
   handler for `/api/crews/*/dispatch` never touches the dispatcher).

**Open questions for Phase 1:**
1. Should `/api/crews/create` require at least one task spec with a
   non-empty `assignee`, or allow all-unassigned templates (dispatched
   tasks just sit `ready`/unclaimed until someone assigns them, same as
   any manually-created unassigned task today)? Leaning toward allowing
   it — the assignee validation happens at `kb.create_task` time already;
   a second gate here would be a parallel validation copy.

**Critical files:**
- `api/crews.py` (new)
- `api/kanban_bridge.py` (`_create_task_payload` extension point)
- `api/routes.py`
- `static/panels.js`
- `static/index.html`
- `static/i18n.js`

#### Phase 2 (v1.1) — Office-view crew grouping — STATUS: DONE (shipped 2026-08-10)

**Shipped 2026-08-10:** landed per the plan below, one deviation noted.
`_kanbanOfficeViewWorkers()` (`static/panels.js`) now returns crew-grouped
sections -- `{templateId, workers}[]` -- instead of a flat worker list: a
single `Map` keyed by `task.workflow_template_id` built while walking the
flat filtered list once, so an interleaved dispatch order (crew A, crew B,
crew A again) still lands both of crew A's workers in one contiguous group;
the untagged bucket (`templateId: null`) is appended in a second, separate
step so it always renders last regardless of when its first ungrouped
worker appeared. `_kanbanRenderOfficeView()` renders one
`.kanban-office-group` section per bucket via a new
`_kanbanOfficeGroupHtml()`, each with its own `.kanban-office-grid` (same
grid class as before, just one per group now) and a header resolved by
`_kanbanCrewName()`, falling back to the raw template id. Crew names are
looked up from `_kanbanCrewsList` -- the exact cache `loadKanbanCrews()`
already populates for the Crews modal, not a second fetch path.

**One deviation:** the plan says names come from "the already-loaded
`/api/crews` list, cached client-side" -- but if a user opens the office
view before ever opening the Crews modal, that cache is still `null` and
group headers would be stuck showing raw template ids. Added a one-time,
flag-guarded lazy fetch (`_kanbanCrewsListFetchInFlight`) inside
`_kanbanRenderOfficeView()` that calls `loadKanbanCrews()` itself (no
parallel endpoint or duplicate fetch logic) the first time a render needs
names and the cache is still empty, then re-renders once it resolves.
Subsequent renders reuse the now-warm cache, matching the "not re-fetching
on every render" requirement.

A new `#kanbanCrewFilter` `<select>` sits in the sidebar filter stack next
to `#kanbanAssigneeFilter`/`#kanbanTenantFilter`, populated by
`_kanbanPopulateCrewFilter()`/`_kanbanCrewFilterIds()` from the distinct
`workflow_template_id` values actually present in `_kanbanBoard`'s tasks
(not the full `/api/crews` list, so a crew with zero currently-visible
tasks isn't offered as a filter option) -- hooked into
`_kanbanRenderBoard()` itself, the same call site the office view and every
existing refresh path (poll/SSE, filter, lane toggle) already drives, so it
can't drift out of sync either. `kanbanWorkflowTemplateFilter` stays the one
authoritative value (already read by `_kanbanCurrentFilters()` and set by
`dispatchKanbanCrew()`); the select's `onchange` just updates that variable
and calls `loadKanban(true)`, reusing Phase 1's `?workflow_template_id=`
param -- narrowing the same `_kanbanBoard` object both the normal board and
the office view's grouping read from, not a second independently-filtered
copy. `clearKanbanFilters()` resets it with the exact same shape as the
existing tenant-filter reset (`.value` + `.dataset.defaultValue`).

3 new i18n keys (`kanban_office_ungrouped`, `kanban_crew_filter_label`,
`kanban_all_crews`) across all 15 locale blocks, following this feature
area's existing convention of identical English text per locale (key
parity is the enforced, tested contract here -- see `kanban_office_view`/
`kanban_crews` and siblings, already English-only in every locale before
this phase). New CSS (`.kanban-office-group`/`.kanban-office-group-title`)
added inside the existing theme-token-guarded "Office view:" comment block
in `static/style.css`, no hardcoded colors.

Tests: extended `tests/test_kanban_office_view.py` in place (11 → 21 cases
-- 10 new: grouping by `workflow_template_id` with interleaved crews, the
ungrouped bucket forced trailing rather than first-appearance order, the
dedicated "Ungrouped" label, name lookup + guarded lazy-fetch-once from
`_kanbanCrewsList`, one grid per group instead of one flat grid, the filter
select's presence/placement/wiring, filter options sourced from the loaded
board rather than the full crews list, the filter hooked into
`_kanbanRenderBoard()`, the filter reusing the same `kanbanWorkflowTemplateFilter`/
`loadKanban()` path the office view's data comes from, and the
`clearKanbanFilters()` reset -- plus the 3 new keys folded into the
existing locale-parity test rather than a new one, exactly as the plan
specified. No new test file. Verified all 10 new/extended assertions fail
against the pre-Phase-2 baseline (a byte-for-byte copy of `static/panels.js`/
`index.html`/`style.css`/`i18n.js` from immediately before this phase's
edits) and pass after, while the 11 original Phase-1-era cases pass
unchanged against both. Full verification run: `test_kanban_office_view.py`
(21), `test_crews_api.py`/`test_crews_ui.py` (41, confirmed unaffected --
Phase 2 touches no Crews backend or dispatch code), `test_kanban_bridge.py`/
`test_kanban_ui_static.py`/`test_kanban_view_toggle.py`,
`test_agent_definitions_api.py`/`_ui.py`, `test_audit_trail_api.py`/`_ui.py`,
`test_memory_entries.py`, `test_skills_security_scan.py` (239 across that
sweep), and the full locale-parity suite (100 -- every per-locale test file
plus `test_issue3539_language_dropdown_all_locales.py`) -- all passing,
zero regressions. `node -c static/panels.js` clean.

Purely additive to the shipped office view; no new storage, no new
endpoints beyond Phase 1's `?workflow_template_id=` filter. **Depends on
Phase 1 shipping first** (needs `workflow_template_id` actually populated
on real tasks) — build sequentially, not in parallel with Phase 1.

- `_kanbanOfficeViewWorkers()` (`static/panels.js:2602-2611`) groups by
  `task.workflow_template_id` when present; `_kanbanRenderOfficeView()`
  renders a section header per crew (template name looked up from the
  already-loaded `/api/crews` list, cached client-side) instead of one flat
  grid, with ungrouped/CLI-created workers falling into a trailing
  "Ungrouped" section — additive branch on the existing render path, same
  "can't drift out of sync" reasoning the office view itself used for
  hooking into `_kanbanRenderBoard()`.
- A crew filter `<select>` (populated from distinct `workflow_template_id`
  values in `_kanbanBoard`) narrows both the office view and the normal
  board — reuses `_board_payload`'s new `?workflow_template_id=` param from
  Phase 1, same UX slot as the existing tenant/assignee filters
  (`clearKanbanFilters()` extended to also reset it).

**Tests:** extend `tests/test_kanban_office_view.py` with grouped-render
cases (multiple crews' workers interleaved, ungrouped fallback, filter
narrows both board and office view) rather than a new test file.

**Critical files:** `static/panels.js`, `tests/test_kanban_office_view.py`.

#### Phase 1.2 (v1.2) — Crew templates gallery: search + last-dispatched recency — STATUS: DONE (shipped 2026-08-10)

**Scoping this first, per the "Current status" pointer above.** The doc's
"Not started" line named "a real workflow-builder/templates-gallery/
dispatch-dialog beyond what Crews v1 does" as the open part of Priority 2.
The workflow-builder and dispatch-variables-dialog pieces are already
resolved: a step-graph builder is explicitly out of scope (see
"Investigated and rejected" above — nothing upstream to build it against),
and the dispatch-time `{variable}` collection dialog shipped as Phase 1's
follow-up (see above). What was actually still open is the "templates
gallery" half: today's Crews modal (`#kanbanCrewsModal`) is a flat
`.kanban-crew-list` grid with no search, no sort, no metadata beyond name/
description/task-count.

**Investigated and scoped down, not the full Hermes-Studio "gallery."**
Hermes-Studio's templates gallery has categories, tags, and a curated/
featured split across what's implied to be a large, possibly shared,
catalog. hermes-webui's crews are a plain per-profile, user-owned,
uncategorized collection capped at `MAX_CREWS = 50` (`api/crews.py`) — a
single user's own templates, not a browsable marketplace. At that scale, a
categories/tags/featured taxonomy is speculative UI for a problem that
doesn't exist yet (most profiles will have a handful of crews, not dozens
needing organization by category) — building it now would be exactly the
kind of unnecessary-polish gallery the task brief warned against, not a
real gap. What *is* a real, already-felt gap even at small-N: (a) no way to
jump straight to a crew by typing part of its name once you have more than
a screenful, and (b) the list has no signal for "which of these do I
actually use" — cards render in raw creation order forever, so an
old-but-frequently-redispatched crew sits wherever it was first created
instead of surfacing near the top. Both are small, additive, conservative
slices; neither touches the create/edit form or the dispatch-confirm/
variables-collection code path (left untouched, per the constraint that
another agent owns that code path concurrently).

**Shipped 2026-08-10:**
- **Search/filter**: a `#kanbanCrewsSearch` input (reuses the existing
  `.sidebar-search` component verbatim — same one `#kanbanSearch`/
  `#agentsSearch` already use, not a new search-box implementation) sits
  above `#kanbanCrewList` inside `kanbanCrewsModal`. Purely client-side over
  the already-loaded `_kanbanCrewsList` cache (capped at 50 rows — no
  pagination or server-side search needed at this scale, mirrors how
  `renderAgentDefinitions`'s Personas search works). New pure function
  `_kanbanFilterCrews(crews, query)` (name + description, case-insensitive
  substring) called from `_renderKanbanCrewList()`; `filterKanbanCrews()` is
  the `oninput` handler, mirroring `filterAgentDefinitions()`'s
  call-render-again pattern exactly.
- **Last-dispatched recency**: `api/crews.py` gains a `last_dispatched_at`
  field (`None` until first dispatch) on every crew row, stamped by a new
  `_touch_crew_dispatched(crew_id, ts)` at the end of `dispatch_crew()`
  under the existing `_WRITE_LOCK`, using the same read-modify-write shape
  as `update_crew()`. Stamped on *every* dispatch attempt that finds a real
  crew, regardless of per-task success/failure — "last dispatched" means
  "a dispatch of this template was last attempted at this time," not "last
  fully succeeded"; a template that always fails to dispatch cleanly is
  still surfaced as recently-touched rather than silently invisible.
  `duplicate_crew()` does **not** copy the source's `last_dispatched_at` —
  a duplicate is a new template with no dispatch history of its own.
  Best-effort: if the crew_id isn't found in real storage (e.g. a test
  double, or a race with a concurrent delete), the touch is a silent no-op
  rather than raising — dispatch itself still succeeds/fails on its own
  merits, this is pure metadata.
  `_kanbanCrewCard()` shows a "Last dispatched: {relative time}" /
  "Never dispatched" meta line, reusing `_formatRelativeSessionTime()`
  from `static/sessions.js` (already generic despite the name — see its own
  session_time_* i18n keys, already present in all 15 locales) rather than
  writing a second relative-time formatter. `_renderKanbanCrewList()` sorts
  the (filtered) list via a new pure `_kanbanSortCrews(crews)`:
  `last_dispatched_at` descending (never-dispatched crews sort last), tied
  by `created_at` descending — most-recently-used-or-created first, instead
  of raw insertion order.
- 4 new i18n keys (`kanban_crews_search_placeholder`, `kanban_crews_no_match`,
  `kanban_crew_last_dispatched`, `kanban_crew_never_dispatched`) across all
  15 locale blocks, English text in every locale — same established
  convention this feature area already uses (see Phase 2's note on
  `kanban_office_ungrouped` and siblings).
- New CSS (`.kanban-crews-search`, `.kanban-crew-card-last-dispatched`)
  added inside the existing theme-token-guarded "Crews:" comment block in
  `static/style.css`, all `var(...)` tokens, no hardcoded colors.

**Deliberately not touched:** `dispatchKanbanCrew()`'s body, the
`{variable}` collection modal, and the create/edit form — all outside this
slice's scope and, per the task constraint, another agent's concurrent
work touches that exact code path. The Crews list modal closes immediately
after a successful dispatch today (unchanged), so the just-dispatched
crew's new `last_dispatched_at` simply shows correctly the *next* time the
modal is reopened (`loadKanbanCrews()` already re-fetches from `/api/crews`
on every `openKanbanCrews()` call) — no extra refresh call was needed
inside the dispatch function itself.

**Known gap, not caught until implementation — flagging rather than
silently shipping:** `_touch_crew_dispatched` stamps the timestamp once per
`dispatch_crew()` call, not once per successfully-created task. A crew
dispatched twice in quick succession (e.g. a user double-clicks through two
separate confirms) correctly reflects the *later* attempt, but there is no
per-task-spec dispatch history, only a single template-level "last
attempted" signal. That matches the recency-signal's stated purpose
("which templates do I actually use") and was not scoped to be a full
dispatch-history log — Activity/Audit Trail already covers per-turn history
elsewhere in the app; a second, crew-specific history log was judged out of
scope for this slice.

Tests: extended `tests/test_crews_api.py` (27 → 32, 5 new cases —
`last_dispatched_at` present as `None` on create, duplicate does not carry
it over, a real dispatch against real profile-scoped storage stamps it, a
fully-failed dispatch still stamps it, dispatching a crew absent from
storage doesn't raise) and `tests/test_crews_ui.py` (19 → 25, 6 new cases —
search input markup/wiring, the new pure `_kanbanFilterCrews`/
`_kanbanSortCrews` functions executed for real via node — not a
source-string proxy — against case-insensitive/substring/nulls-last/
tie-break cases, the card's last-dispatched line reusing
`_formatRelativeSessionTime` rather than a second formatter, the shared
filter/sort/render wiring, CSS theme-token guard, and the backend field
check) plus the existing locale-parity test extended in place with the 4
new keys — all passing. Verified the new tests fail against the
pre-Phase-1.2 code (reverting `api/crews.py` alone drops the new API-side
cases; reverting `static/panels.js`/`index.html`/`style.css`/`i18n.js`
drops the new UI-side cases) and pass after. Full verification run: all 57
Crews tests (`test_crews_api.py` + `test_crews_ui.py`),
`test_kanban_office_view.py`/`test_kanban_bridge.py`/`test_kanban_ui_static.py`/
`test_kanban_view_toggle.py` (crew-grouping/filter logic reads
`workflow_template_id` only, untouched by this slice, confirmed still
green), the full 100-case locale-parity suite, and
`test_agent_definitions_api.py`/`_ui.py`/`test_audit_trail_api.py`/`_ui.py`
as unrelated-regression checks — all passing, zero regressions. `ruff
check` clean on `api/crews.py`; `node -c` clean on `static/panels.js` and
`static/i18n.js`.

**Critical files:** `api/crews.py`, `static/panels.js`, `static/index.html`,
`static/style.css`, `static/i18n.js`, `tests/test_crews_api.py`,
`tests/test_crews_ui.py`.

#### Phase 3 — Cost panel — STATUS: DONE (shipped 2026-08-10, option 2: labeled approximation)

**Decided 2026-08-10 (superseding the earlier "cut for now" decision below,
kept for its reasoning): option 2, ship the best-effort heuristic join, with
an explicit approximation disclosure in the UI — a human call, made after
weighing option 1 (real fix, but requires a separate PR against
`hermes-agent-src`, which this repo only mounts read-only) against option 3
(stay cut indefinitely). Re-read the original three-option reasoning below
before touching this again; it is still accurate about *why* no precise
number is possible today.

**Not planned to a concrete API/data-shape — deliberately.** No data
path today truthfully connects a kanban task to the `estimated_cost_usd` of
the CLI session its dispatched worker actually ran (`HERMES_KANBAN_TASK` is
set in the worker's env, `hermes_cli/kanban_db.py:7392`, but never written
onto the resulting `sessions` row). Presenting a "crew cost" number built on
a guess would misreport real spend as fact. Three options, needing a human
decision before any implementation work starts here:

1. **Upstream fix** (best): a `hermes-agent-src` change stamps
   `HERMES_KANBAN_TASK` onto the new `sessions` row (e.g. as
   `kanban_task_id`) at session-start time. Then a cost endpoint becomes a
   straightforward `SUM(estimated_cost_usd) FROM sessions WHERE
   kanban_task_id IN (...)` join, same shape as the existing analytics
   query at `api/routes.py:10946-10987`. Out of scope for hermes-webui
   itself — this repo only mounts `hermes-agent-src` read-only; needs a
   separate PR against that source tree.
2. **Best-effort heuristic join** (approximate, must be labeled as such in
   the UI): match a crew's dispatched task's `assignee` (profile) +
   `started_at`/`completed_at` window against `sessions` rows on that
   profile started inside the window. Fragile under concurrent
   same-profile dispatches (two tasks with the same assignee running at
   once become ambiguous) — needs an explicit "approximate, may be
   inaccurate under concurrent same-profile runs" disclosure, not a silent
   number.
3. **Cut for now.** Ship Phase 1/2 without any cost surface; revisit once
   (1) lands or a maintainer accepts (2)'s approximation risk.

**Superseded — originally decided (3), cut for now.** 2026-08-10's later
decision (above) chose option (2) instead: option (1)'s upstream fix is
still the better long-term answer (see open question #1 below, still open),
but it requires a separate PR against a different source tree, so it wasn't
picked as *this* session's path.

**Open questions for Phase 3:**
1. **Still open.** Is a `hermes-agent-src` PR for option (1) realistic/
   desired later, replacing the heuristic with a real join once it lands?
   The heuristic below does not block that migration — it's an additive
   endpoint (`GET /api/crews/cost`), not a schema change, so swapping its
   internals for a real join later is a contained change.
2. **Still open.** If/when precise cost data exists: should Personas apply
   to kanban-dispatched workers at all? `assignee`/profile and
   `agent_definition_id`/persona are currently unconnected — a Persona's
   system prompt is only ever injected into the webui chat path
   (`api/streaming.py`/`api/gateway_chat.py`), never into a kanban-dispatched
   CLI worker.

#### Data shape (no new storage — read-only, computed on request)

```json
{
  "costs": {
    "<workflow_template_id>": {
      "approx_cost_usd": 0.35,
      "task_count": 3,
      "priced_task_count": 2
    }
  },
  "is_approximate": true
}
```
`is_approximate` is always `true` — there is no code path that can ever set
it `false` today; it exists so the frontend (and any future consumer) has a
machine-readable signal to gate a disclosure on, not just prose in this doc.
`priced_task_count` vs `task_count` lets the UI distinguish "every dispatched
task in this crew matched a priced session" from "some tasks have no
session data yet (still running, or the assignee profile has no readable
`state.db`)" — both cases legitimately return `0.0`, and collapsing them
into one number would hide that difference.

#### API endpoints (`api/routes.py`, next to the existing `/api/crews` block)

- `GET /api/crews/cost?board=<board>` → the shape above, computed over
  every currently-non-archived-or-archived (`include_archived=True`, so a
  completed crew's cost doesn't silently disappear once its tasks are
  archived) task on the given board that carries a `workflow_template_id`.
  No `workflow_template_id` filter param — the endpoint always returns
  every crew's estimate in one response (the Crews modal and the Kanban
  office view both want "all crews currently visible," not one at a time,
  and task counts here are small enough that a single unfiltered scan is
  cheap, unlike Audit Trail's cross-session scan which needed an explicit
  cap).

#### Storage decision

None — pure computation, no new file, no new table. `api.crews.estimate_crew_costs(tasks)`
takes a flat list of already-fetched Kanban task dicts (the route handler
fetches them via the same `kb.list_tasks`/`_task_dict` machinery
`_board_payload` already uses, not a second task-reading path) and reads
each distinct `assignee`'s CLI `state.db` via `api.models._agent_state_db_path(profile=...)`
— the existing per-profile path-resolution helper, not a new one.

#### Frontend hook-in

- `static/panels.js`: `loadKanbanCrewCosts()` fetches and caches
  `_kanbanCrewCostsCache` (`null` until first load, mirroring
  `_kanbanCrewsList`'s cache-then-lazy-fetch-once shape exactly, including
  its own fetch-in-flight guard). `_kanbanCrewCostLine(crewId)` formats the
  disclosure string — returns `''` (renders nothing) when a crew has zero
  priced tasks, so an unpriced/never-dispatched crew's card doesn't show a
  misleading "$0.00". Wired into both existing render paths: `_kanbanCrewCard()`
  (Crews modal list) and `_kanbanOfficeGroupHtml()` (Kanban office view
  group header) — one shared formatter, not two independent cost strings
  that could drift out of sync with each other's wording.
- `static/style.css`: `.kanban-crew-card-cost`/`.kanban-office-group-cost`,
  theme-token colors only (`var(--muted)`), added inside the existing
  theme-token-guarded "Crews:"/"Office view:" comment blocks.
- `static/i18n.js`: one new key, `kanban_crew_approx_cost` (`"~{0} (approx,
  {1} of {2} tasks priced)"`), across all 15 locale blocks. The word
  "approx" is baked into the template string itself, not just surrounding
  UI copy — so the disclosure survives even if a future edit moves the line
  to a place where surrounding label text doesn't carry it.
- No slash command, no new nav tab — this is a small addition to two
  already-existing surfaces (Crews modal, office view), not a new screen.

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)

1. `tests/test_crew_cost_estimate.py` (new, unit-level — monkeypatches
   `api.models._get_profile_home` to a `tmp_path` sqlite `state.db`, no HTTP
   server needed): tasks without a `workflow_template_id` ignored; a task
   with no `assignee`/`started_at` is counted but not priced; a session
   inside a task's `[started_at, completed_at]` window is matched and
   summed; a session outside the window is not matched; `source='webui'`
   sessions are excluded (crew-dispatched workers are always CLI-spawned);
   multiple tasks in one crew across different assignees sum correctly;
   distinct crews stay separate; a missing/unreadable `state.db` degrades
   to zero without raising; a source-string guard that the route handler
   always sets `is_approximate: true` on both its success and its
   exception-fallback branch.
2. `tests/test_crews_ui.py` additions: the two formatter/loader functions
   exist; the cost line's body always references both the
   `kanban_crew_approx_cost` i18n key and `priced_task_count` (regression
   guard against a future edit dropping the approximation disclosure); both
   render call sites (`_kanbanCrewCard`/`_kanbanOfficeGroupHtml`) call the
   shared formatter; the lazy-fetch-once cache pattern (guards against
   re-fetching on every render, mirroring the existing crew-names guard);
   the route handler string-present in `routes.py`; CSS theme-token guard
   on both new classes.

#### Open questions — resolved 2026-08-10

1. **Which option to ship** — resolved: option 2. See "Decided" note above.
2. **Per-crew vs. per-dispatch-run cost?** Resolved: per-crew
   (`workflow_template_id`), not per-run (`current_step_key`) — matches how
   the office view already groups by crew, not by individual dispatch, and
   keeps the UI to one number per crew rather than a growing list of
   historical run costs. A user wanting per-run granularity can still infer
   it from Kanban's existing task-level `current_step_key`/timestamps; this
   just doesn't surface it as a second aggregated view.
3. **Should ambiguous concurrent-dispatch double-counting be fixed with a
   dedupe pass (e.g. never attribute the same session to two tasks)?**
   Resolved: no, deliberately left as-is. The plan doc's own framing for
   option 2 accepts this fragility as inherent to the heuristic, not a bug
   to paper over with a dedupe heuristic that would just be a second,
   unverified guess layered on top of the first one. The UI disclosure
   covers this ("approx"), which is the actual mitigation, not silent
   dedup logic that could hide the ambiguity instead of admitting it.

**Shipped 2026-08-10:** implemented exactly per the plan above —
`api.crews.estimate_crew_costs()` (+ its `_profile_session_rows()` helper)
in `api/crews.py`, `GET /api/crews/cost` in `api/routes.py`, cost lines
wired into both the Crews modal and the Kanban office view in
`static/panels.js`, theme-token CSS, and 1 new i18n key × 15 locales.
Tests: `tests/test_crew_cost_estimate.py` (9 cases) and additions to
`tests/test_crews_ui.py` (6 cases) — all passing, full suite verified with
no regressions. Known limitation (by design, not a bug — see Open question
#3 above): concurrent same-profile dispatches can double-count or
misattribute a session's cost; the UI's "approx" disclosure is the
mitigation, not a dedupe algorithm.

#### Critical files

- `api/crews.py`
- `api/routes.py`
- `static/panels.js`
- `static/style.css`
- `static/i18n.js`
- `tests/test_crew_cost_estimate.py` (new)
- `tests/test_crews_ui.py`

---

## Priority 3 — other confirmed gaps

- **Knowledge Browser** — STATUS: DONE, see full write-up below.
- **Audit Trail UI** — STATUS: DONE, see full write-up below.
- **Analytics/cost dashboard** — STATUS: DONE, see full write-up below.
- **Command palette** — STATUS: DONE, see full write-up below.
- **Chat export** — STATUS: DONE, see full write-up below.
- **Sound notification system** — synthesized Web Audio API chimes (agent
  spawned/complete/failed, chat notification, thinking tick), no audio
  files needed.
- **Voice input** (Web Speech API, `use-voice-input.ts`/
  `use-voice-recorder.ts`) — not present.
- **Onboarding tour** — hermes-webui has `onboarding.py`/`onboarding.js`;
  worth checking whether it's a guided step-by-step *tour*
  (`react-joyride`-style, like Hermes-Studio has in addition to a setup
  wizard) or just the wizard.

### Command palette + keyboard-shortcuts modal — STATUS: DONE (shipped 2026-08-10)

Hermes-Studio has a ⌘K-style global command palette (`cmdk`-style) plus a
global keyboard-shortcuts help modal. hermes-webui had no discoverable global
command palette.

**Read `static/commands.js` first — resolved deliberately, not silently
duplicated.** hermes-webui already has a slash-command registry (`COMMANDS`
array, ~29 builtin entries) plus a runtime-merged autocomplete surface
(`getMatchingCommands()`) that additionally pulls in async agent/plugin/
skill/bundle commands loaded from `/api/commands` and friends. A command
palette conceptually overlaps with that, so the decision below is load-bearing
for anyone extending this later.

**Decision:** the palette's command data source IS the existing `COMMANDS`
array from `commands.js` directly — not a second, independently-authored list
of command names/descriptions. It deliberately does **not** call
`getMatchingCommands()` (which additionally merges in the async-loaded agent/
plugin/skill/bundle commands): that call is async (network round-trip on
first use) and would make the palette's open feel laggy the first time, and
those commands remain fully discoverable today by typing `/` in the composer.
The palette surfaces the same static 29-entry table the composer autocomplete
already dispatches through — one source of truth for name/description/arg
metadata, zero duplicated strings. This does mean the palette's command list
is a strict subset of the composer's `/`-autocomplete list (missing agent/
plugin/skill/bundle commands) — an accepted, documented gap, not an oversight.

This feature is purely client-side: **no Data shape section, no API
endpoints section** — no new persisted data, no new backend endpoint.

#### Frontend hook-in
- `static/index.html`: new `#btnCommandPalette` icon button in
  `.app-titlebar-inner` (next to `#btnTitlebarNewChat`, so it's visible from
  every panel, not just chat — the rail's `.nav-tab` icons are user-
  reorderable/hideable via `localStorage['hermes-webui-hidden-tabs']`, which
  is the wrong shape for a global action). New overlay markup:
  `#commandPaletteOverlay` › `#commandPaletteModal` (`#commandPaletteInput`,
  `#commandPaletteList`, a footer keyboard hint), and a second, independent
  `#shortcutsHelpOverlay` › `#shortcutsHelpModal` (static list of shortcut
  groups: General / Sessions / Composer).
- `static/panels.js`: `openCommandPalette`, `closeCommandPalette`,
  `_renderCommandPaletteResults`, `_filterCommandPaletteEntries`,
  `_commandPaletteNavEntries()` (reads live `.rail .nav-tab[data-panel]`
  buttons from the DOM, skipping `.nav-tab-hidden` ones, so the palette's
  Navigate section always matches whatever panels the user currently has
  visible/ordered — not a second hardcoded panel list that could drift),
  `_commandPaletteCommandEntries()` (reads `COMMANDS` from `commands.js`),
  `_commandPaletteActionEntries()` (Keyboard Shortcuts +, when a session is
  open, the three Chat Export actions below — ties the two Priority-3
  features together instead of building a second export entry point),
  `_selectCommandPaletteEntry`, `_navigateCommandPalette`,
  `openShortcutsHelp`, `closeShortcutsHelp`. Palette keyboard-nav state
  (`_paletteSelectedIdx`) is separate from the composer dropdown's
  `_cmdSelectedIdx` so the two never collide if both happen to be open.
- `static/boot.js`: global keydown handler registers Ctrl/Cmd+**Shift**+P →
  `openCommandPalette()`. Plain Ctrl/Cmd+K is already bound to "new chat"
  (`static/boot.js` ~line 2422) — cmdk's usual ⌘K would silently steal that
  binding, so this uses the VS Code / cmdk-alternate convention
  (Ctrl/Cmd+Shift+P) instead, confirmed unused anywhere else in the
  codebase. Fires globally (not skipped for text-input focus), matching the
  existing Cmd/Ctrl+, → Settings handler's precedent, since Shift+P is not a
  text-editing chord. Bare `?` → `openShortcutsHelp()`, guarded to skip
  input/textarea/contenteditable targets (same `isText` guard already used
  by the Cmd/Ctrl+B handler). Escape closes whichever of the two is open,
  extending the existing Escape handler.
- `static/style.css`: new `.cmdk-overlay`/`.cmdk-modal`/`.cmdk-input`/
  `.cmdk-section-label`/`.cmdk-empty`/`.shortcuts-help-*` rules for the
  modal shells only. List rows reuse the **existing**
  `.cmd-item`/`.cmd-item-name`/`.cmd-item-desc`/`.cmd-item-arg`/
  `.cmd-item-badge` classes already styled for the composer's slash-
  autocomplete dropdown — same visual language, zero new item CSS. All
  colors go through existing `var(--...)` tokens; the overlay backdrop
  reuses the established `rgba(7,12,19,.62)` + `backdrop-filter:blur(6px)`
  convention already shared by `.app-dialog-overlay` and
  `.kanban-modal-overlay` (not a new pattern).
- `static/i18n.js`: new keys (`command_palette`, `command_palette_placeholder`,
  `command_palette_no_results`, `command_palette_section_navigate`,
  `command_palette_section_commands`, `command_palette_section_actions`,
  `command_palette_hint`, `keyboard_shortcuts`, `keyboard_shortcuts_close`,
  `shortcuts_group_general`, `shortcuts_group_sessions`,
  `shortcuts_group_composer`, `shortcut_open_palette`,
  `shortcut_open_shortcuts`, `shortcut_new_chat`, `shortcut_toggle_sidebar`,
  `shortcut_focus_composer`, `shortcut_open_settings`,
  `shortcut_navigate_sessions`, `shortcut_send`, `shortcut_send_newline`)
  across all 15 locale blocks.

**Selection behavior (a second deliberate safety decision):** picking a
Navigate or Action entry executes immediately (switch panel / open shortcuts
modal / trigger export download) and closes the palette. Picking a **command**
entry does **not** auto-execute — it switches to the Chat panel if not
already active, inserts `/name` (+ trailing space if the command declares an
`arg`) into the composer, and focuses it, exactly mirroring what clicking a
suggestion in the existing composer autocomplete dropdown already does. This
is deliberate: several builtin commands are destructive or session-mutating
(`/clear`, `/stop`, `/new`), and the palette is reachable from any panel —
auto-firing one of those on selection, possibly against a session the user
isn't even looking at, would be a bad surprise. Non-destructive/unambiguous
Navigate and Action entries don't have that risk, so they execute directly.

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)
`tests/test_command_palette_ui.py` (structural wiring guards, no browser):
1. Trigger button + overlay markup present in `index.html`
   (`btnCommandPalette`, `commandPaletteOverlay`, `commandPaletteInput`,
   `commandPaletteList`, `shortcutsHelpOverlay`, `shortcutsHelpModal`).
2. `panels.js` defines the open/close/render/filter/select functions listed
   above.
3. `boot.js` registers the Ctrl/Cmd+Shift+P and bare `?` keydown bindings,
   and the existing Ctrl/Cmd+K "new chat" binding is untouched (regression
   guard against reintroducing the collision).
4. The palette's command source is literally `COMMANDS` (grep for a `COMMANDS`
   reference inside the palette's entry-building function) — guards against
   a future edit silently duplicating command definitions instead of reusing
   the registry, per the decision above.
5. i18n keys present in all 15 locale blocks (same key-diff pattern as
   `tests/test_agent_definitions_ui.py`).

#### Open questions — RESOLVED 2026-08-10
1. **Shortcut collision with existing Cmd/Ctrl+K** — resolved: use
   Ctrl/Cmd+Shift+P instead (confirmed unused).
2. **Reuse vs. duplicate the slash-command registry** — resolved: reuse
   `COMMANDS` directly; skip the async agent/plugin/skill/bundle layer for
   palette purposes (documented gap, not an oversight).
3. **Auto-execute vs. insert-into-composer on select** — resolved:
   insert-into-composer for commands (safety), immediate-execute for
   Navigate/Action entries.

**Shipped 2026-08-10:** implemented exactly per the plan above — trigger
button + Ctrl/Cmd+Shift+P + `?` shortcuts modal, `COMMANDS`-reuse data
source, DOM-driven Navigate section, insert-not-execute command selection,
21 new i18n keys × 15 locales, `tests/test_command_palette_ui.py`. Known
gap (by design, see decision above): agent/plugin/skill/bundle commands
are not in the palette's Commands section, only the static builtin
`COMMANDS` table — they're still reachable via `/` in the composer.

### Chat export — STATUS: DONE (shipped 2026-08-10)

Hermes-Studio's `export-menu.tsx` offers Markdown/JSON/Text export of a
session's chat messages.

**Investigation finding (this changes the scope of the gap):** hermes-webui
already ships most of this — `static/messages.js`'s `transcript()` (client-
side Markdown from `S.messages`, wired to Settings → Session actions'
"Transcript" button `#btnDownload`), `#btnExportJSON` and `#btnExportHTML`
(both hit the existing `GET /api/session/export?session_id=...&format=...`
endpoint, `api/routes.py:_handle_session_export` ~line 16849), plus a
per-conversation "Export as HTML" item in the sidebar ⋮ menu
(`_appendSessionExportHtmlAction` in `static/sessions.js`, works on *any*
session in the active profile, not just the currently-open one — the
endpoint is non-mutating and session_id-addressed). So this is **not** "no
equivalent found" — it's two narrower, real gaps:
1. **No plain-Text format anywhere** — only Markdown/JSON/HTML exist.
2. **The one entry point that works on a session that isn't currently
   open** (the sidebar ⋮ menu) **only offers HTML**, not Markdown/JSON/Text.
   Getting a non-active session's transcript as Markdown or JSON today
   requires first opening it.

Per the task brief's own example of when a new backend endpoint is
warranted ("exporting a session not currently open") — that's exactly gap
#2, so this closes it by extending the *existing* endpoint rather than
building a parallel client-side-only implementation that couldn't reach a
session that isn't loaded.

#### Data shape
No new persisted data. Export reads the existing `Session.__dict__` (via
`api/helpers.py`'s `redact_session_data()`), the same source the current
`format=json`/`format=html` branches already use.

#### API endpoints
No new endpoint — extends the existing `GET /api/session/export` handler
(`api/routes.py:_handle_session_export`) with two new `format` values,
alongside the existing `json` (default) and `html`:
- `format=md` → `text/markdown; charset=utf-8`,
  `Content-Disposition: attachment; filename="hermes-{sid}.md"`
- `format=text` → `text/plain; charset=utf-8`,
  `Content-Disposition: attachment; filename="hermes-{sid}.txt"`

Both are built by a new small module `api/session_export_text.py`
(`render_session_markdown(session)`, `render_session_text(session)`),
importing (not duplicating) `_content_to_text()`, `_fmt_ts()`, and
`_ROLE_LABELS` already defined in `api/session_export_html.py`, so all four
export formats flatten multimodal content and format timestamps identically.
System messages are skipped, matching the existing HTML branch's behavior.

#### Frontend hook-in
- `static/index.html`: new `#btnExportText` button next to the existing
  `#btnDownload`/`#btnExportJSON`/`#btnExportHTML` trio in Settings → Session
  actions.
- `static/boot.js`: `$('btnExportText').onclick` — same `<a href=...
  download>` pattern as `#btnExportJSON`, hitting `format=text`.
- `static/sessions.js`: `_appendSessionExportHtmlAction` is replaced by
  `_appendSessionExportActions(menu, session)`, called from both branches of
  `_openSessionActionMenu` (read-only and normal). It appends four menu
  items — Markdown / JSON / Text / HTML — each hitting
  `/api/session/export?session_id=<THIS row's session>&format=...`, so all
  four formats now work identically for any session in the active profile,
  not only the one currently open (closes gap #2 above). Non-mutating, so
  offered for read-only/imported sessions too, matching the prior HTML-only
  behavior.
- Command palette (previous section): when a session is open, three palette
  Action entries fire the same export URLs for the active session — the
  palette does not build a second export mechanism.
- `static/style.css`: no new CSS. Reuses the existing `.ws-opt`/
  `.session-action-opt` menu-item styling and `.settings-action-btn` button
  styling already used by the sibling export buttons/menu items.
- `static/i18n.js`: new keys (`export_session_text_tooltip`,
  `export_session_text`, `session_export_md`, `session_export_md_desc`,
  `session_export_json_sidebar`, `session_export_json_sidebar_desc`,
  `session_export_text_sidebar`, `session_export_text_sidebar_desc`) across
  all 15 locale blocks. (`session_export_html`/`_desc` already exist and are
  reused as-is for the fourth menu item.)

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)
`tests/test_chat_export.py`:
1. API: `format=md` and `format=text` on `/api/session/export` return 200
   with the correct `Content-Type`/`Content-Disposition`/filename extension
   and body content derived from the session's messages; the existing
   `format` omitted/`json`/`html`/400 (`session_id` required)/404 (unknown
   session) behaviors are unchanged (regression guard, mirrors
   `tests/test_sprint6.py`'s existing export tests).
2. UI wiring: `btnExportText` present in `index.html` and wired in
   `boot.js`; `_appendSessionExportActions` defined in `sessions.js` and
   called from both `_openSessionActionMenu` branches (grep-level, matching
   `test_agent_definitions_ui.py`'s wiring-guard style); i18n keys present
   in all 15 locale blocks.

#### Open questions — RESOLVED 2026-08-10
1. **New backend endpoint vs. extend the existing one** — resolved: extend
   `_handle_session_export`'s `format` switch. A wholly new endpoint would
   duplicate the session-lookup/profile-scoping/redaction logic that's
   already correct there.
2. **Client-side-only vs. server-rendered for Markdown/Text** — resolved:
   server-rendered for the *new* Text format and for any export that isn't
   the currently-open session; the existing client-side `transcript()` (used
   by the pre-existing "Transcript" button) is left untouched since it
   already works and duplicating it into two divergent Markdown renderers
   isn't necessary — the two just happen to produce near-identical output.
3. **Plain-Text formatting** — resolved: same message order/structure as
   Markdown but with `##`/`_..._` markup stripped (`ROLE (timestamp):` plain
   line, no emphasis), so it's readable in a bare text viewer.

**Shipped 2026-08-10:** implemented exactly per the plan above —
`api/session_export_text.py` (new), two new `format=` branches on the
existing `/api/session/export` endpoint, `#btnExportText` in Settings,
`_appendSessionExportActions` replacing the HTML-only sidebar menu helper,
8 new i18n keys × 15 locales, `tests/test_chat_export.py`. No known gaps —
this closes both identified gaps (Text format; non-active-session
Markdown/JSON export) without touching the pre-existing, working
`transcript()`/`btnExportJSON`/`btnExportHTML` code paths.

### Audit Trail UI — STATUS: DONE (shipped 2026-08-10)

Hermes-Studio's `audit/audit-trail-screen.tsx` + `/api/audit` browses a
history of user/agent actions.

hermes-webui has no equivalent screen, but — unlike the other Priority 3
items — it already has the raw data. Two existing journals, both currently
write-only crash-recovery/replay plumbing with no read-side UI:

- **`api/turn_journal.py`** — one append-only JSONL shard per
  `(session_id, pid)` under `_turn_journal/`, written by
  `append_turn_journal_event`/`append_turn_journal_event_for_stream`. Each
  row is a turn lifecycle event: `submitted` (written at
  `api/routes.py:21435`, carries `role, content, attachments, workspace,
  model, model_provider, stream_id, turn_id, created_at`) through to a
  terminal `completed` or `interrupted` (written from ~13 call sites across
  `api/streaming.py`). This is the closest thing hermes-webui has to a
  literal audit log today — `api/session_recovery.py` already labels a
  related boot-time consistency check `audit_only_pending_turn_journal`.
- **`api/run_journal.py`** — one JSONL file per `(session_id, run_id)` under
  `_run_journal/{session_id}/{run_id}.jsonl`, mirroring the full SSE event
  stream (tool calls, tool results, errors, `done`/`cancel`) for reconnect
  replay. Too fine-grained to render row-by-row in an audit view, but
  `latest_run_summary()`/`_summary_from_events()` already reduce a run down
  to `{terminal_state, event_count, last_event, last_seq}` — exactly the
  shape an audit list row needs for a "what happened in this run" line.

**Honest scope limit, not a gap to fix:** both journals are deleted
alongside their session (`delete_turn_journal`/`delete_run_journal`, called
from the session-delete path in `api/routes.py` per #3802 — they hold
plaintext message/request/response content, same privacy reasoning as the
memory-redaction invariant in the Patterns/memory vault cleaner above). So
this is a browsable **recent-activity trail for sessions currently on
disk**, not a permanent tamper-evident audit log independent of session
lifetime. That matches hermes-webui's existing privacy stance (delete a
session, its content is gone) and should not be "fixed" by adding a second,
longer-retention store — note this in the UI copy (e.g. "history clears
when the session is deleted") rather than surprising a user later.

#### Data shape (no new storage — read-only aggregation over existing journals)

A new `api/audit_trail.py`, modeled on `api/session_recovery.py`'s existing
`iter_turn_journal_session_ids` + `read_turn_journal` +
`derive_turn_journal_states` usage (~line 896), not a new storage format:

```json
{
  "session_id": "sess_abc123",
  "turn_id": "20260810T140000Z-a1b2c3d4e5f6",
  "stream_id": "stream_xyz",
  "submitted_at": 1786300000.0,
  "role": "user",
  "content_preview": "Refactor the profile switch endpoint...",
  "model": "claude-opus-5",
  "model_provider": "anthropic",
  "status": "completed",
  "ended_at": 1786300042.5,
  "run_summary": {
    "run_id": "stream_xyz",
    "terminal_state": "done",
    "event_count": 214,
    "last_event": "stream_end"
  }
}
```
`content_preview` is `content` truncated (~200 chars) server-side — the raw
turn journal already stores full plaintext, no new redaction concern, but
the list view should not ship full message bodies over the wire for
sessions with many turns. `status` comes straight from
`derive_turn_journal_states`'s latest event per `turn_id` (`submitted` with
no terminal event yet reads as `"pending"`/`"running"`); `run_summary` is an
optional enrichment via `find_run_summary(turn's stream_id)` — best-effort,
`None` if the run journal was already trimmed/missing (a turn without a run
directory is not an error state, just an older/interrupted-before-stream
turn).

#### API endpoints (`api/routes.py`, next to the `/api/memory`/`/api/skills/scan` blocks)

- `GET /api/audit?session_id=<sid>` → `{"entries": [...]}` for one session,
  newest-first, reusing `iter_turn_journal_session_ids` scoped to a single
  `sid` isn't needed — just call `read_turn_journal(sid)` directly and 404
  if there's no journal at all (empty journal for an existing session is a
  valid empty-list response, not a 404).
- `GET /api/audit?limit=50` (no `session_id`) → cross-session recent
  activity, newest-first, capped (`limit` clamped 1–200, default 50) —
  iterate `iter_turn_journal_session_ids(session_dir)`, read each, take the
  terminal-or-latest event per turn, merge-sort by `submitted_at`, truncate.
  Cross-session iteration cost is bounded by how many *distinct sessions
  currently have a turn-journal shard on disk* (pruned on session delete, so
  this does not grow unboundedly the way a real audit table would) — still
  worth a cheap cap (e.g. only scan the N most-recently-modified journal
  files by mtime before parsing) so a profile with thousands of old sessions
  doesn't make the no-`session_id` view scan every shard on every request.
- Profile-scoped like every other endpoint here (`session_dir` already
  resolves per active profile via the existing profile-switch mechanism —
  no new isolation logic needed, same as Personas' storage decision above).

#### Frontend hook-in

- `static/index.html`: new nav tab (`data-panel="audit"`, label **"Activity"**
  or **"History"** — "Audit Trail" reads as a compliance feature and may
  overpromise; final naming is an open question below) next to Kanban/
  Sessions; panel container with a session filter dropdown (defaults to
  "All sessions", reusing the existing session-picker dropdown pattern
  already used elsewhere) and a flat list `#auditList`.
- `static/panels.js`: `loadAuditTrail(sessionId?)`, `renderAuditEntries`,
  `_auditEntryRow` (turn preview + status badge + relative timestamp,
  expandable to show the `run_summary` line) — same list-row idiom as the
  Kanban office-view worker cards, not a new visual language.
- No slash command planned — this is a browse/inspect surface, not
  something you'd script through chat (unlike Personas/Skills, which have
  create/apply actions worth a `/command`).
- `static/i18n.js`: new keys across all 15 locale blocks (nav label, empty
  state, status labels: pending/running/completed/interrupted/error).

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)

1. `tests/test_audit_trail_api.py`: single-session and cross-session
   listing, empty-journal-vs-no-journal distinction (200 empty list vs 404),
   `content_preview` truncation, `run_summary` enrichment present/absent,
   `limit` clamping, profile isolation (mirrors the Personas profile-
   isolation test).
2. `tests/test_audit_trail_ui.py`: nav tab + panel wiring, locale-key
   parity, CSS theme-token guard (same shape as the three shipped Priority 1
   items' UI test files).
3. A regression test asserting deleted-session journals do NOT appear in
   the cross-session view (proves the read side respects the existing
   `delete_turn_journal`/`delete_run_journal` privacy behavior rather than
   caching stale entries).

#### Open questions — RESOLVED 2026-08-10

1. **Naming** — resolved: shipped as **"Activity"** (nav label, `tab_audit`
   i18n key). Internal module/route names stay `audit_trail`/`/api/audit` —
   same "internal name can differ from the user-facing label" split as
   Personas.
2. **Cross-session view cost at scale** — resolved: shipped with the
   mtime-capped scan as planned (`_recent_turn_journal_session_ids`, cap
   200 shards), not benchmarked against a real large profile yet. Revisit
   if that turns out to be a real bottleneck in practice.
3. **Does `run_summary` belong in v1?** — resolved: **scoped down**, not cut
   entirely. `run_summary` enrichment ships only on the single-session view
   (`read_session_audit_trail`) where the per-turn `find_run_summary` glob
   cost is bounded by one session's turn count. The cross-session view
   (`read_recent_audit_trail`) intentionally omits it — turn-level status
   only — so a poll of "recent activity across sessions" never pays that
   cost per turn per session.

**Shipped 2026-08-10:** new `api/audit_trail.py` — pure reduction functions
over `session_dir`, no new storage. `_group_turn_events()` groups raw
turn-journal events by `turn_id` keeping the original `submitted` event
(content/model/attachments) separate from the latest terminal event
(completed/interrupted), so a terminal overwrite never loses the
submission's detail the way a plain latest-event-wins reduction
(`derive_turn_journal_states`) would have. `GET /api/audit?session_id=<sid>`
(404 if the session file doesn't exist, empty list if it exists with no
journal yet) and `GET /api/audit?limit=` (cross-session, capped 1-200,
default 50) both wired into `api/routes.py` next to `/api/memory`. UI: new
"Activity" nav tab (rail + mobile sidebar), panel with a session-filter
`<select>` populated from the loaded entries' distinct session ids, and a
flat `#auditList` of status-badged entry cards (running/completed/
interrupted, themed via CSS variables) — same list-row idiom as the Kanban
office-view cards. No slash command (browse/inspect surface, matches the
plan). 7 new i18n keys across all 15 locales. Tests: `tests/
test_audit_trail_api.py` (13 cases — turn grouping/detail-preservation,
content-preview truncation, sort order, run_summary presence/absence in
each view, limit clamping, the deleted-session regression guard, route
wiring) and `tests/test_audit_trail_ui.py` (10 structural guards) — all
passing, plus the full locale-parity suite (10 language files + the
language-dropdown-all-locales test) with no regressions. `ruff check`
clean on `api/audit_trail.py`; no new findings introduced in the touched
`api/routes.py` region.

#### Critical files

- `api/audit_trail.py` (new)
- `api/routes.py`
- `static/panels.js`
- `static/index.html`
- `static/i18n.js`
- `static/style.css`

### Sound notification system — STATUS: DONE (shipped 2026-08-10)

Hermes-Studio synthesizes Web Audio API chimes for agent spawned/complete/
failed, a chat notification, and a "thinking tick," gated by a user toggle.
No audio files, no new dependency — same approach fits hermes-webui exactly.

**Investigated first, not a clean-slate build:** hermes-webui already has a
mature synthesized-chime mechanism, not a gap to fill from zero.
`static/messages.js`'s `playNotificationSound()` (turn complete, called from
the `done` SSE handler at `static/messages.js:6112`) and
`playAttentionSound(key)` (approval/clarify needed, `static/messages.js:5707`/
`:5715`, plus a cross-session sidebar variant at `static/sessions.js:5323`)
already do exactly what's being asked — a short `AudioContext`
oscillator+gain envelope, no file assets — gated by a single existing
profile-scoped toggle: `sound_enabled` (`api/config.py:9292`, already in
`_SETTINGS_BOOL_KEYS` at `api/config.py:9566`), surfaced as
`#settingsSoundEnabled` in Settings → Preferences and mirrored at boot into
`window._soundEnabled` (`static/boot.js:3263`). This **is** "the existing
settings/preferences storage pattern" the task brief points at — reuse it,
do not add a second toggle or a parallel storage key.

**Actual gap, exhaustively checked:** grepped every call site of
`playNotificationSound`/`playAttentionSound` (4 total, listed above) against
hermes-webui's full SSE event surface in `static/messages.js`. Three of
Hermes-Studio's five named chime kinds are genuinely missing:
- **Agent failed** — the `apperror` SSE handler (`static/messages.js:6274`,
  handles rate-limit/quota/auth-mismatch/gateway-auth/model-not-found/
  interrupted/compression-exhausted/tool-limit/no-response) never plays a
  sound today; a turn can fail silently in a background tab.
- **Agent spawned** — the `server_turn_started` SSE handler
  (`static/messages.js:7807`, fires when the server-side cron/goal-drain
  thread starts a turn the browser did not itself POST) never plays a
  sound; this is the closest hermes-webui concept to Hermes-Studio's
  "agent spawned" (a run beginning without the user's direct click).
- **Thinking tick** — no equivalent exists at all.

"Chat notification" and "agent complete" are **already covered** by the
existing `playNotificationSound`/`playAttentionSound` pair — not rebuilt.

#### Data shape
None — purely client-side, reusing the existing `sound_enabled` boolean
(already persisted server-side via `/api/settings`/`settings.json`, already
mirrored to `window._soundEnabled`). No new storage.

#### API endpoints
None — no new endpoint. The existing `POST /api/settings`
(`sound_enabled` field) already covers persistence.

#### Frontend hook-in (`static/messages.js` only)
- `playFailureSound()` — new function next to `playNotificationSound`/
  `playAttentionSound` (~line 8660), same oscillator+gain envelope shape but
  a descending two-tone (mirrors `playAttentionSound`'s existing
  high-to-low interval, distinct frequencies so it's audibly different from
  both existing chimes), gated on `window._soundEnabled`. Called from the
  `apperror` handler for every `d.type` **except** `'cancelled'` (an
  explicit user Stop-click is not a failure and must stay silent — the
  existing card-rendering `isCancelled` branch at `static/messages.js:6326`
  is the exact discriminator to reuse, not a second status parse).
- `playAgentSpawnedSound()` — new function, short single ascending blip,
  gated on `window._soundEnabled`. Called once from the
  `server_turn_started` handler (`static/messages.js:7807`) right after the
  existing `evSid !== sid` / stream-identity guards, so it never fires for
  the tab's own user-initiated sends (those already get
  `playNotificationSound()` on completion, not a spawn chime).
- `playThinkingTickSound()` — new function, a single soft tick (not a
  repeating metronome — a repeating tick while streaming would be an
  obnoxious regression, not a feature). Played **once per stream**, only
  when the tab is backgrounded (reuses the existing
  `_isBackgroundedForBrowserNotification()` helper,
  `static/messages.js:72`, the same check `sendBrowserNotification` already
  gates on) — if you're watching the turn live you can see it thinking and
  don't need an audio cue. Hooked into the `reasoning` handler
  (`static/messages.js:5565`), deduped via a new `window._thinkingTickStreams`
  `Set` keyed by `streamId` (mirrors `playAttentionSound`'s existing
  `_attentionSoundSeenKeys` dedupe pattern) so a long multi-chunk reasoning
  stream ticks exactly once, not per chunk.
- No new i18n keys, no new Settings UI — the existing
  `#settingsSoundEnabled` checkbox and `settings_label_sound`/
  `settings_desc_sound` copy already describe "notification sound" broadly
  enough to cover the three new kinds without misleading copy.

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)
`tests/test_sound_notifications_ui.py` (shape from `test_audit_trail_ui.py`
— read `static/messages.js` as text, slice named functions/handlers with
`str.index`, assert on their bodies):
1. `playFailureSound`/`playAgentSpawnedSound`/`playThinkingTickSound` exist
   and each starts with an `if(!window._soundEnabled) return;` guard (no
   second toggle invented).
2. The `apperror` handler's body calls `playFailureSound()`, and the call
   site is positioned so the existing `isCancelled` branch does not reach
   it (asserted by slicing the handler and checking the call appears
   guarded, not unconditionally at the top).
3. The `server_turn_started` handler's body calls `playAgentSpawnedSound()`.
4. The `reasoning` handler's body calls `playThinkingTickSound()` and that
   function's own body checks `_isBackgroundedForBrowserNotification()`
   before playing (regression guard against it becoming an always-on
   metronome).
5. Regression: no second `sound_enabled`-like key was added to
   `api/config.py`'s `_SETTINGS_BOOL_KEYS` or a new `#settings...Sound...`
   checkbox added to `static/index.html` (proves the existing toggle was
   extended, not duplicated).

#### Open questions — resolved before implementation
1. **Does this need a `Data shape`/`API endpoints` section?** No — noted
   explicitly per the task brief's allowance: purely client-side, riding
   the pre-existing `sound_enabled` toggle end-to-end.
2. **Per-kind toggles (e.g. mute just the thinking tick)?** Rejected —
   Hermes-Studio's own model and hermes-webui's existing settings surface
   both use one master sound toggle; adding four more checkboxes for four
   chime kinds is scope creep past what was asked ("a user-toggleable
   on/off setting", singular).

**Shipped 2026-08-10:** landed per the plan above — three new functions in
`static/messages.js`, all gated on the pre-existing `window._soundEnabled`,
hooked into the three genuinely-silent SSE handlers (`apperror`,
`server_turn_started`, `reasoning`). No backend change, no new settings key,
no new i18n keys. Two implementation-level refinements found while coding,
not deviations from intent: (1) `playFailureSound()`'s `d.type!=='cancelled'`
check is computed directly off the freshly-parsed event body at the top of
the `apperror` handler (covers both the current-session and
backgrounded-session branches with one call site) rather than reusing the
`isCancelled` local, which is declared deeper inside a branch that only
runs for the current session — same discriminator logic, just evaluated
once at the point both branches can see it. (2) `playAgentSpawnedSound()`
additionally skips a `recovered` `server_turn_started` frame (a tab
reconnecting to a turn that already started earlier) — a replay is not a
new spawn, and playing the chime on every reconnect would be a false
positive. Tests: `tests/test_sound_notifications_ui.py` — all passing;
confirmed failing against the pre-change file (the three functions/call
sites did not exist).

#### Critical files
- `static/messages.js`

### Voice input — STATUS: already covered, don't rebuild

**Investigated first, per the task brief.** hermes-webui already has a full,
feature-detected Web Speech API dictation implementation — this is not a gap.
`static/boot.js`'s composer-mic IIFE (~line 673 onward):
- Feature-detects `window.SpeechRecognition||window.webkitSpeechRecognition`
  and a `MediaRecorder`/`getUserMedia` fallback; if **neither** exists it
  returns immediately and the mic button — `#btnMic`
  (`static/index.html:649`), which starts `style="display:none"` in markup
  — is simply never shown. No error, no broken input, exactly the graceful
  degradation the task brief asks for.
- Dictates directly into the real chat composer, `#msg`
  (`static/index.html:638`) — `_commitTranscript()`
  (`static/boot.js:794`) appends (or replaces, per an append/replace user
  preference) recognized text into that exact textarea.
- Goes further than Hermes-Studio's inventory: server-side STT
  (`/api/transcribe`) is tried first when available, with browser
  `SpeechRecognition` and a raw-audio-attach mode as fallbacks; continuous
  vs. single-utterance dictation (auto by touch/coarse-pointer detection, or
  an explicit `hermes-mic-continuous` override); a wake lock while
  recording; hold-to-record; and dedicated i18n error copy for denied/
  no-speech/network/insecure-origin failures (`mic_denied`, `mic_no_speech`,
  `mic_network`, `mic_insecure_origin`).

Building a second, parallel voice-input mechanism here would violate this
repo's own contract (GUIDELINES rule 8, "extend the mechanism, don't copy
it") and would just be a strictly worse duplicate of what already ships.

**No code changed for this item.** No new files, no new test file — a test
asserting pre-existing, unchanged behavior cannot satisfy GUIDELINES rule 6
("must fail before, pass after"; nothing here changed for it to fail
against). No CHANGELOG entry, per this doc's own "skip if nothing was
actually built" convention (see the Kanban mission-event-log precedent
above under "Priority 2 — Multi-agent orchestration").

### Onboarding tour — STATUS: DONE (shipped 2026-08-10)

**Investigated first, exactly as this doc originally flagged.** Read
`api/onboarding.py` (1137 lines) and `static/onboarding.js` (839 lines) in
full before writing any plan. Finding: hermes-webui's onboarding is **only**
the first-run setup wizard — `ONBOARDING.steps =
['system','setup','workspace','password','finish']`
(`static/onboarding.js:1`), a linear form flow (provider/API-key/workspace/
password) rendered in `#onboardingOverlay`. Grepped the whole `static/`
tree for `data-tour|guided-tour|walkthrough|spotlight|react-joyride|joyride`
— zero hits anywhere. There is no react-joyride-style guided walkthrough
that highlights live UI elements (nav tabs, composer, panels) after setup
finishes. This confirms the doc's original open question: it's genuinely
just the wizard, not a tour — so, per this doc's own stated rule, a new
tour gets built (not an "already covered" note).

#### Data shape
One new profile-scoped boolean setting, `tour_completed`, added the exact
same way `sound_enabled`/`onboarding_completed` already are:
`api/config.py`'s settings-defaults dict (`"tour_completed": False,`) and
`_SETTINGS_BOOL_KEYS` (`api/config.py:9539`). No new file, no new storage
shape — rides the existing `settings.json`/`/api/settings` mechanism.

#### API endpoints
None new. Persisted via the existing `POST /api/settings`
(`{"tour_completed": true}`), same call already used for every other
boolean preference.

#### Frontend hook-in
- New file `static/tour.js` (small, dependency-free, matches this repo's
  "no build step, vanilla JS" constraint — `AGENTS.md` explicitly rules out
  adding a framework/dependency for something like this): a minimal
  spotlight-and-tooltip walkthrough engine.
  - `APP_TOUR_STEPS`: an ordered array of `{selectors, titleKey, bodyKey,
    placement}` — `selectors` is an array (not a single selector) because
    this repo renders two parallel nav markups for desktop (`.rail
    .rail-btn.nav-tab`) vs. mobile (`.sidebar-nav .nav-tab`)
    (`static/index.html:155-169` vs. `:176-190`); the engine picks
    whichever candidate is actually visible via `el.offsetParent!==null`
    (the same visibility check already used elsewhere in this codebase,
    e.g. `static/ui.js:5433`), and **skips a step entirely** (moves to the
    next one) if no candidate is visible, rather than erroring or spotlighting
    a hidden element. Six steps: welcome (no target, centered card),
    `#btnNewChat`, `#msg` (composer), the `kanban` nav tab, the `skills`
    nav tab, the `settings` nav tab (copy mentions "Take a tour" lives
    under Settings → Help for replay).
  - Spotlight technique: a `pointer-events:none` ghost `div` positioned via
    `getBoundingClientRect()` over the target, visually cutting it out of
    the dimmed viewport via a large-spread `box-shadow` — no `clip-path`
    polygon math, no DOM reparenting of real app elements. The full-viewport
    overlay container itself (not the spotlight ghost) is the element that
    actually receives clicks, so the highlighted element is **visually**
    cut out but not **interactively** clickable during the tour — a
    deliberate choice, not an oversight: letting a click reach e.g. the
    real Kanban nav tab mid-tour would navigate away and strand the tour
    overlay. Escape / Skip / Next are the only ways to advance or exit.
    (Overlay dim reuses the existing hardcoded-rgba convention, matching
    `.onboarding-overlay`/`.app-dialog-overlay`'s own precedent; border/
    text/accent colors on the tooltip card itself are theme tokens.)
  - Tooltip card: Next/Back/Skip/Done buttons + a "Step N of 6" counter,
    positioned near the target (below if room, else above, horizontally
    clamped to viewport), recomputed on `resize`/`scroll`.
  - `startAppTour()` (manual entry), `_maybeAutoStartAppTour()` (auto entry,
    below), `_endAppTour(completed)` (persists `tour_completed:true` via
    `POST /api/settings` whichever way the tour ends — Done or Skip; only a
    stray click that fails to reach either button, e.g. a page navigation
    mid-tour, does not persist, so the tour is offered again next boot in
    that edge case — acceptable, matches how the onboarding wizard itself
    behaves on an interrupted session).
- `static/boot.js`: auto-trigger hook right after
  `await _onboardingReady;` (`static/boot.js:3676` — the point where the
  setup wizard has either finished, been skipped, or never needed to run),
  calling `_maybeAutoStartAppTour()` if `!window._tourCompleted`. Runs
  regardless of whether the wizard itself ran this boot or was already
  complete from a prior session — this is a distinct, later "orient me in
  the UI" step, not a continuation of setup. `window._tourCompleted` is
  mirrored from `_bootSettings.tour_completed` alongside
  `window._soundEnabled` (`static/boot.js:3263`).
- `static/index.html`: new `#appTourOverlay`/`#appTourSpotlight`/
  `#appTourCard` markup (mirrors `#onboardingOverlay`'s existing
  structure); a third `help-card` in the Settings → Help section
  (`static/index.html:1707-1742`, alongside the existing Documentation/
  Issues cards) — "Take a tour" — `onclick="startAppTour()"` for replay at
  any time, matching this doc's rule 10 ("place a control where it's
  used" — Help is exactly where a user goes looking for orientation, not a
  new top-level nav item for a six-step tour).
- `static/style.css`: new `.app-tour-*` classes, theme-token based for the
  card (`var(--text)`/`var(--muted)`/`var(--accent-bg-strong)`/etc.,
  matching `.onboarding-card`'s existing token usage), hardcoded-rgba dim
  for the backdrop/spotlight cutout only (matching the existing overlay
  convention, not a deviation from it).
- `static/i18n.js`: new keys across all 15 locale blocks — `tour_step_N_title`/
  `tour_step_N_body` (welcome + 5 more), `tour_next`, `tour_back`,
  `tour_skip`, `tour_done`, `tour_step_counter` (`"Step {n} of {total}"`
  shape, matching how other counter strings in this file are templated),
  `settings_help_tour_label`, `settings_help_tour_desc`.

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)
New `tests/test_onboarding_tour_ui.py` (shape from `test_audit_trail_ui.py`):
1. `static/tour.js` exists and defines `APP_TOUR_STEPS`/`startAppTour`/
   `_maybeAutoStartAppTour`/`_endAppTour`; every step's `selectors` entries
   (except the no-target welcome step) reference ids/attributes that are
   actually present in `static/index.html` (proves the step list isn't
   pointing at a typo'd or removed element).
2. `static/boot.js`'s post-`_onboardingReady` region calls
   `_maybeAutoStartAppTour()`, and `window._tourCompleted` is mirrored from
   settings the same way `window._soundEnabled` is (regression guard
   pinning the "no second, parallel settings-loading path" rule).
3. `api/config.py`: `"tour_completed"` present in both the settings-defaults
   dict (default `False`) and `_SETTINGS_BOOL_KEYS`.
4. `static/index.html`: the third Help-section card exists, calls
   `startAppTour()`, and the new overlay/spotlight/card markup exists.
5. Locale-parity: the new keys present in all 15 locale blocks (reuses
   `test_audit_trail_ui.py`'s regex-based per-locale-block slicer).
6. CSS theme-token guard on `.app-tour-card` (border/text/accent must be
   `var(--…)`, no hardcoded hex — the backdrop/spotlight rgba dim is
   explicitly exempted in the test, same as the existing `.onboarding-overlay`/
   `.app-dialog-overlay` precedent, not a gap in the guard).

#### Open questions — resolved before implementation
1. **Auto-show on every boot until dismissed, or once ever?** Resolved:
   once ever, gated by the persisted `tour_completed` flag — matches how
   `onboarding_completed` already behaves for the wizard, and avoids the
   tour becoming a recurring nag.
2. **Should `skipOnboarding()` (the wizard's own Skip button) also suppress
   the tour?** Resolved: no — they're independent flags. A user who skips
   *setup* (still wants to configure a provider later) is not the same
   signal as not wanting a one-time UI orientation; auto-starting the tour
   after either wizard outcome (finish or skip) keeps the behavior simple
   and predictable rather than adding a second conditional path.
3. **Step count / which elements?** Resolved at six (welcome + New Chat +
   composer + Kanban + Skills + Settings) — enough to orient a first-time
   user to the major surfaces without turning into an exhaustive, tedious
   13-tab march through every nav item.

**Shipped 2026-08-10:** landed per the plan above. New `static/tour.js`
(dependency-free spotlight/tooltip engine, six steps), a new
`tour_completed` boolean setting (`api/config.py`, same
defaults-dict/`_SETTINGS_BOOL_KEYS` pattern as every other toggle here), a
`static/boot.js` auto-trigger hooked right after the onboarding-wizard
resolution point, a "Take a tour" Help card for manual replay, new
`.app-tour-*` CSS (theme tokens for the card, matching the existing
hardcoded-rgba dim convention for the backdrop/spotlight only), and 20 new
i18n keys across all 15 locale blocks. **Known gap in the i18n work:** the
new copy ships as identical English text in all 15 locale blocks (satisfies
the enforced key-parity test, matches the precedent already set by the
Kanban office-view keys above) rather than real per-language translation —
translating 20 new strings into 14 languages accurately is out of scope for
what an implementing agent can verify quality of; flagging rather than
shipping a plausible-looking but unverified translation. Tests:
`tests/test_onboarding_tour_ui.py` — all passing, confirmed failing against
the pre-change tree (file/functions/wiring did not exist).
**Known gap, not silently shipped:** step targets are fixed CSS
selectors — a future rename/removal of `#btnNewChat` or a nav tab's
`data-panel` value needs to update `APP_TOUR_STEPS` in lockstep; test #1
above is the regression guard for that, not a runtime auto-heal.

#### Critical files
- `static/tour.js` (new)
- `static/boot.js`
- `static/index.html`
- `static/style.css`
- `static/i18n.js`
- `api/config.py`

---

### Knowledge Browser — STATUS: DONE (shipped 2026-08-10)

Hermes-Studio (`memory/knowledge-browser-screen.tsx`,
`/api/knowledge/{list,read,search,graph}`) has a separate RAG/knowledge-base
browser with list/read/search/graph views, distinct from chat memory.

**Investigation before scoping (per instructions — don't assume
greenfield):** audited every profile-scoped, browsable text source that
already exists on disk or via an existing endpoint:

| Source | Exists today? | Already has a browse UI? |
|---|---|---|
| `MEMORY.md` (`§`-delimited facts) | Yes, real file, `home/memories/MEMORY.md` | Only as one editable blob via the existing **Memory** tab (`/api/memory`, whole-file read/write) — not split into individually browsable/searchable facts |
| `USER.md` / `SOUL.md` | Yes | Same — whole-file editable blob via **Memory** tab |
| Saved prompts (`webui/saved_prompts.json`) | Yes, `{id,label,text}` rows, `/api/prompts` CRUD already exists | No dedicated browse/search screen — only a small quick-insert popup on the chat composer (`#savedPromptsPopup`) |
| Prompt files (`HERMES_HOME/prompts/*.md`) | Yes, real standalone `.md` files, e.g. a user's `glm47-heretic-cybersecurity.md` | **No.** Zero references anywhere in `api/` — completely unexposed today |
| Personas (`agent_definitions.json`) | Yes | Already has full CRUD gallery (Priority 1, shipped) — out of scope here, would be pure duplication |
| Project context (workspace `HERMES.md`/`.hermes.md`/cursor rules) | Yes, but resolved per-*workspace* at request time, no stable list of "all workspaces' docs" exists | Surfaced read-only inside the Memory tab for the *current* workspace only |
| A RAG/vector index, entity graph, or any relationship data | **No.** No embedding store, no fact-extraction, no citation/entity graph exists anywhere in the codebase | — |

**Conclusion:** there is real, substantial knowledge-shaped data to browse —
just not a RAG pipeline or graph. Building a `/api/knowledge/graph` endpoint
would mean fabricating a graph view with no real backing data, which the
task explicitly rules out. **v1 ships list/read/search only, no graph.**

**Scope decision — why MEMORY.md/USER.md/SOUL.md are included even though
a separate Priority 1 effort ("Patterns / memory vault cleaner") also reads
MEMORY.md:** that item is an *edit/curate* UI (split into Patterns vs.
`CORRECTION:` tabs, expand/delete, append via `/api/memory/write`) — a
different concern from a *read-only, cross-type search* index. Knowledge
Browser here adds **no** write path to memory files at all; it only reads
them (through the same redaction the existing `/api/memory` GET already
applies). The two features will likely both parse `§`-delimited entries
independently until whichever lands second refactors the split into a
shared helper — flagged here so that isn't a surprise at merge time, not
blocking either feature.

#### Data shape
Read-only. No new storage — everything is read from files/JSON that already
exist. List item (lightweight, no full content):
```json
{
  "id": "memory:2",
  "type": "memory",
  "title": "Zola's 90-day goals are to finish the honeypot project...",
  "snippet": "Zola's 90-day goals are to finish the honeypot project, polish resume/LinkedIn/GitHub...",
  "source_path": "/home/user/.hermes/memories/MEMORY.md",
  "updated_at": 1754841600.0
}
```
`type` is one of `memory | user | soul | saved_prompt | prompt_file`. Read
response (`GET /api/knowledge/read`) is the same shape plus a full `content`
field (redacted via the existing `_redact_text()` chokepoint, same as
`/api/memory`'s GET). Id scheme:
- `memory:<index>` — one id per `§`-delimited entry in `MEMORY.md` (not the
  whole file as one blob — this is what makes it individually browsable/
  searchable, unlike the Memory tab's whole-file editor)
- `user:0`, `soul:0` — the whole `USER.md`/`SOUL.md` file as one item
- `saved_prompt:<uuid>` — one id per row in `saved_prompts.json`, same `id`
  field the existing `/api/prompts` CRUD already uses
- `prompt_file:<filename>` — one id per `*.md` file directly under
  `HERMES_HOME/prompts/` (non-recursive glob)

Caps: `SEARCH_QUERY_MAX = 200` chars, `SEARCH_RESULTS_MAX = 50` rows,
`PROMPT_FILE_MAX_BYTES = 20_000` (read cap per prompt file, mirrors the
existing `_PROJECT_CONTEXT_MAX_BYTES` pattern in `routes.py`),
`PROMPT_FILE_GLOB_MAX = 200` files scanned, `MEMORY_ENTRY_MAX = 300` `§`
entries indexed (guards against a pathological MEMORY.md). `memory`/`user`
items respect the existing `memory_enabled`/`user_profile_enabled` config
flags (same flags `/api/memory` already honors) — a disabled section is
simply omitted from the list, matching that endpoint's behavior exactly
rather than inventing a second convention.

#### API endpoints (`api/routes.py`, GET block, next to the existing
`/api/memory` route)
- `GET /api/knowledge/list` → `{"items": [...]}` (lightweight rows, no
  `content`)
- `GET /api/knowledge/read?id=<id>` → `{"item": {...with content}}`; 404 if
  the id doesn't resolve against a freshly-recomputed listing (ids are never
  used to build a filesystem path directly from client input — read always
  re-derives the item from the same enumeration `list_items()` uses, closing
  any path-traversal surface by construction, per GUIDELINES rule 5)
- `GET /api/knowledge/search?q=<query>` → `{"query": q, "results": [...]}`;
  400 if `q` is empty; case-insensitive substring match across `title` +
  full `content` (not just the snippet), so a search can find a term buried
  inside a long prompt file even though the list view only shows a short
  snippet

No `/api/knowledge/graph` in v1 — see "Conclusion" above.

#### Storage decision
New file `api/knowledge_browser.py`. Pure read functions
(`list_items()`/`read_item()`/`search_items()`), profile-scoped via the same
`api.profiles.get_active_hermes_home()` mechanism every other profile-scoped
module uses (`agent_definitions.py`, saved prompts). No write functions, no
new files created, no new locking needed — it only ever reads
`memories/MEMORY.md`, `memories/USER.md`, `SOUL.md`, `webui/saved_prompts.json`,
and `prompts/*.md`, all of which already exist independently of this feature.

#### Frontend hook-in
- `static/index.html`: new nav tab (`data-panel="knowledge"`, label
  **"Knowledge"**, rail + mobile sidebar-nav, inline `<svg>` icon) next to
  Memory/Insights; `<div class="panel-view" id="panelKnowledge">` with
  search box `#knowledgeSearch` + list `#knowledgeList` (same skeleton as
  `#agentsList`); `<div id="mainKnowledge" class="main-view">` detail pane
  with `#knowledgeDetailTitle`, `#knowledgeDetailBody`,
  `#knowledgeDetailEmpty` (same skeleton as `#mainAgents`). Read-only: no
  create/edit/delete buttons in the panel head.
- `static/panels.js`: add `'knowledge'` to `MAIN_VIEW_PANELS` and
  `APP_TITLEBAR_KEYS`; add `loadKnowledgeItems`, `renderKnowledgeItems`,
  `searchKnowledgeItems` (debounced, calls `/api/knowledge/search` server-side
  rather than filtering the already-loaded snippet-only list, since a real
  search must see full content), `openKnowledgeItem`/`_renderKnowledgeDetail`.
  Hook into `switchPanel`'s lazy-load dispatch (`if (nextPanel ===
  'knowledge') await loadKnowledgeItems();`), mirroring every other panel.
- `static/i18n.js`: new keys in all 15 locale blocks — key-parity is a
  test-enforced contract (see Tests below).
- No slash command in v1 (unlike Personas) — kept out to hold scope modest;
  can be added later mirroring `/personas` if wanted.

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)
1. HTTP round-trip (`tests/test_knowledge_browser_api.py`): seed real data
   through *existing* endpoints — `/api/memory/write` for memory/user/soul
   sections, `/api/prompts` create/delete for saved prompts — then confirm
   `/api/knowledge/list`/`read`/`search` see it, with cleanup restoring prior
   content.
2. Unit-level (direct module calls, `get_active_hermes_home` monkeypatched
   to a `tmp_path`, mirroring `test_agent_definitions_api.py`'s profile
   isolation test): `prompt_file` items (no HTTP endpoint creates these, so
   this is the only way to test them), `MEMORY.md` splitting into individual
   `§` entries, snippet truncation, search query cap/empty-query rejection,
   `memory_enabled`/`user_profile_enabled` gating, profile isolation (two
   profiles never see each other's items), path-traversal-safe `read_item`
   (an id that doesn't match the current enumeration returns `None`, never
   reads an arbitrary path).
3. Static UI-wiring guards (`tests/test_knowledge_browser_ui.py`, shape from
   `test_agent_definitions_ui.py`): nav tab + panel/main containers present,
   JS functions wired, CSS `showing-knowledge` rule present, locale-parity
   across all 15 blocks.

#### Open questions — resolved 2026-08-10
1. **Include MEMORY.md/USER.md/SOUL.md despite the concurrent Patterns
   effort?** Resolved yes — read-only, additive, no write path added; see
   "Scope decision" above.
2. **Graph view?** Resolved: not in v1, no real data to back it honestly.
   Revisit only if a genuine entity/fact-extraction or embedding-based
   relationship model is ever added elsewhere in the codebase — the graph
   should represent something real, not force-fit MEMORY.md's flat entries
   into an artificial node/edge shape.
3. **Project context (workspace docs)?** Left out of v1 — there is no
   existing "list every workspace's context doc" primitive (resolution is
   always for one workspace, on demand); adding one is a bigger change than
   this modest v1 warrants. Noted as a natural v2 extension.

#### Critical files
- `api/knowledge_browser.py` (new)
- `api/routes.py`
- `static/panels.js`
- `static/index.html`
- `static/i18n.js`

**Shipped 2026-08-10:** implemented exactly per the plan above —
`api/knowledge_browser.py` (list/read/search over memory §-entries, USER.md,
SOUL.md, saved prompts, and standalone prompt files), three
`/api/knowledge/*` GET endpoints in `api/routes.py`, a Knowledge nav tab +
sidebar list + read-only detail pane in `static/index.html`/`panels.js`/
`style.css`, and 10 new i18n keys across all 15 locale blocks. Tests:
`tests/test_knowledge_browser_api.py` and `tests/test_knowledge_browser_ui.py`.
Known gaps (by design, see Open questions): no graph view, no project-context
indexing, no slash command.

### Analytics/cost dashboard — STATUS: DONE (shipped 2026-08-10)

Hermes-Studio (`analytics-screen.tsx`, `cost-store.ts`,
`/api/state-analytics`, `/api/provider-usage`) tracks cost/usage over time,
per provider.

**Investigation before scoping (per instructions — read `usage.py` and
`skill_usage.py` first):** `api/usage.py` is a tiny (26-line) pure helper —
just `prompt_cache_hit_percent()`, no endpoint of its own.
`api/skill_usage.py` is a read-only `.usage.json` reader for the Skills
panel, unrelated to cost/tokens. **Neither is where the historical
dashboard lives.** That dashboard already exists: `_handle_insights()` in
`api/routes.py` (route `GET /api/insights`, ~260 lines) backs the existing
**Insights** nav tab (`static/panels.js` `loadInsights`/`_renderInsights`,
title literally "Usage Analytics"). It already provides, over a selectable
1–365 day window: total cost/tokens/sessions, a daily cost+token trend
chart, a **per-model** cost/token/cache-hit breakdown table with cost/token/
session share percentages, activity-by-day-of-week and activity-by-hour
heatmaps, and merges both WebUI (`_index.json`) and CLI (`state.db`)
sessions. **This directly contradicts this doc's original one-line claim**
("only does live per-turn display metrics, not a historical screen") — that
claim was wrong, and is corrected here rather than repeated.

**The real, narrower gap versus Hermes-Studio's `cost-store.ts`:** Insights
groups exclusively by **model**, never by **provider** — even though the
raw data already carries a provider: WebUI session rows in `_index.json`
already have a `model_provider` field (`api/webui_session_db.py`
`_METADATA_FIELDS`), and CLI rows in `state.db` carry `billing_provider`
(confirmed via `PRAGMA table_info(sessions)` — there is no `model_provider`
column in `state.db`, unlike the WebUI JSON side; the two sources use
different real column names for the same concept). Insights also has no
week/month rollup (only daily) and no "which sessions cost the most"
breakdown, both of which Studio's cost-store-style view implies. This is a
"read-only aggregation over data that already exists on disk" gap exactly
like Audit Trail's — the provider field is already being written, just
never read for this purpose.

**Decision: ship a focused, separate "Analytics" nav tab (as directed) that
is provider-centric and complements Insights rather than duplicating it —
not a second copy of the whole Insights screen.** Insights keeps owning
day-of-week/hour heatmaps and per-model breakdown; Analytics owns
per-provider breakdown, week/month granularity, and a top-spending-sessions
list. Both read the same two underlying sources independently (see Open
question #2 below for why the session-walk isn't shared code).

#### Data shape
Read-only aggregation, no new storage — reads the same `_index.json` +
`state.db` sources `_handle_insights` already reads.
```json
{
  "period_days": 30,
  "granularity": "week",
  "total_sessions": 42,
  "total_tokens": 1250000,
  "total_cost": 12.34,
  "providers": [
    {
      "provider": "anthropic",
      "sessions": 30,
      "input_tokens": 900000,
      "output_tokens": 200000,
      "cache_read_tokens": 50000,
      "cost": 9.87,
      "cost_share": 80,
      "token_share": 88,
      "session_share": 71
    }
  ],
  "trend": [
    {"bucket": "2026-W32", "cost": 3.21, "input_tokens": 300000, "output_tokens": 60000, "sessions": 10}
  ],
  "top_sessions": [
    {"session_id": "abc123", "title": "Refactor auth flow", "model": "claude-opus-4", "provider": "anthropic", "cost": 1.02, "tokens": 45000, "ts": 1754841600.0}
  ]
}
```
Provider derivation: `model_provider` (WebUI rows) or `billing_provider`
(CLI rows) if present; else derived from `model`'s `provider/model` prefix
if it contains `/`; else `"unknown"`. `trend` bucket keys use Python's
`datetime` module (not `time.strftime("%G-W%V")`, which is not reliably
portable to Windows' C runtime — this codebase ships a `start.ps1`, so
portability matters): `%Y-%m-%d` for day, ISO `<year>-W<week>` via
`isocalendar()` for week, `%Y-%m` for month. `top_sessions` is capped at 10,
sorted by cost descending, with `title` passed through the same
`_redact_text()` chokepoint `/api/sessions` already uses for titles.

#### API endpoints (`api/routes.py`, GET block, next to `/api/insights`)
- `GET /api/analytics?days=<1-365>&granularity=<day|week|month>` →
  the shape above. `days` clamps exactly like `/api/insights` (invalid →
  30). `granularity` defaults to `week`; an unrecognized value falls back to
  `week` rather than erroring, matching the codebase's "degrade gracefully
  on bad query params" convention used throughout `routes.py`.

#### Frontend hook-in
- `static/index.html`: new nav tab (`data-panel="analytics"`, label
  **"Analytics"**, rail + mobile sidebar-nav, inline `<svg>` icon — visually
  distinct from the Insights icon) next to Insights; `panelAnalytics` with a
  period `<select id="analyticsPeriod">` (7/30/90/365, mirrors
  `#insightsPeriod`) and a granularity `<select id="analyticsGranularity">`
  (day/week/month); `<div id="mainAnalytics" class="main-view">` rendering
  into `#analyticsContent` (mirrors `#mainInsights`/`#insightsContent`).
- `static/panels.js`: add `'analytics'` to `MAIN_VIEW_PANELS` and
  `APP_TITLEBAR_KEYS`; add `loadAnalytics(animate)`/`_renderAnalytics(d,
  box)`, hooked into `switchPanel`'s lazy-load dispatch. Reuses the existing
  theme-var-only `.insights-card`/`.insights-table`/`.insights-stat` CSS
  classes for the overview/provider-table cards (GUIDELINES rule 8 — extend
  the existing card/table mechanism rather than re-styling from scratch);
  adds a small number of new `.analytics-*` classes (provider bars,
  top-session rows) only where no existing class fits, still theme-var only.
- `static/i18n.js`: new keys in all 15 locale blocks.

#### Tests to write (must fail before, pass after — GUIDELINES rule 6)
1. Unit-level (`tests/test_analytics_dashboard_api.py`, mirroring
   `test_insights.py`'s `_FakeHandler`/monkeypatched-`SESSION_DIR` pattern —
   deliberately not a live-HTTP test, matching how Insights itself is
   tested): provider grouping across multiple sessions with the same/
   different `model_provider`; day/week/month bucket keys for known
   timestamps; top-sessions sorted+capped+redacted; CLI/`state.db` rows
   merged via monkeypatched `_active_state_db_path`, exercising both
   `billing_provider` present and `NULL` (falls back to model-prefix
   derivation); `days`/`granularity` param clamping and defaults; empty
   state (no sessions) returns zeros/empty lists without raising.
2. Static UI-wiring guards (`tests/test_analytics_dashboard_ui.py`): nav tab
   + panel/main containers present, JS functions wired, `'analytics'` in
   `MAIN_VIEW_PANELS`, CSS `showing-analytics` rule present, locale-parity
   across all 15 blocks.

#### Open questions — resolved 2026-08-10
1. **Duplicate Insights entirely, or build something narrower?** Resolved:
   narrower and complementary — see "Decision" above. Revisit only if user
   feedback wants Insights and Analytics merged into one screen.
2. **Share the session-walk code between `_handle_insights` and the new
   handler?** Considered and **declined** for this change: `_handle_insights`
   already has ~500 lines of passing tests (`tests/test_insights.py`,
   `tests/test_issue691_model_health_table.py`) and refactoring it to share
   a generator is a real behavior-preserving-refactor risk that is out of
   scope for "add a new read-only endpoint" (GUIDELINES rule 9 — the diff is
   the task and nothing else). The new handler independently re-walks the
   same two sources with its own compact aggregation. Flagged as a
   worthwhile follow-up cleanup once both are stable, not done here.
3. **`billing_provider` vs `model_provider` naming split** — resolved as
   documented above: the two data sources genuinely use different column
   names for the same concept (confirmed via `PRAGMA table_info`), so the
   handler reads whichever field its source actually has rather than
   assuming one name everywhere.

#### Critical files
- `api/routes.py`
- `static/panels.js`
- `static/index.html`
- `static/i18n.js`

**Shipped 2026-08-10:** implemented exactly per the plan above — a new
`_handle_analytics()` in `api/routes.py` behind `GET /api/analytics`, an
Analytics nav tab + period/granularity controls + provider breakdown/trend/
top-sessions view in `static/index.html`/`panels.js`/`style.css`, and 19 new
i18n keys across all 15 locale blocks. Tests:
`tests/test_analytics_dashboard_api.py` and
`tests/test_analytics_dashboard_ui.py`. Known gap (by design, see Open
question #2): the session-walk logic is intentionally not shared with
`_handle_insights` to avoid touching its tested code; a future cleanup could
extract a common helper once both handlers are stable.

---

## Priority 4 — overlapping features, Hermes-Studio's approach worth borrowing

- **Skills**: hermes-webui's usage-tracking (`skill_usage.py`) is more
  precise than Hermes-Studio's (real `.usage.json` stats vs. none). What's
  missing on hermes-webui's side is the *discovery* half: a tabbed
  Installed/Marketplace/Featured browser with category filters over 2,000+
  skills, install flow, and the security scan card (Priority 1).
- **Approvals**: both have the backend concept (hermes-webui:
  `route_approvals.py`, SSE-based). Worth checking whether hermes-webui's
  approval UI is as prominent/blocking as Hermes-Studio's modal — their
  `SECURITY.md` treats the blocking approval modal as a core safety feature,
  not just a UX nicety.
- **Terminal**: hermes-webui already has `terminal.py`/`terminal.js`.
  Hermes-Studio's is a Python `pty-helper.py` + xterm.js with fit/search/
  web-links addons, keepalive pings every 8s, SIGWINCH-based resize. Worth
  diffing addon support and resize handling specifically.
- **Kanban / task board**: hermes-webui's `kanban_bridge.py` vs.
  Hermes-Studio's `tasks.tsx`/`tasks-screen.tsx` with a dedicated
  `/api/tasks/$taskId/move` endpoint for drag-move-between-columns. Check
  whether hermes-webui's board already supports this cleanly.
- **Jobs/cron**: hermes-webui already has scheduling primitives (daily/
  hourly/weekly/monthly/custom, visible in `panels.js`) — same territory as
  Hermes-Studio's `jobs.tsx` (create/edit dialogs, pause/resume/trigger,
  output viewer). Confirm hermes-webui's output-viewer and pause/resume are
  equally complete.
- **PWA**: both have `manifest.json` + `sw.js`. Hermes-Studio adds three
  user-configurable **mobile chat nav modes** (dock/integrated/scroll-hide) —
  worth stealing if hermes-webui's mobile nav is fixed/single-mode.
- **Gateway capability probing** (`gateway-capabilities.ts`): a two-tier
  Core-vs-Enhanced capability set, cached with a 30s TTL probe, with UI
  features gating themselves off gracefully (`use-feature-available.ts`) when
  the gateway doesn't support something. Clean pattern worth adopting for
  hermes-webui if it ever runs against gateways with varying capability
  levels (e.g. mid self-update, degraded states) instead of hard-failing.
- **Modes system**: named presets of model + suggestion settings
  (save/apply/rename), with drift detection when live settings diverge from
  the applied mode. Distinct from hermes-webui's existing `profiles.py` —
  worth checking whether profiles already cover this or are workspace/account
  level only.
- **Security posture as three layers, not an afterthought**: Hermes-Studio
  ships a `SECURITY.md`, a dedicated `security.yml` CI workflow (gitleaks +
  regex secret-pattern fallback on every PR), and skill-level content
  scanning (Priority 1) — repo hygiene, CI, and runtime scanning all aimed at
  the same "don't let untrusted content compromise the agent" concern. Worth
  adopting the same three-layer shape.

---

## hermes-webui advantages (keep, don't lose in the rewrite)

- **Git worktrees** (`worktrees.py`) — Hermes-Studio has nothing equivalent.
- Skill **usage tracking** is more accurate/real than Hermes-Studio's
  (see Priority 4 above).

---

