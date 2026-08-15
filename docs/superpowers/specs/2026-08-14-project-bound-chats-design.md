# Project-Bound Chats

Date: 2026-08-14 (updated 2026-08-15 to match what was actually implemented)
Status: Implemented

## Problem

`project-lifecycle` (a Hermes skill) resolves an authoritative project from
`WORKSPACES.yaml` when the user *names* the project in the task text. It has
no notion of "this chat already belongs to project X" — every turn requires
re-stating the project, and nothing stops the agent from acting in the wrong
folder if the task text doesn't mention one, or mentions one ambiguously.

The only existing "auto-detect project from chat" logic is the
`project-lifecycle-preload` plugin, which infers a project from Discord
channel/category metadata. It doesn't cover WebUI chats at all, and even
where it applies it's a guess (channel name matching), not an enforced
binding.

Goal: let a WebUI chat be explicitly bound, once, to a `WORKSPACES.yaml`
project. Every subsequent turn in that chat carries the resolved,
authoritative project context and forces the agent to operate under
`project-lifecycle` for that project — deterministically, not via semantic
skill selection or title/channel guessing. Unbound chats are unaffected.

## Non-goals

- No changes to `hermes-core`, the `project-lifecycle` skill itself, or the
  Discord `project-lifecycle-preload` plugin.
- No remote (SSH) *terminal* — an interactive remote shell is a separate,
  much larger feature with its own risk profile and stays out of scope.
  (Read-only SSH *file browsing* for bound SSH projects was added — see
  "SSH read-only file browsing" below; this was a scope change from the
  original draft, made explicitly after the rest of this feature shipped.)
- No change to `session.workspace` behavior for chats that are not bound to
  a project.

## Background: what already exists

- `hermes` (agent) container and `hermes-webui` container share one Docker
  volume (`hermes-stack_hermes_data`), mounted at `/opt/data` in `hermes`
  and `/home/hermeswebui/.hermes` in `hermes-webui`. WebUI can read
  `WORKSPACES.yaml` and any skill's `SKILL.md` directly off disk — no
  cross-container API call needed.
- `WORKSPACES.yaml` (at `<state_dir>/hermes-workspaces/WORKSPACES.yaml`) is
  a registry of named projects, each with `repo_path` (local) or SSH target
  info, `access_mode`, `status` (e.g. `NEEDS_CONFIRMATION` for
  unconfirmed/candidate entries), and `required_docs`.
- `project-lifecycle`'s `SKILL.md` lives at
  `<state_dir>/skills/project-lifecycle/project-lifecycle/SKILL.md` and is
  plain, readable text — the whole skill is one file.
- `Session` (api/models.py) already has a `workspace` field: an absolute
  local folder path used by WebUI's file explorer/terminal/tool sandbox.
  This is unrelated to `WORKSPACES.yaml` — it's WebUI's own "last folder you
  browsed to" convenience, backed by `workspaces.json` / `load_workspaces()`
  / `get_last_workspace()` in `api/workspace.py`.
- Every chat turn — both the gateway-routed path (`api/gateway_chat.py`)
  and the direct streaming path (`api/streaming.py`) — builds its
  WebUI-only system prompt through a single shared function,
  `_webui_ephemeral_system_prompt()` (`api/streaming.py:740`). This is
  already how persona system prompts, surface context (source/session/
  workspace), and delivery context get injected. It's the natural single
  point to add bound-project context, reached by both code paths with no
  duplicated logic.

## Design

### 1. Data model

- New `Session` field: `bound_project_key: str | None`. Value is a
  `WORKSPACES.yaml` project key (e.g. `"job-os"`), never a raw path.
  `None` means unbound — chat behaves exactly as it does today.
- For a **local** (`access_mode: local`) bound project, `session.workspace`
  is server-set to the registry's resolved `repo_path` at bind time, and
  re-asserted (not just defaulted) on every load while the binding holds —
  it is not client-writable while `bound_project_key` is set. This is the
  actual enforcement: WebUI's own file explorer/terminal/tool sandbox
  cannot drift outside the bound project.
- For an **ssh**-mode bound project, `session.workspace` is left alone
  (there is no local path to lock to). WebUI's local-filesystem panels
  will simply have nothing relevant to show for that chat.

### 2. Registry resolution — new module `api/project_registry.py`

- `list_registry_projects() -> list[dict]`: parses `WORKSPACES.yaml` off
  the shared volume, cached with mtime-based invalidation (same pattern as
  `load_workspaces()` in `api/workspace.py`). Each entry normalized to:

  ```
  {
    key: str,
    name: str,
    access_mode: "local" | "ssh",
    repo_path: str | None,
    ssh: {target, key, remote_path} | None,
    status: str,
    required_docs: list[str],
    available: bool,       # False for NEEDS_CONFIRMATION / candidate-only
    unavailable_reason: str | None,
  }
  ```

  Unavailable entries are included (not hidden) so the picker shows *why*
  a project can't be bound yet, instead of silently omitting it — omitting
  would itself be a form of guessing.

- `resolve_registry_project(key) -> dict | None`: same shape, single
  lookup. This is the one function both the bind endpoint and the
  turn-time injector call — there is exactly one place that parses
  `WORKSPACES.yaml` into this shape.

### 3. Binding API (api/routes.py)

- `GET /api/workspaces/registry` → `{"projects": list_registry_projects()}`.
  Used by the project picker (new-chat panel and the rebind control).
- `POST /api/session/bind_project` `{session_id, project_key}`:
  - `project_key` unknown or `available: false` → 400 with the specific
    reason (`"project_not_found"` / `"project_unavailable: <status>"`).
    Nothing is bound.
  - Valid and available → sets `session.bound_project_key`; for
    `access_mode: local`, also sets `session.workspace = repo_path`;
    persists the session.
  - `project_key: null` → clears `bound_project_key` (unbind). Does not
    touch `session.workspace` — it stays wherever it last was.

### 4. Binding UI

Two touchpoints, both calling the same `_bindProjectAndRefresh()` →
`POST /api/session/bind_project` path (`static/workspace.js`) — one shared
function, no duplicated bind logic:

- **At/near chat creation**: a "Projects" section was added to the
  existing composer workspace-switcher dropdown (`#composerWsDropdown`,
  opened via the folder chip next to the model/persona pickers — see
  `renderBoundProjectDropdownSection()` in `workspace.js`, wired into
  `renderWorkspaceDropdownInto()` in `panels.js`). A session already
  exists the moment "New conversation" is clicked in this app (there is
  no separate "configure then create" step), so this dropdown is
  reachable immediately at chat start.
- **Rebind on an existing chat**: a "Project" `<select>` in the workspace
  panel header (`#boundProjectRow` / `#boundProjectSelect` in
  `index.html`), populated by `renderBoundProjectControl()`, showing the
  current binding (or "Unbound") and letting the user change or clear it.

Both fetch the registry through a shared 15s-cached `_fetchProjectRegistry()`
so opening the dropdown and then the panel doesn't double-fetch.

**Local-mode trust-boundary fix (found during implementation):** setting
`session.workspace = repo_path` alone was not sufficient — WebUI's file
explorer, terminal, git, and upload endpoints all gate through
`resolve_trusted_workspace()`, which only trusts paths under the user's
home directory, the boot-time default workspace, or the saved-workspace
list (`workspaces.json`). A registry `repo_path` living elsewhere (the
common case) would 404 the instant the user opened the workspace panel.
Fix: `bind_project` now also registers the resolved `repo_path` into the
saved-workspace list (idempotently, same shape `_handle_workspace_add`
already uses) at bind time — reusing that existing trust path instead of
adding a bound-project bypass to every gated endpoint individually.

### 5. Turn-time injection — the enforcement mechanism

- New `_bound_project_prompt(session) -> str` in `api/streaming.py`,
  called from `_webui_ephemeral_system_prompt()` alongside the existing
  persona/surface-context/delivery blocks.
- If `session.bound_project_key` is set, resolve it **fresh** (not from
  whatever was true at bind time) via `resolve_registry_project`:
  - If it no longer resolves, or its `available` flipped to `false` since
    binding, the turn does **not** proceed silently as if unbound. It
    surfaces a visible error to the user for that turn (registry drifted;
    binding needs to be redone) — never a silent downgrade to normal
    behavior.
  - Otherwise, prepend to the system prompt, in order:
    1. The resolved authoritative block: project name, access_mode,
       `repo_path` (local) or `ssh_target` / `remote_path` / key path
       (ssh), and `required_docs`.
    2. The full text of `project-lifecycle`'s `SKILL.md`, read off the
       shared volume and cached with mtime invalidation (mirrors how the
       registry itself is cached).
    3. An explicit instruction: operate only inside this resolved
       location; ignore any other folder/project the user's message text
       might mention.
- Both `gateway_chat.py` and `streaming.py` call
  `_webui_ephemeral_system_prompt()` already (one call site each) — no
  duplicated wiring needed; bound-chat behavior is identical regardless of
  which backend routes the turn.

### 6. Error handling

- **Bind time**: unknown key, unavailable project, or a `WORKSPACES.yaml`
  parse failure → 400 with a specific reason; nothing is bound, no
  partial state.
- **Turn time**: registry drift (key removed / gone unavailable since
  bind) or an unreadable `SKILL.md` → visible error surfaced in that turn,
  turn does not proceed as if nothing happened.

### 7. SSH read-only file browsing (added after initial ship)

Deliberately narrow scope: list a directory and read a text file's
content, both anchored under the registry's declared `remote_path`, for a
session bound to an `access_mode: ssh` project. No writes, no arbitrary
command execution, no interactive terminal — WebUI's *embedded terminal*
stays local-only exactly as before. The agent's own SSH work (via
project-lifecycle) is unaffected either way; this only powers WebUI's own
file explorer/preview panels.

- New module `api/ssh_workspace.py`: `ssh_list_dir(project, rel)` and
  `ssh_read_file(project, rel)`, shaped to return the exact same entry/
  content dicts `api.workspace.list_dir()` / `read_file_content()` already
  return, so the frontend needs zero changes to render them.
- Every remote path is anchored by validating `rel` through the same
  traversal-safe normalizer local paths use
  (`_normalize_workspace_rel_path`) before joining under `remote_path` —
  never a raw user path. Every value interpolated into the remote shell
  command is `shlex.quote()`-escaped.
- Directory listing skips symlinks entirely (v1 — safely resolving a
  remote symlink target without a local filesystem to check against is
  its own problem, deferred). File reads reject non-regular files and
  anything over `MAX_FILE_BYTES`; binary/office/image preview is out of
  scope (text only).
- `SshWorkspaceError` (connection failure, auth failure, timeout,
  incomplete SSH config) surfaces as a `502` with the underlying message —
  never a silent fallback to a local path or an empty listing.
- Wired into the existing `/api/list` and `/api/file` handlers: both check
  `_resolve_ssh_bound_project(session)` first (resolved fresh from the
  registry, same pattern as `_bound_project_prompt`) and branch to SSH
  before touching the local-filesystem code path at all.
- No live SSH server was available to test success-path listing/reading
  end-to-end; that logic is covered by unit tests with mocked
  `subprocess.run` (`tests/test_ssh_workspace.py`). The live-endpoint tests
  (`tests/test_ssh_bound_project_endpoints.py`) prove routing and the
  connection-failure error path against a real (deliberately unreachable,
  RFC 5737 TEST-NET-1) target.

## Open items for the implementation plan

- Exact wording/format of the authoritative context block and where in
  the system prompt it sits relative to persona/surface-context text.
- Whether `bind_project` requires the session to have no in-flight run
  (almost certainly yes — same guard pattern as other session-mutating
  endpoints).
- Test coverage: registry parsing (available/unavailable/malformed),
  bind/unbind API, turn-time injection on both chat paths, workspace lock
  enforcement for local mode, and the "registry drifted mid-binding"
  error path.
