# Load Page Scripts On Demand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status (2026-11-10):** executed in commits 0c717013f, a42fc87b4, 0ff40ba3e and 6191b2c3d, with the deviations listed in `.agent/PROJECT_STATUS.md`. The task text below is the plan as written.

**Goal:** Stop loading the Jobs, Notebook, Files, Work Hub, Goal Planner and Dashboard scripts on every visit; load each one the first time its page (or a feature that needs it) is opened.

**Architecture:** A small classic-script loader, `static/page-modules.js`, maps a page name to its ordered script list and injects those scripts once, returning a promise. `switchPanel()` (static/panels.js) awaits the loader before it calls the page's `mount()`. The handful of cross-page callers (for example `window.Notebook.openFrom` from chat and the workspace panel) go through the same loader. The pages' own code does not change: each script still publishes its `window.X = {mount, ...}` object when it runs.

**Tech Stack:** Vanilla JS classic scripts, the existing Python static handler (`api/routes.py::_serve_static`), the service worker (`static/sw.js`), pytest + Playwright.

## Global Constraints

- No new dependencies, bundlers or build steps (AGENTS.md).
- Tests run through `./scripts/test.sh`, never bare pytest.
- Scripts keep `?v=__WEBUI_VERSION__` cache-busting; the loader appends the same version (`window.__HERMES_WEBUI_BUNDLE_VERSION__`).
- Script order inside one page must match today's `index.html` order (for example job-os: state, api, render, index).
- Fail closed: if a page's scripts fail to load, the page shows its error state and a later visit retries; nothing pretends the page loaded.
- Never edit files while a suite run is in progress (it changes the version digest).
- After each task: commit (with the Co-Authored-By line), redeploy the live UI, `graphify update .`, push to `fork`.

## Measured baseline (2026-11-10, isolated instance, Dashboard landing)

| Script group | Raw | Gzipped |
|---|---|---|
| job-os (state, api, render, index) | 327 KB | 92 KB |
| notebook (api, index) | 148 KB | 43 KB |
| dashboard (sprite, index) | 137 KB | 40 KB |
| work-hub.js | 106 KB | 28 KB |
| file-manager.js | 42 KB | 12 KB |
| goal-planner.js | 11 KB | 3 KB |
| **In scope, total** | **771 KB** | **218 KB** |

The browser parses and runs all of this on every visit. Moving it behind the loader saves the parse/run cost on every visit and the download on first visits. Repeat visits already download nothing (commit 2040ea7af).

## Out of scope (named so they are not forgotten)

- **Office (`static/office/index.js`, three.js) and Agent Canvas (`static/agent-canvas.js` + d3-force):** they receive live chat events while their page is hidden (`HermesOffice.onSpawn/onToolActivity/onComplete` in messages.js, `AgentCanvas.reset` in sessions.js) and the sidebar Office mounts at boot. Making them lazy needs an event buffer and a separate plan.
- **panels.js (888 KB) and style.css (1.65 MB):** they bundle many pages (settings, kanban, skills, logs...). Splitting them is a larger refactor that should follow this plan, using the same loader.
- **Dashboard when it is the landing page:** the loader still runs at once, so there is no saving there, only for visits that land elsewhere.

## File structure

- Create `static/page-modules.js`: the loader (`loadPageModule(name)`, `PAGE_MODULES`), ~60 lines, loaded early with `defer` before panels.js.
- Modify `static/index.html`: remove the in-scope `<script>` tags; add the loader tag.
- Modify `static/panels.js` (`switchPanel`, around the `nextPanel === 'jobs'` lines): await the loader before `mount()`.
- Modify `static/workspace.js`, `static/messages.js`, `static/dashboard/index.js`: Notebook calls go through the loader.
- Modify `static/sw.js`: drop the moved files from `SHELL_ASSETS`, runtime-cache versioned page-module scripts.
- Create `tests/test_page_modules_browser.py`; update the browser tests that assume the globals exist at boot.

---

### Task 1: The loader

**Files:**
- Create: `static/page-modules.js`
- Modify: `static/index.html` (add `<script src="static/page-modules.js?v=__WEBUI_VERSION__" defer></script>` directly before the `panels.js` tag)
- Test: `tests/test_page_modules_browser.py`

**Interfaces:**
- Produces: `window.loadPageModule(name: string) -> Promise<void>`; `window.PAGE_MODULES: {[name]: string[]}` (paths relative to the page base, without `?v=`).

- [ ] **Step 1: Write the failing test**

```python
"""Page scripts load once, in order, the first time they are asked for."""
import pytest
from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1280, "height": 800})
            tab.scripts = []
            tab.on("request", lambda r: tab.scripts.append(r.url.split("/static/")[1].split("?")[0])
                   if r.resource_type == "script" and "/static/" in r.url else None)
            tab.goto(BASE + "/", wait_until="load")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            yield tab
        finally:
            browser.close()


def test_a_page_module_loads_once_and_in_order(page):
    page.evaluate("async () => { await Promise.all([loadPageModule('jobs'), loadPageModule('jobs')]); }")
    jobs = [s for s in page.scripts if s.startswith("job-os/")]
    assert jobs == ["job-os/state.js", "job-os/api.js", "job-os/render.js", "job-os/index.js"]
    assert page.evaluate("() => typeof window.JobOS.mount") == "function"


def test_an_unknown_page_module_rejects(page):
    assert page.evaluate("() => loadPageModule('nope').then(() => 'ok', e => e.message)") == "unknown page module: nope"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/test.sh tests/test_page_modules_browser.py -q`
Expected: FAIL, `loadPageModule is not defined`.

- [ ] **Step 3: Write the loader**

```js
/* Page scripts that load the first time their page opens (docs/superpowers/plans/
   2026-11-10-load-page-scripts-on-demand.md). Order inside a page matters:
   later files use globals the earlier ones define. */
(function () {
  'use strict';
  var PAGE_MODULES = {
    jobs: ['static/job-os/state.js', 'static/job-os/api.js', 'static/job-os/render.js', 'static/job-os/index.js'],
    notebook: ['static/notebook/api.js', 'static/notebook/index.js'],
    dashboard: ['static/dashboard/sprite.js', 'static/dashboard/index.js'],
    notes: ['static/work-hub.js', 'static/goal-planner.js'],
    files: ['static/file-manager.js']
  };
  var pending = {};
  function version() {
    var v = window.__HERMES_WEBUI_BUNDLE_VERSION__;
    return v && v.indexOf('__') !== 0 ? '?v=' + encodeURIComponent(v) : '';
  }
  function addScript(path) {
    return new Promise(function (resolve, reject) {
      var el = document.createElement('script');
      el.src = new URL(path + version(), document.baseURI).href;
      el.async = false;
      el.onload = function () { resolve(); };
      el.onerror = function () { el.remove(); reject(new Error('could not load ' + path)); };
      document.head.appendChild(el);
    });
  }
  window.PAGE_MODULES = PAGE_MODULES;
  window.loadPageModule = function (name) {
    var files = PAGE_MODULES[name];
    if (!files) return Promise.reject(new Error('unknown page module: ' + name));
    if (!pending[name]) {
      pending[name] = files.reduce(function (chain, path) {
        return chain.then(function () { return addScript(path); });
      }, Promise.resolve()).catch(function (error) {
        delete pending[name]; // the next visit tries again
        throw error;
      });
    }
    return pending[name];
  };
}());
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./scripts/test.sh tests/test_page_modules_browser.py -q`
Expected: PASS. (job-os scripts are still also in index.html at this point, so `jobs` order is checked on the loader's own requests: filter `page.scripts` to requests made after the `evaluate` call if the boot tags make the list ambiguous.)

- [ ] **Step 5: Commit, redeploy, graphify, push**

```bash
git add static/page-modules.js static/index.html tests/test_page_modules_browser.py
git commit -m "pages: add an on-demand page script loader"
```

### Task 2: Jobs, Files and Goal Planner load on first open

These three pages are reached only through `switchPanel()`; nothing else calls them.

**Files:**
- Modify: `static/index.html` (remove the four `job-os/*.js` tags, `file-manager.js`, `goal-planner.js`)
- Modify: `static/panels.js` — the lines `if (nextPanel === 'jobs' && window.JobOS ...)` and `if (nextPanel === 'files' && window.HermesFileManager ...)`
- Modify: `static/sw.js` — remove `./static/job-os/*.js` from `SHELL_ASSETS`; let `isPageModule(shellPath)` (any path in `PAGE_MODULES` with this build's `VQ`) be cached like `isI18nSlice`
- Test: `tests/test_page_modules_browser.py`

**Interfaces:**
- Consumes: `loadPageModule(name)` from Task 1.

- [ ] **Step 1: Write the failing test**

```python
def test_jobs_scripts_load_only_when_the_jobs_page_opens(page):
    assert not [s for s in page.scripts if s.startswith("job-os/") or s in ("file-manager.js", "goal-planner.js")]
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_function("() => window.JobOS && document.querySelector('#mainJobs, [data-panel=jobs]')", timeout=15000)
    assert "job-os/index.js" in page.scripts
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./scripts/test.sh tests/test_page_modules_browser.py::test_jobs_scripts_load_only_when_the_jobs_page_opens -q`
Expected: FAIL on the first assert (the scripts load at boot).

- [ ] **Step 3: Implement**

In `switchPanel()` replace the two mount lines with:

```js
  if (nextPanel === 'jobs' || nextPanel === 'files') {
    const moduleName = nextPanel;
    try { await loadPageModule(moduleName); }
    catch (err) { if (typeof showToast === 'function') showToast(t('page_load_failed'), 5000, 'error'); return false; }
    if (!panelTicketIsCurrent()) return false;
    if (nextPanel === 'jobs' && window.JobOS) window.JobOS.mount();
    if (nextPanel === 'files' && window.HermesFileManager) window.HermesFileManager.mount();
  }
```

Add `page_load_failed: 'This page could not load. Check your connection and open it again.'` to the `en` block of `static/i18n.js` only (other languages fall back to English). Move `goal-planner.js` into the `notes` module (Task 3) because Work Hub calls it.

- [ ] **Step 4: Run the test and the Jobs/Files suites**

Run: `./scripts/test.sh tests/test_page_modules_browser.py $(grep -lE "JobOS|HermesFileManager" tests/test_*.py) -q`
Expected: PASS. Tests that read `window.JobOS` right after boot fail: in each, call `page.evaluate("() => loadPageModule('jobs')")` first (that is the behaviour change, not a regression).

- [ ] **Step 5: Measure, commit, redeploy, graphify, push**

Record the boot script bytes before/after with the isolated instance (`HERMES_HOME`/`HERMES_WEBUI_STATE_DIR` in the scratchpad, port 8789) and put the numbers in the commit message.

### Task 3: Notebook and Work Hub, including their cross-page callers

Notebook is also opened from chat (`messages.js` ~line 994), the workspace panel (`workspace.js` ~691-700) and the Dashboard (`dashboard/index.js` ~1662), all guarded by `window.Notebook && ...`. With lazy loading those guards would silently do nothing, so they go through the loader.

**Files:**
- Modify: `static/index.html` (remove `notebook/*.js`, `work-hub.js`)
- Modify: `static/panels.js` (`notebook` and `notes` mount lines, same pattern as Task 2)
- Modify: `static/workspace.js`, `static/messages.js`, `static/dashboard/index.js`
- Modify: `static/sw.js` (remove `./static/notebook/*.js` from `SHELL_ASSETS`)
- Test: `tests/test_page_modules_browser.py`

**Interfaces:**
- Produces: `window.withNotebook(fn: (Notebook) => any) -> Promise<any>` in `static/page-modules.js`.

- [ ] **Step 1: Write the failing test**

```python
def test_opening_a_note_from_chat_loads_the_notebook_first(page):
    assert not [s for s in page.scripts if s.startswith("notebook/")]
    opened = page.evaluate("async () => { const r = await withNotebook(n => typeof n.openFrom); return r; }")
    assert opened == "function"
    assert "notebook/index.js" in page.scripts
```

- [ ] **Step 2: Run it to verify it fails**

Expected: FAIL, `withNotebook is not defined` (and notebook scripts present at boot).

- [ ] **Step 3: Implement**

Add to `static/page-modules.js`:

```js
  window.withNotebook = function (fn) {
    return window.loadPageModule('notebook').then(function () { return fn(window.Notebook); });
  };
```

Replace each guarded call, for example in `workspace.js`:

```js
    row.onclick = () => withNotebook(n => n.openFrom(note.id, projectId));
```

and in `messages.js`:

```js
      if(linkedNote) withNotebook(n => n.openFrom(s.noteId, s.projectId)).catch(()=>{});
```

(Keep each call's existing arguments exactly; only the guard changes.)

- [ ] **Step 4: Run the test plus every test that mentions Notebook or Work Hub**

Run: `./scripts/test.sh tests/test_page_modules_browser.py $(grep -lE "Notebook|loadWorkHubPanel|work-hub" tests/test_*.py) -q`
Expected: PASS after adding `loadPageModule('notebook')` / `loadPageModule('notes')` to tests that use the globals straight after boot.

- [ ] **Step 5: Measure, commit, redeploy, graphify, push**

### Task 4: Dashboard when it is not the landing page

`job-os/index.js:1066` calls `if (window.HermesDashboard) window.HermesDashboard.select('career')` to jump to the Dashboard's career tab. With lazy loading that guard would silently do nothing, so it becomes `loadPageModule('dashboard').then(() => window.HermesDashboard.select('career'))`.

**Files:**
- Modify: `static/index.html` (remove `dashboard/sprite.js`, `dashboard/index.js`)
- Modify: `static/panels.js` (`dashboard` mount line, same pattern as Task 2)
- Modify: `static/sw.js`
- Test: `tests/test_page_modules_browser.py`, `tests/test_dashboard_browser.py`

- [ ] **Step 1: Write the failing test**

```python
def test_landing_on_chat_does_not_load_the_dashboard(page_on_chat):
    assert not [s for s in page_on_chat.scripts if s.startswith("dashboard/")]


def test_landing_on_the_dashboard_still_shows_it(page):
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector("#dashboardRoot .rpg-hero, #dashboardRoot [data-dash-ready]", timeout=15000)
```

(`page_on_chat` is the Task 1 fixture with `BASE + "/#chat"`.)

- [ ] **Step 2: Run to verify the first test fails.**
- [ ] **Step 3: Implement the mount change and remove the tags.**
- [ ] **Step 4: Run `tests/test_page_modules_browser.py tests/test_dashboard_browser.py` and the dashboard visual tests; expected PASS.**
- [ ] **Step 5: Measure first paint on Dashboard landing before/after (it must not get slower), commit, redeploy, graphify, push.**

### Task 5: Docs and the checklist note

- [ ] Add a paragraph to `ARCHITECTURE.md` (static assets section): which pages load on demand, the loader, the out-of-scope list above.
- [ ] Add a dated entry to `.agent/PROJECT_STATUS.md` with the measured before/after.
- [ ] Commit, push.

## Self-review

- Coverage: every in-scope script group has a task (job-os, files, goal planner: Task 2; notebook, work hub: Task 3; dashboard: Task 4). Office/Agent Canvas/panels.js/style.css are listed as out of scope with the reason.
- Names used across tasks: `loadPageModule`, `PAGE_MODULES`, `withNotebook`, `page_load_failed` — defined in Tasks 1-3.
- Risk to watch: tests that read page globals at boot (33 files mention JobOS/HermesDashboard/HermesOffice/Notebook/HermesFileManager); each needs an explicit `loadPageModule` call, which is the intended new contract.
