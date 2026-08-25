# Project Workspace Binding

Date: 2026-08-26
Status: Draft (pre-approved by user; proceeding to implementation under
`/unsupervised` — recommended options chosen throughout, see decision log
below)

## Problem

The sidebar "Project" feature (`project_id`, `static/sessions.js`,
`load_projects()`/`save_projects()` in `api/routes.py`) groups chats into
named folders with a color and a three-dot menu (Rename / color / Delete).
It has no notion of a filesystem location — chats filed into a Project keep
whatever `session.workspace` they already had, and a brand-new chat created
inside a Project gets whatever the normal default-workspace logic picks,
unrelated to the Project itself.

Goal: let a Project be bound, once, to a local workspace folder, so every
chat that belongs to that Project — existing, newly created, or later moved
in — defaults to that folder as its workspace.

## Non-goals (explicitly decided during brainstorming, not oversights)

- **Not** the separate `bound_project_key` / `WORKSPACES.yaml` registry
  feature (see `docs/superpowers/specs/2026-08-14-project-bound-chats-design.md`).
  That feature binds one *chat* to a *curated registry* project and
  force-injects system-prompt context every turn. This feature binds a
  *Project folder* (the sidebar grouping) to an arbitrary local path picked
  from the same workspace list/picker used elsewhere in the app, and only
  changes `session.workspace` — no system-prompt injection, no
  `project-lifecycle` skill force-preload. The two features are independent
  and can coexist on the same session (a session can have both a
  `project_id` with a bound workspace *and* a separate `bound_project_key`,
  though that combination is unusual).
- **No retroactive undo chain.** The registry feature captures
  `pre_bind_workspace` so unbinding restores the prior workspace. This
  feature does not: clearing a Project's bound workspace leaves member
  sessions' `workspace` exactly where it was (whatever the last bind set it
  to, or whatever they had before if never touched). Simpler data model,
  explicitly chosen over the undo-chain complexity for this lower-stakes
  feature.
- **No remote/SSH workspace binding.** Local paths only, matching the
  existing local workspace picker. SSHFS remote workspaces (see the
  2026-08-22 spec) are out of scope here.
- **No new persistent sidebar chrome.** A bound path gets a title/tooltip on
  the Project chip at most — no new always-visible icon row, badge system,
  or expanded folder metadata display.

## Background: what already exists

- **Project data model** (`api/routes.py`, `load_projects()`/
  `save_projects()`): a flat JSON list of
  `{project_id, name, color, profile, created_at}`. No workspace field
  today. CRUD lives at `POST /api/projects/create|rename|delete|merge`.
- **Session-to-project assignment**: `Session.project_id` (`api/models.py`),
  set via `POST /api/session/new` (body `project_id`, read around line
  14974 in the `/api/session/new` handler) or moved via
  `POST /api/session/move` (`api/routes.py:16869`).
- **Bulk project-session repointing pattern**: `_reassign_project_sessions()`
  (`api/routes.py:14335`) already solves "update a field on every session in
  project X" safely — reads `SESSION_INDEX_FILE`, and for each matching
  session either updates the live cached `Session` object under `LOCK` (if
  it has an active stream, deferring the actual disk write to the
  streaming thread's own next checkpoint/final save) or calls
  `get_session()` + direct `s.save()` otherwise. Used today by
  `/api/projects/delete` (unassign) and `/api/projects/merge` (repoint).
  This feature's bulk-apply-workspace step reuses the same pattern with
  `workspace` as the field instead of `project_id`.
- **Single-session safe update pattern**: `/api/session/move` acquires the
  per-session lock via `_get_session_agent_lock(...).acquire(timeout=5)`,
  returning `503` if a stream is actively writing, rather than blocking
  indefinitely or racing the streaming thread's writer. Reused for the
  "moving a session into an already-bound Project" case.
- **Workspace trust gate**: `resolve_trusted_workspace()` /
  `is_blocked_system_path()` (already used by both the registry
  bind-project feature and the plain workspace-create form) is the existing
  chokepoint that keeps `session.workspace` from ever pointing outside an
  allowed root. Reused here rather than adding a second path-validation
  path.
- **Existing folder-picking UI**: `openWorkspaceCreate()` /
  `_renderWorkspaceForm()` (`static/panels.js`) — a path text field with
  live autocomplete suggestions (`_wireWorkspaceFormPathSuggestions()`)
  drawn from already-known workspaces, server-validated on save. This is
  the "existing workspace picker" reused for binding, not a new custom
  filesystem browser (browsers can't natively browse a *server's*
  filesystem; this codebase's existing answer to that is the suggestion
  list + validated text input, so this feature follows suit).
- **Project context menu**: `_showProjectContextMenu()`
  (`static/sessions.js:9763`) — Rename, then a color-dot row, then a
  divider and Delete. The new "bind workspace" entry point goes above
  Rename, per the user's own request.

## Design

### 1. Data model

- `projects.json` entries gain an optional field: `workspace_path: str |
  null`. Absent/`null` = unbound (current behavior, zero change for every
  existing Project until someone opts in).

### 2. Backend API

**New endpoint: `POST /api/projects/set_workspace`**
Body: `{project_id, workspace_path}` (`workspace_path: null` to unbind).

1. Validate `project_id` exists (`load_projects()`, same lookup pattern as
   `/api/projects/rename`).
2. If `workspace_path` is non-null: resolve and validate it through
   `resolve_trusted_workspace()` then `is_blocked_system_path()`, exactly as
   the registry bind-project feature does for its local-path branch
   (`api/routes.py:15290-15302`). Reject with `400` on failure, same error
   shape as that existing code.
3. Persist `workspace_path` on the project entry via `save_projects()`.
4. Bulk-apply to every current member session: new helper
   `_apply_project_workspace(project_id, workspace_path)`, modeled directly
   on `_reassign_project_sessions()` — same `SESSION_INDEX_FILE` scan, same
   active-stream cache-vs-disk branching, same per-session try/except so one
   slow/broken session can't abort the batch. Sets `s.workspace` instead of
   `s.project_id`. Returns the count updated (mirrors the existing
   function's return contract).
5. Respond `{"ok": true, "project": <updated project dict>,
   "sessions_updated": <count>}`.

**`POST /api/session/new`** (`api/routes.py`, around line 14859): after the
existing `workspace = ... if body.get("workspace") else None` resolution and
before the worktree-default branch, add: if `workspace` is still `None` and
`body.get("project_id")` names a project with a non-null `workspace_path`,
default `workspace` to that (through the same trust gate already applied to
`body.get("workspace")` — belt-and-suspenders even though the stored value
was validated at bind time, since a project file could in principle be
hand-edited). An explicit `workspace` in the request body still wins — this
only fills in the *default*, matching how `body.get("workspace")` already
takes priority over other fallbacks in this handler.

**`POST /api/session/move`** (`api/routes.py:16869`): after `s.project_id =
target_pid` and before `s.save()`, if `target_pid` is set and that project
has a non-null `workspace_path`, also set `s.workspace` to it. Uses the
lock already held by this handler — no new locking needed here, unlike the
bulk endpoint above.

### 3. Frontend

- `_showProjectContextMenu()` (`static/sessions.js`): new item **"Workspace
  Folder"** inserted above the existing Rename item. Shows the current bound
  path (or "Not set") in its label/title so a glance at the menu tells you
  the state without opening anything.
- Clicking it opens a small inline picker (not a full page/panel switch,
  unlike `openWorkspaceCreate()`): a text input with the same
  `_wireWorkspaceFormPathSuggestions()`-style autocomplete against known
  workspaces, pre-filled with the current bound path if any, plus a "Clear"
  action to unbind. Save calls `POST /api/projects/set_workspace`, then
  refreshes the session list (member sessions' workspace chips may have
  changed) and shows a toast including the `sessions_updated` count (e.g.
  "Workspace bound · 4 chats updated") so the "switch existing chats too"
  behavior is visible, not silent.
- Project chip gets a `title` attribute with the bound path when set (cheap,
  no new persistent chrome, satisfies "no new UI clutter" while still making
  the binding discoverable on hover).

### 4. Edge cases

- **Active stream in a member session** at bind time: handled by
  `_apply_project_workspace`'s reuse of `_reassign_project_sessions`'s
  existing cache-vs-disk branch — never races the streaming thread's writer.
- **Active stream in the single session being moved**: `/api/session/move`
  already bounds its lock acquisition at 5s and returns `503` rather than
  blocking or racing; the new workspace-set piggybacks on that same
  already-held lock, no new failure mode introduced.
- **Invalid or since-removed path** at bind time: same `400` + message shape
  the registry feature and the workspace-create form already use — no new
  error UX to design.
- **Sessions with no `project_id`**: entirely untouched, no behavior change.
- **Unbinding** (`workspace_path: null`): future new/moved-in sessions to
  that Project stop getting a default; current member sessions' `workspace`
  is left exactly as it is (see Non-goals — no undo chain).

## Decision log (brainstorming, all recommended options chosen with
user's explicit blanket pre-approval before stepping away)

1. Target feature: the sidebar Project folder (`project_id`), not the
   `WORKSPACES.yaml` registry feature — confirmed against the described
   three-dot/Rename menu.
2. Existing member sessions: binding a workspace **does** retroactively
   switch every session currently in that Project, not just future ones.
3. Folder picker: reuse the existing workspace-picker/autocomplete
   mechanism, not a freeform-only text box.
4. Depth of "focus": workspace default only (`session.workspace`) — no
   system-prompt/context force-injection like the registry feature has.
