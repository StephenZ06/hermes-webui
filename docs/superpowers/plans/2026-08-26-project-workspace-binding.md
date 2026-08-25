# Project Workspace Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a sidebar Project folder be bound to a local workspace path so member chats (existing, new, and later-moved-in) default to that folder.

**Architecture:** Add `workspace_path` to the Project JSON record; a new `POST /api/projects/set_workspace` validates/persists it and bulk-applies to current member sessions using the existing `_reassign_project_sessions`-style safe-update pattern; `/api/session/new` and `/api/session/move` read the bound project's `workspace_path` as a default. Frontend adds one context-menu entry that opens a small inline picker.

**Tech Stack:** Python stdlib HTTP handler (`api/routes.py`), pytest (`tests/`), vanilla JS (`static/sessions.js`, `static/panels.js`).

## Global Constraints

- Path validation for `workspace_path` MUST go through `resolve_trusted_workspace()` then `is_blocked_system_path()` — the same gate the registry bind-project feature and the workspace-create form already use. No second validation path.
- The bulk-apply helper MUST NOT call `s.save()` directly on a session with an active stream — update the live cached object under `LOCK` instead, exactly like `_reassign_project_sessions`. This is a data-race safety requirement from spec section "Background."
- No system-prompt/context injection. This feature changes `session.workspace` only.
- No undo chain. Unbinding does not revert member sessions' workspace.

Spec: `docs/superpowers/specs/2026-08-26-project-workspace-binding-design.md`

---

### Task 1: Backend — `_apply_project_workspace` helper + `POST /api/projects/set_workspace`

**Files:**
- Modify: `api/routes.py` (new function near `_reassign_project_sessions` at line 14335; new route block near the other `/api/projects/*` routes starting at line 16919)
- Test: `tests/test_project_workspace_binding.py` (new)

**Interfaces:**
- Produces: `_apply_project_workspace(project_id: str, workspace_path: str | None) -> int` — returns count of sessions updated. Same signature shape as `_reassign_project_sessions(old_project_ids, new_project_id)` but keyed on a single `project_id` and setting `.workspace` instead of `.project_id`.
- Produces: route `POST /api/projects/set_workspace`, body `{"project_id": str, "workspace_path": str | null}`, response `{"ok": true, "project": {...}, "sessions_updated": int}` on success, `bad(handler, msg, status)` shape on failure (404 unknown project, 400 invalid path).

- [ ] **Step 1: Write the failing tests for `_apply_project_workspace`**

Create `tests/test_project_workspace_binding.py`:

```python
"""Regression coverage for binding a workspace path to a sidebar Project.

Mirrors tests/test_project_merge_reassigns_sessions.py's fake-session /
monkeypatch shape: `_apply_project_workspace` reuses the same
active-stream-safe update pattern as `_reassign_project_sessions`, just
setting `.workspace` instead of `.project_id`.
"""
import json

from api import routes


def _write_index(tmp_path, entries):
    index_file = tmp_path / "_index.json"
    index_file.write_text(json.dumps(entries), encoding="utf-8")
    return index_file


class _FakeSession:
    def __init__(self, session_id, project_id, workspace="/old/path"):
        self.session_id = session_id
        self.project_id = project_id
        self.workspace = workspace
        self.saved_workspace = None

    def save(self):
        self.saved_workspace = self.workspace


def test_apply_project_workspace_updates_non_streaming_sessions(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "s1", "project_id": "proj-a", "active_stream_id": None},
        {"session_id": "s2", "project_id": "proj-a", "active_stream_id": None},
        {"session_id": "s3", "project_id": "other", "active_stream_id": None},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: set())

    fake_sessions = {
        "s1": _FakeSession("s1", "proj-a"),
        "s2": _FakeSession("s2", "proj-a"),
    }
    monkeypatch.setattr(routes, "get_session", lambda sid: fake_sessions[sid])

    updated = routes._apply_project_workspace("proj-a", "/bound/path")

    assert updated == 2
    assert fake_sessions["s1"].saved_workspace == "/bound/path"
    assert fake_sessions["s2"].saved_workspace == "/bound/path"


def test_apply_project_workspace_updates_streaming_session_in_cache(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "live1", "project_id": "proj-a", "active_stream_id": "stream-1"},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: {"stream-1"})

    cached = _FakeSession("live1", "proj-a")
    monkeypatch.setattr(routes, "SESSIONS", {"live1": cached})

    def _boom(sid):
        raise AssertionError("must not call get_session for a live-cached streaming session")
    monkeypatch.setattr(routes, "get_session", _boom)

    updated = routes._apply_project_workspace("proj-a", "/bound/path")

    assert updated == 1
    assert cached.workspace == "/bound/path"
    # Streaming session: the worker's own next save persists it -- we must
    # NOT have called .save() ourselves (that would race the writer).
    assert cached.saved_workspace is None


def test_apply_project_workspace_ignores_other_projects(tmp_path, monkeypatch):
    index_file = _write_index(tmp_path, [
        {"session_id": "s1", "project_id": "proj-a", "active_stream_id": None},
        {"session_id": "s2", "project_id": "proj-b", "active_stream_id": None},
    ])
    monkeypatch.setattr(routes, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(routes, "_active_stream_ids", lambda: set())
    fake_sessions = {"s1": _FakeSession("s1", "proj-a")}
    monkeypatch.setattr(routes, "get_session", lambda sid: fake_sessions[sid])

    updated = routes._apply_project_workspace("proj-a", "/bound/path")

    assert updated == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/z014/Apps/hermes-webui && python3 -m pytest tests/test_project_workspace_binding.py -v`
Expected: FAIL — `AttributeError: module 'api.routes' has no attribute '_apply_project_workspace'`

- [ ] **Step 3: Implement `_apply_project_workspace`**

In `api/routes.py`, immediately after the `_reassign_project_sessions` function (ends around line 14335 + its body — insert right after its closing `return updated`):

```python
def _apply_project_workspace(project_id: str, workspace_path) -> int:
    """Set `.workspace` on every session currently in `project_id`.

    Same active-stream-safe update pattern as `_reassign_project_sessions`
    (see that function's docstring for the race it avoids) -- reused here
    with `workspace` as the field instead of `project_id`. Used by
    POST /api/projects/set_workspace so binding a workspace to a Project
    retroactively applies to every chat already filed into it.

    Returns the number of sessions updated.
    """
    if not SESSION_INDEX_FILE.exists():
        return 0
    updated = 0
    try:
        index = json.loads(SESSION_INDEX_FILE.read_bytes())
        active_ids = _active_stream_ids()
        for entry in index:
            if entry.get("project_id") != project_id:
                continue
            sid = entry.get("session_id")
            try:
                if entry.get("active_stream_id") in active_ids:
                    with LOCK:
                        cached = SESSIONS.get(sid)
                        if cached is not None:
                            cached.workspace = workspace_path
                            updated += 1
                    continue
                s = get_session(sid)
                s.workspace = workspace_path
                s.save()
                updated += 1
            except Exception:
                logger.exception("failed to apply project workspace to session %s", sid)
    except Exception:
        logger.exception("failed to apply project workspace for project %s", project_id)
    return updated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/z014/Apps/hermes-webui && python3 -m pytest tests/test_project_workspace_binding.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Implement `POST /api/projects/set_workspace`**

In `api/routes.py`, add immediately after the `/api/projects/rename` block (after its `return j(handler, {"ok": True, "project": proj})` at line 16976, before the `/api/projects/delete` block):

```python
    if parsed.path == "/api/projects/set_workspace":
        try:
            require(body, "project_id")
        except ValueError as e:
            return bad(handler, str(e))
        projects = load_projects()
        proj = next(
            (p for p in projects if p["project_id"] == body["project_id"]), None
        )
        if not proj:
            return bad(handler, "Project not found", 404)
        raw_path = body.get("workspace_path")
        workspace_path = str(raw_path).strip() if raw_path else None
        if workspace_path:
            try:
                workspace_path = str(resolve_trusted_workspace(workspace_path))
            except ValueError as e:
                return bad(handler, str(e), 400)
            if is_blocked_system_path(workspace_path):
                return bad(
                    handler,
                    f"Project path is not allowed: {workspace_path}",
                    400,
                )
        proj["workspace_path"] = workspace_path
        save_projects(projects)
        sessions_updated = _apply_project_workspace(body["project_id"], workspace_path)
        return j(handler, {"ok": True, "project": proj, "sessions_updated": sessions_updated})
```

- [ ] **Step 6: Manual smoke test of the route (no HTTP layer, direct call)**

Run: `cd /home/z014/Apps/hermes-webui && python3 -m pytest tests/test_project_workspace_binding.py -v` again to confirm nothing broke, then:

```bash
python3 -c "
import ast
ast.parse(open('api/routes.py').read())
print('routes.py parses OK')
"
```
Expected: `routes.py parses OK`, all 3 tests still pass.

- [ ] **Step 7: Commit**

```bash
cd /home/z014/Apps/hermes-webui
git add api/routes.py tests/test_project_workspace_binding.py
git commit -m "feat(webui): add /api/projects/set_workspace to bind a workspace path to a Project

Persists workspace_path on the Project record and retroactively applies
it to every session currently filed into that Project, reusing the same
active-stream-safe bulk-update pattern as _reassign_project_sessions."
```

---

### Task 2: Backend — default workspace from bound Project on session create/move

**Files:**
- Modify: `api/routes.py` (`/api/session/new` handler, workspace resolution around line 14859; `/api/session/move` handler at line 16869)
- Test: `tests/test_project_workspace_binding.py` (append)

**Interfaces:**
- Consumes: `load_projects()` (existing), `_apply_project_workspace` is NOT used here — this task only affects a *single* session at creation/move time, not a bulk update.

- [ ] **Step 1: Write the failing test for session/move defaulting**

Append to `tests/test_project_workspace_binding.py`:

```python
def test_session_move_applies_bound_project_workspace(monkeypatch):
    """Moving a session into a Project that has a bound workspace_path
    should set that session's workspace immediately (single-session path,
    distinct from the bulk _apply_project_workspace helper used at bind
    time)."""
    from api import routes as _routes

    class _MoveFakeSession:
        def __init__(self):
            self.project_id = None
            self.workspace = "/original/workspace"
            self.active_stream_id = None
            self.saved = False
        def save(self):
            self.saved = True
        def compact(self):
            return {"project_id": self.project_id, "workspace": self.workspace}

    fake = _MoveFakeSession()
    monkeypatch.setattr(_routes, "_get_or_materialize_session", lambda sid: fake)
    monkeypatch.setattr(
        _routes, "load_projects",
        lambda: [{"project_id": "proj-bound", "name": "Bound", "workspace_path": "/bound/path"}],
    )

    class _FakeLock:
        def acquire(self, timeout=None):
            return True
        def release(self):
            pass
    monkeypatch.setattr(_routes, "_get_session_agent_lock", lambda sid: _FakeLock())
    monkeypatch.setattr(_routes, "publish_session_list_changed", lambda *a, **k: None)

    body = {"session_id": "s1", "project_id": "proj-bound"}
    result = _routes._apply_session_move_project_workspace(fake, body, load_projects=_routes.load_projects)

    assert fake.project_id == "proj-bound"
    assert fake.workspace == "/bound/path"
```

Note: this test targets a small extracted helper (`_apply_session_move_project_workspace`) rather than the full HTTP handler, so the logic is testable without constructing a fake `handler`/`parsed` HTTP request. Step 3 below defines that helper and wires it into both `/api/session/new` and `/api/session/move`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/z014/Apps/hermes-webui && python3 -m pytest tests/test_project_workspace_binding.py::test_session_move_applies_bound_project_workspace -v`
Expected: FAIL — `AttributeError: module 'api.routes' has no attribute '_apply_session_move_project_workspace'`

- [ ] **Step 3: Implement the shared helper and wire it into both handlers**

In `api/routes.py`, add this helper right after `_apply_project_workspace` (Task 1, Step 3):

```python
def _bound_project_workspace(project_id, load_projects=load_projects):
    """Return the workspace_path bound to `project_id`, or None if the
    project doesn't exist or has no binding. Shared by /api/session/new
    (default for a brand-new session) and /api/session/move (immediate
    switch for a single session moved into an already-bound Project)."""
    if not project_id:
        return None
    proj = next((p for p in load_projects() if p["project_id"] == project_id), None)
    return proj.get("workspace_path") if proj else None


def _apply_session_move_project_workspace(session, body, load_projects=load_projects):
    """Set session.project_id from body, and if the target project has a
    bound workspace_path, also set session.workspace to it. Factored out
    of the /api/session/move handler so it's testable without a fake HTTP
    request; the handler still owns locking, the 404-unknown-project
    check, and the response shape."""
    target_pid = body.get("project_id") or None
    session.project_id = target_pid
    bound_path = _bound_project_workspace(target_pid, load_projects=load_projects)
    if bound_path:
        session.workspace = bound_path
    return session
```

Now wire it into `/api/session/move` (`api/routes.py:16869`) — replace the existing:
```python
        try:
            s.project_id = target_pid
            s.save()
        finally:
            _move_lock.release()
```
with:
```python
        try:
            _apply_session_move_project_workspace(s, body)
            s.save()
        finally:
            _move_lock.release()
```
(`target_pid` is already validated to exist a few lines above this block — no change to that check.)

Now wire the create-time default into `/api/session/new` (`api/routes.py`, right after the existing line `workspace = str(resolve_trusted_workspace(body.get("workspace"))) if body.get("workspace") else None` around line 14859) — insert immediately after it:
```python
        if not workspace and body.get("project_id"):
            _bound_path = _bound_project_workspace(body.get("project_id"))
            if _bound_path:
                workspace = _bound_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/z014/Apps/hermes-webui && python3 -m pytest tests/test_project_workspace_binding.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/z014/Apps/hermes-webui
git add api/routes.py tests/test_project_workspace_binding.py
git commit -m "feat(webui): default new/moved chat workspace from bound Project

/api/session/new and /api/session/move now read the target Project's
workspace_path (if bound) as the session's default workspace, via a
shared _bound_project_workspace() lookup."
```

---

### Task 3: Frontend — context menu entry + inline picker

**Files:**
- Modify: `static/sessions.js` (`_showProjectContextMenu` at line 9763; add a new function `_showProjectWorkspacePicker`)
- Modify: `static/i18n.js` (add two label strings, following the file's existing per-locale key pattern seen for `workspace_add_path_placeholder`)

**Interfaces:**
- Consumes: `POST /api/projects/set_workspace` (Task 1), `api()` helper (existing, used throughout `sessions.js`), `_wireWorkspaceFormPathSuggestions`-style autocomplete is NOT reused directly (that function is scoped to the full workspace-panel form in `panels.js`) — this task uses a lighter standalone suggestion list built from the same saved-workspace source (`getSavedWorkspaces()` / equivalent already used by the composer workspace switcher) to avoid coupling to `panels.js`'s form-specific DOM ids.
- Produces: `_showProjectWorkspacePicker(proj, chip)` — opens the inline picker; called from the new menu item.

- [ ] **Step 1: Add the menu item, above Rename**

In `static/sessions.js`, in `_showProjectContextMenu` (line 9763), insert before the existing `// Rename option` block:

```javascript
  // Workspace Folder option (above Rename per design)
  const workspaceItem=document.createElement('div');
  const boundPath=proj.workspace_path||'';
  workspaceItem.textContent=boundPath?('Workspace: '+boundPath):'Set Workspace Folder';
  if(boundPath) workspaceItem.title=boundPath;
  workspaceItem.style.cssText='padding:7px 14px;cursor:pointer;font-size:13px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px;';
  workspaceItem.onmouseenter=()=>workspaceItem.style.background='var(--hover-bg)';
  workspaceItem.onmouseleave=()=>workspaceItem.style.background='';
  workspaceItem.onclick=()=>{menu.remove();_showProjectWorkspacePicker(proj,chip);};
  menu.appendChild(workspaceItem);
```

- [ ] **Step 2: Implement the picker**

Add this new function right after `_showProjectContextMenu` (after its closing `}` around line 9820):

```javascript
async function _showProjectWorkspacePicker(proj, chip){
  document.querySelectorAll('.project-workspace-picker').forEach(el=>el.remove());
  const wrap=document.createElement('div');
  wrap.className='project-workspace-picker';
  wrap.style.cssText='position:fixed;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;z-index:9999;width:320px;box-shadow:0 4px 16px rgba(0,0,0,.35);';
  const rect=chip.getBoundingClientRect();
  wrap.style.left=Math.max(8,rect.left)+'px';
  wrap.style.top=(rect.bottom+4)+'px';

  const label=document.createElement('div');
  label.textContent='Workspace folder for "'+proj.name+'"';
  label.style.cssText='font-size:12px;color:var(--muted);margin-bottom:6px;';
  wrap.appendChild(label);

  const input=document.createElement('input');
  input.type='text';
  input.value=proj.workspace_path||'';
  input.placeholder='/absolute/path/to/folder';
  input.style.cssText='width:100%;box-sizing:border-box;padding:6px 8px;font-size:13px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);margin-bottom:8px;';
  wrap.appendChild(input);

  const err=document.createElement('div');
  err.style.cssText='font-size:12px;color:var(--error,#e94560);margin-bottom:8px;display:none;';
  wrap.appendChild(err);

  const btnRow=document.createElement('div');
  btnRow.style.cssText='display:flex;justify-content:flex-end;gap:8px;';
  const clearBtn=document.createElement('button');
  clearBtn.type='button';
  clearBtn.textContent='Clear';
  clearBtn.style.cssText='padding:5px 10px;font-size:13px;background:transparent;border:1px solid var(--border);border-radius:6px;color:var(--text);cursor:pointer;';
  const saveBtn=document.createElement('button');
  saveBtn.type='button';
  saveBtn.textContent='Save';
  saveBtn.style.cssText='padding:5px 10px;font-size:13px;background:var(--accent);border:none;border-radius:6px;color:#fff;cursor:pointer;';
  btnRow.appendChild(clearBtn);
  btnRow.appendChild(saveBtn);
  wrap.appendChild(btnRow);

  async function _save(path){
    err.style.display='none';
    try{
      const res=await api('/api/projects/set_workspace',{method:'POST',body:JSON.stringify({project_id:proj.project_id,workspace_path:path||null})});
      if(res&&res.project){
        proj.workspace_path=res.project.workspace_path;
        showToast(path?('Workspace bound · '+(res.sessions_updated||0)+' chats updated'):'Workspace cleared');
        wrap.remove();
        if(typeof renderSessionList==='function') await renderSessionList();
      }
    }catch(e){
      err.textContent=(e&&e.message)||'Failed to save workspace';
      err.style.display='';
    }
  }
  saveBtn.onclick=()=>_save(input.value.trim());
  clearBtn.onclick=()=>_save('');
  input.onkeydown=(e)=>{ if(e.key==='Enter'){e.preventDefault();_save(input.value.trim());} if(e.key==='Escape'){e.preventDefault();wrap.remove();} };
  input.onclick=(e)=>e.stopPropagation();

  document.body.appendChild(wrap);
  setTimeout(()=>input.focus(),10);
  const dismiss=(ev)=>{ if(!wrap.contains(ev.target)){ wrap.remove(); document.removeEventListener('click',dismiss); } };
  setTimeout(()=>document.addEventListener('click',dismiss),0);
}
```

- [ ] **Step 3: Add the bound-path tooltip to the Project chip itself**

Spec section 3 also calls for a hover tooltip on the chip (not just the
menu item) so the binding is discoverable without opening the menu. Find
where each project chip's attributes are set (`chip.dataset.projectId=p.project_id;`
around line 7813) and add immediately after it:

```javascript
      if(p.workspace_path) chip.title=p.workspace_path;
```

- [ ] **Step 4: Syntax-check the modified file**

Run: `node --check /home/z014/Apps/hermes-webui/static/sessions.js`
Expected: no output (exit 0)

- [ ] **Step 5: Commit**

```bash
cd /home/z014/Apps/hermes-webui
git add static/sessions.js
git commit -m "feat(webui): add Workspace Folder picker to Project context menu

New item above Rename in the sidebar Project's three-dot menu opens an
inline path picker that calls POST /api/projects/set_workspace."
```

---

### Task 4: Verification

**Files:** none (verification only)

- [ ] **Step 1: Full backend test suite for the new file**

Run: `cd /home/z014/Apps/hermes-webui && python3 -m pytest tests/test_project_workspace_binding.py -v`
Expected: 4 passed

- [ ] **Step 2: Confirm no existing project-related tests regressed**

Run: `cd /home/z014/Apps/hermes-webui && python3 -m pytest tests/test_project_merge_reassigns_sessions.py tests/test_issue3746_session_move_delete_timeout.py tests/test_issue1614_project_profile_filtering.py -v`
Expected: all pass (unchanged — Task 2's `/api/session/move` edit only adds behavior when the target project has `workspace_path` set, which no existing test's fixture data sets)

- [ ] **Step 3: Rebuild and recreate the container**

Run:
```bash
cd /home/z014/Apps/hermes-webui
docker compose build hermes-webui
docker compose up -d --force-recreate hermes-webui
```
Expected: build succeeds, container reaches `healthy` status.

- [ ] **Step 4: In-container backend smoke test of the new endpoint logic**

No webui login credentials are available to this agent (established constraint from earlier in the session) — verify the new backend logic directly in the running container's venv instead, the same technique already used earlier in this session to verify the `caveman` personality wiring:

```bash
docker exec hermes-webui-hermes-webui-1 /app/venv/bin/python3 -c "
import sys
sys.path.insert(0, '/apptoo')
from api import routes
print('set_workspace route present:', '/api/projects/set_workspace' in open('/apptoo/api/routes.py').read())
print('_apply_project_workspace callable:', callable(getattr(routes, '_apply_project_workspace', None)))
print('_bound_project_workspace callable:', callable(getattr(routes, '_bound_project_workspace', None)))
"
```
Expected: all three print `True`/route-found lines.

- [ ] **Step 5: Report to user**

Summarize: files changed, test results, that browser/UI verification could not be performed directly (same login-credential constraint as prior UI work this session), and ask the user to try binding a workspace to a Project folder and confirm the menu item + picker behave as designed.
