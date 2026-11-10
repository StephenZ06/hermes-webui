"""Page scripts load the first time their page opens, once and in order
(static/page-modules.js; docs/superpowers/plans/2026-11-10-load-page-scripts-on-demand.md)."""

import pytest

from tests._pytest_port import BASE


def _open(sync_api, browser, path="/"):
    tab = browser.new_page(viewport={"width": 1280, "height": 800})
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
