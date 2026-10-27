# Project workspace starter — implementation handoff

**Prepared:** 2026-10-20  
**Implemented commit:** `89c3b56d0` (`Add workspace-backed project starter`)  
**Deployment:** the native Hermes WebUI service was restarted and is serving
`g89c3b56d0` on `127.0.0.1:8787`.

## User goal

Replace Chat's old project-folder flow, which made a WebUI-only folder and
required a workspace to be assigned later. The new flow should begin with the
workspace and establish a useful on-disk project contract immediately.

The intended workflow is:

1. In Chat, choose **New project**.
2. Select a saved workspace.
3. Name the project folder, choose a starter template, and provide a brief.
4. Optionally attach a `.md` or `.txt` brief.
5. Hermes creates both the physical folder and the Chat sidebar project in one
   request.
6. The new project contains durable documentation and continuity instructions
   for future coding agents.

## What was implemented

### Chat intake UI

`static/sessions.js` replaces the previous inline folder-name input and the
project-picker's basic prompt with one modal flow.

The modal includes:

- project folder name;
- saved workspace selector (offline workspaces are excluded);
- templates: **blank**, **web**, **iOS**, **API/backend**, and **research**;
- free-form project brief;
- optional `.md` / `.txt` brief attachment, capped at 100 KB;
- lightweight local template suggestion based on brief keywords; and
- an **existing project** mode.

Existing-project mode treats the selected saved workspace as the project root.
It must therefore already be registered in Hermes Spaces. It does not browse
arbitrary paths from this modal.

When launched from a chat's project picker, the created/adopted project is also
assigned to that chat. The project retains the initiating session's profile;
otherwise the backend uses the active profile.

### Safe backend workflow

`api/routes.py` adds:

- `POST /api/projects/create_starter`
- `POST /api/projects/adopt_starter`

Both routes first pass the selected path through Hermes' existing trusted
workspace validation. New projects create their folder beneath that root. The
create route then saves the sidebar project record with the physical project
path as `workspace_path`.

If saving the sidebar project record fails after files are created, the route
attempts to remove only the just-created folder. It never removes an adopted or
pre-existing project folder.

### Starter packs

`api/project_starter.py` is the new filesystem-focused module. It uses the
existing anchored/no-follow workspace helpers rather than untrusted pathname
writes.

For new projects it creates:

- `AGENTS.md`
- `.agent/ECC_HANDOFF.md`
- `README.md`
- template-specific files in `docs/`

Web projects receive `PRODUCT.md`, `ARCHITECTURE.md`, `UI_UX.md`, and
`TESTING.md`. iOS adds `IOS.md`; API adds `API.md`; research adds
`RESEARCH.md`, `SOURCES.md`, and `FINDINGS.md`.

The supplied brief is placed into the generated documents rather than leaving
only blank boilerplate.

For adoption, Hermes creates **only missing** starter files. It deliberately
does not replace `README.md`, existing architecture docs, or any other
user-authored files.

### Continuity contract

Every generated `AGENTS.md` directs coding agents to read
`.agent/ECC_HANDOFF.md` before any persisted project change and update it
before finishing. Read-only/no-change questions are explicitly excluded.

The generated handoff separates verified changed, tested, committed, deployed,
and user-verified states; it also prohibits secrets and raw chat logs.

The repository-wide handoff at `.agent/HANDOFF.md` was updated with a concise
record of this feature and its deployment state.

## What is intentionally not implemented yet

- There is no live LLM planning call during project intake. Template suggestion
  is keyword-based and the user can override it.
- There is no adaptive follow-up questionnaire for missing stack choices yet.
  A good next step is a separate, explicitly invoked planning action using the
  selected/current profile, not an automatic model call for every new project.
- Existing-project adoption currently selects from already-saved workspaces;
  it does not expose a new folder browser inside the creation modal.
- The Work Hub's separate project creation path was left unchanged on purpose;
  this implementation is scoped to Chat projects.

## Verification already performed

The following command completed successfully after the implementation:

```bash
HERMES_WEBUI_TEST_PYTHON=/home/z014/.hermes/hermes-agent/.venv/bin/python \
  ./scripts/test.sh \
  tests/test_project_starter.py \
  tests/test_project_lifecycle_hook.py \
  tests/test_route_table_parity.py \
  tests/test_sprint15.py
```

Result: **60 passed**.

Additional checks passed:

- `node --check static/sessions.js`
- `git diff --check`
- `graphify update .`

## Deployment facts

- The committed revision is `89c3b56d0`.
- `hermes-webui-native.service` was restarted successfully.
- `/sw.js` reported `g89c3b56d0` after restart.
- The restart recovered stale cron execution records and re-armed the existing
  `graphify-refresh` scheduled job. This was runtime recovery output from the
  restart, not a change to cron configuration.

## Working tree note

At the time this handoff was written, these unrelated user files remained
untracked and were deliberately left untouched:

- `BlockNote Integration Plan for Hermes WebUI.md`
- `mockups/`

This handoff file itself is newly created and has not been committed yet.
