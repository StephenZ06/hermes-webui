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

**Done, all on `feature/plan-canvas`, all uncommitted as of this writing —
check `git status` before assuming any of this is merged:**
- Priority 1, all four items: Personas (+ apply-to-session v1.1), Security
  scanner, Patterns/memory vault cleaner, and Audit Trail UI (technically
  Priority 3, shipped alongside these — see its own section below).
- Priority 2, Phases 1 and 2 of Multi-agent orchestration ("Crews"): crew
  templates + bulk dispatch (plus its dispatch-variables-dialog follow-up),
  and office-view crew grouping. See "Priority 2 — Multi-agent
  orchestration" below for both "Shipped" notes.
- Priority 2, Phase 1.2: a scoped-down "templates gallery" slice — search/
  filter over the crew list plus a "last dispatched" recency signal driving
  default sort order. See that section for why a categories/tags gallery was
  investigated and rejected as unnecessary polish rather than built.

**Explicitly deferred, not forgotten:** Priority 2 Phase 3 (cost panel) —
decided 2026-08-10 to cut it for now rather than ship fabricated/approximate
cost numbers. See Phase 3's section below before touching this; the decision
of *which* follow-up path (upstream fix vs. labeled approximation) is still
open and needs a human call, not an implementing agent's guess.

**Not started, no written plan yet:** the workflow-builder/step-graph-editor
part of Priority 2 remains explicitly out of scope (see "Investigated and
rejected" below — unchanged); Phase 3's cost panel stays deferred; all of
Priority 3 except Audit Trail (Knowledge Browser, Analytics/cost dashboard,
Command palette, Chat export, Sound notifications, Voice input, Onboarding
tour), and all of Priority 4 (Skills marketplace discovery is flagged as
the natural next pick — it's the gate the Security scanner was explicitly
built for).

**Suggested next pick:** Priority 4's Skills marketplace discovery — with
Phase 1/1.2/2 of Crews shipped and the workflow-builder/step-graph part of
Priority 2 staying explicitly out of scope, there is no further conservative
Priority 2 slice queued up; revisit Priority 2 only if a genuinely new,
concrete gap surfaces (not "build the gallery bigger just because"). Before
starting *anything*, read the "Shipped" notes for whichever area you're
touching — they carry the actual design reasoning (why a decision was made
a certain way), not just what shipped.

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

#### Phase 3 (DEFERRED — decided 2026-08-10) — Cost panel

**Decided 2026-08-10: option 3, cut for now.** No code was written for this
phase. Explicitly deferred pending either an upstream `hermes-agent-src`
change (option 1 below) or a future decision to accept the approximate
heuristic (option 2 below) — not abandoned, just not started. Re-read this
whole subsection before picking it up; the reasoning below is still current
as of the decision date.

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

Decided: (3). If you're picking this phase back up, the remaining open
question is which of (1)/(2) to build next — do not silently choose the
heuristic and ship it as if it were accurate; that call still needs a human.

**Open questions for Phase 3 (still open — (3) only decided to defer, not
which of (1)/(2) comes next):**
1. Is a `hermes-agent-src` PR for option (1) realistic/desired, or is
   option (2)'s approximation acceptable given the UI can label it clearly?
2. If/when cost data exists: should Personas apply to kanban-dispatched
   workers at all? `assignee`/profile and `agent_definition_id`/persona are
   currently unconnected — a Persona's system prompt is only ever injected
   into the webui chat path (`api/streaming.py`/`api/gateway_chat.py`),
   never into a kanban-dispatched CLI worker. A cost panel naturally
   invites also showing "which persona/role" a worker ran as, and today
   there is no such concept for a CLI-spawned kanban worker.

---

## Priority 3 — other confirmed gaps

- **Knowledge Browser** (`memory/knowledge-browser-screen.tsx`,
  `/api/knowledge/{list,read,search,graph}`) — separate RAG/knowledge-base
  browser with a graph view, distinct from chat memory. No equivalent today.
- **Audit Trail UI** — planned, see full write-up below.
- **Analytics/cost dashboard** (`analytics-screen.tsx`, `cost-store.ts`,
  `/api/state-analytics`, `/api/provider-usage`) — cost/usage tracked over
  time, per provider. hermes-webui's `usage.py` only does live per-turn
  display metrics, not a historical screen.
- **Command palette** (⌘K, `cmdk`-style) + global keyboard-shortcuts modal —
  no discoverable global command palette found in hermes-webui.
- **Chat export** (`export-menu.tsx`) — Markdown/JSON/Text export, no
  equivalent found.
- **Sound notification system** — synthesized Web Audio API chimes (agent
  spawned/complete/failed, chat notification, thinking tick), no audio
  files needed.
- **Voice input** (Web Speech API, `use-voice-input.ts`/
  `use-voice-recorder.ts`) — not present.
- **Onboarding tour** — hermes-webui has `onboarding.py`/`onboarding.js`;
  worth checking whether it's a guided step-by-step *tour*
  (`react-joyride`-style, like Hermes-Studio has in addition to a setup
  wizard) or just the wizard.

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

