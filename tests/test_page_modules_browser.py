"""Page scripts load the first time their page opens, once and in order
(static/page-modules.js; docs/superpowers/plans/2026-11-10-load-page-scripts-on-demand.md)."""

import pytest

from tests._pytest_port import BASE


def _open(sync_api, browser, path="/", remembered=None):
    tab = browser.new_page(viewport={"width": 1280, "height": 800})
    if remembered:
        # The page this tab was last on, as a reload remembers it ('chat', '#jobs').
        tab.add_init_script(f"sessionStorage.setItem('hermes-webui-panel-route', {remembered!r})")
    tab.scripts = []
    tab.on("request", lambda r: tab.scripts.append(r.url.split("/static/", 1)[1].split("?")[0])
           if r.resource_type == "script" and "/static/" in r.url else None)
    tab.goto(BASE + path, wait_until="load")
    tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    return tab


@pytest.fixture
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        instance = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            yield sync_api, instance
        finally:
            instance.close()


@pytest.fixture
def page(browser):
    return _open(*browser)


def test_an_unknown_page_module_rejects(page):
    assert page.evaluate("() => loadPageModule('nope').then(() => 'ok', e => e.message)") == "unknown page module: nope"


def test_asking_twice_loads_each_script_once(page):
    page.evaluate("async () => { await Promise.all([loadPageModule('files'), loadPageModule('files')]); }")
    assert page.scripts.count("file-manager.js") == 1, page.scripts
    assert page.evaluate("() => typeof window.HermesFileManager.mount") == "function"


def test_jobs_and_files_load_only_when_their_page_opens(page):
    at_boot = [s for s in page.scripts if s in ("job-os/render.js", "job-os/index.js", "file-manager.js")]
    assert at_boot == [], at_boot
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_function("() => window.JobOS && document.querySelector('#mainJobs .job-os, #jobOsRoot, [id^=jobOs], .job-os-shell')", timeout=15000)
    # state.js and api.js stay in index.html (Settings and routes use them).
    assert [s for s in page.scripts if s in ("job-os/render.js", "job-os/index.js")] == ["job-os/render.js", "job-os/index.js"]
    page.evaluate("async () => { await switchPanel('files'); }")
    page.wait_for_function("() => window.HermesFileManager", timeout=15000)
    assert page.scripts.count("file-manager.js") == 1


def test_a_page_whose_scripts_fail_says_so_and_retries(page):
    page.route("**/static/file-manager.js*", lambda route: route.abort())
    result = page.evaluate("async () => { const ok = await switchPanel('files'); return {ok, toast: (document.querySelector('.toast, #toast, [role=status]') || {}).textContent || ''}; }")
    assert result["ok"] is False, result
    page.unroute("**/static/file-manager.js*")
    page.evaluate("async () => { await switchPanel('chat'); await switchPanel('files'); }")
    page.wait_for_function("() => window.HermesFileManager", timeout=15000)


def test_notebook_and_work_hub_load_when_something_needs_them(page):
    moved = ("notebook/index.js", "work-hub.js", "goal-planner.js")
    assert [s for s in page.scripts if s in moved] == [], page.scripts
    # Opening a note from chat, the workspace panel or the Dashboard goes through withNotebook.
    assert page.evaluate("() => withNotebook(n => typeof n.openFrom)") == "function"
    page.evaluate("async () => { await switchPanel('notes'); }")
    page.wait_for_function("() => typeof window.loadWorkHubPanel === 'function' && document.getElementById('workHub')", timeout=15000)
    assert page.evaluate("() => typeof window.GoalPlanner") != "undefined"
    assert [s for s in page.scripts if s in moved] == ["notebook/index.js", "work-hub.js", "goal-planner.js"]


def test_the_workspace_work_hub_pane_loads_work_hub_when_it_is_first(page):
    assert "work-hub.js" not in page.scripts
    page.evaluate("() => switchRightPanelPane('plane')")
    page.wait_for_function("() => typeof window.renderWorkspaceWorkHub === 'function'", timeout=15000)
    assert page.scripts.count("work-hub.js") == 1


@pytest.fixture
def page_on_chat(browser):
    return _open(*browser, remembered="chat")


def test_landing_on_chat_leaves_the_dashboard_for_quiet_time(page_on_chat):
    at_start = list(page_on_chat.scripts)  # the fixture returns once boot is ready
    assert [s for s in at_start if s.startswith("dashboard/")] == [], at_start
    # It still arrives once the page is idle, so its first open needs no loader.
    page_on_chat.wait_for_function("() => !!window.HermesDashboard", timeout=20000)
    assert page_on_chat.evaluate("() => _currentPanel") == "chat"


def test_landing_on_the_dashboard_loads_it_early_and_shows_it(browser):
    tab = _open(*browser, path="/#dashboard")
    tab.wait_for_function("() => window.HermesDashboard && document.querySelector('#dashboardRoot .dash-body')", timeout=15000)
    assert tab.scripts.count("dashboard/index.js") == 1


def test_the_career_button_opens_the_dashboard_on_its_career_tab(page_on_chat):
    page_on_chat.evaluate("async () => { await openCareerDashboard(); }")
    page_on_chat.wait_for_function("() => document.querySelector('.dash-body')?.dataset.tab === 'career'", timeout=15000)
