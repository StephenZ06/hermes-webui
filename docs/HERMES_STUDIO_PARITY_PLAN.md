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

## Priority 1 — already planned, confirmed as real gaps

### Personas (internal name: Agent Library / `agent_definitions`) — STATUS: planned, ready to implement (not started)

**Decided 2026-08-08:** user-facing name is **"Personas"** (resolves open
question #1 below — avoids collision with this codebase's existing use of
"agent" for the running Hermes process). Internal module/route/data names
stay `agent_definitions`/`/api/agent-definitions` as already planned; only
UI-visible strings (nav label, panel title, slash command, i18n keys) say
"Personas". **v1 ships with no apply-to-session** (resolves open question
#2 below) — pure browsable/editable library, no `streaming.py` chokepoint
changes.

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
   **v1 has no apply-to-session.** Pure browsable/editable library only;
   `streaming.py`'s `_webui_ephemeral_system_prompt()` chokepoint is not
   touched in v1. Revisit if a future session wants to select a Persona to
   actually change the running system prompt — at that point extend the
   existing chokepoint rather than adding a second prompt-injection path.
3. Storage/built-ins decisions above are made, not open — flagged only so a
   future "view across all profiles" or "hide a builtin per-profile"
   feature request doesn't get surprised by the current design's limits.

#### Critical files
- `api/agent_definitions.py` (new)
- `api/routes.py`
- `static/panels.js`
- `static/index.html`
- `static/i18n.js`

### Security scanner
Hermes-Studio (`skills-screen.tsx` `SecurityScanCard`, `SecurityRisk` type:
`level: safe|low|medium|high`, `flags[]`, `score`) statically scans every
marketplace skill for risky patterns before install and shows a risk card.

hermes-webui's `skill_usage.py` only reads `.usage.json` for display stats —
no scanning, no risk level, no flags.

Ties directly into the **Skills marketplace gap** below — the scanner is the
natural gate on top of a marketplace browse/install flow hermes-webui doesn't
have yet either.

### Patterns / memory vault cleaner
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

---

## Priority 3 — other confirmed gaps

- **Knowledge Browser** (`memory/knowledge-browser-screen.tsx`,
  `/api/knowledge/{list,read,search,graph}`) — separate RAG/knowledge-base
  browser with a graph view, distinct from chat memory. No equivalent today.
- **Audit Trail UI** (`audit/audit-trail-screen.tsx`, `/api/audit`) —
  hermes-webui already has the raw data (`turn_journal.py`, `run_journal.py`)
  but it's crash-recovery/replay plumbing, never surfaced as a browsable UI.
  Likely the cheapest win in this list — data already exists.
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

## Suggested starting point

Personas (internal: Agent Library) first — it's self-contained (no
dependency on the orchestration work), was already on the plan before this
comparison, and is a clean vertical slice. **Full implementation plan is
written up under "Priority 1 — Personas" above and is ready to build from —
all open questions resolved 2026-08-08 (name: Personas; no
apply-to-session in v1).**

Implement in this order: `api/agent_definitions.py` → `api/routes.py`
endpoints → tests → `static/panels.js` + `index.html` + `i18n.js` (all 15
locales, label text "Personas") → manual verification per `TESTING.md`.
