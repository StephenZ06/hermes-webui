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
