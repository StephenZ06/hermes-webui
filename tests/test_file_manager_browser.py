"""Browser coverage for the main Files destination."""

import pytest

from tests._pytest_port import BASE


@pytest.fixture()
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        instance = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            yield instance
        finally:
            instance.close()


def _open(browser, **context):
    page = browser.new_context(**context).new_page()
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach((node) => node.remove())")
    return page


def test_files_page_mounts_from_navigation(browser):
    page = _open(browser, viewport={"width": 1280, "height": 800})
    page.evaluate("async () => { await switchPanel('files'); }")
    page.wait_for_selector("#fileManagerRoot .file-manager-layout", timeout=15000)
    assert page.locator("main.main").evaluate("node => node.classList.contains('showing-files')")
    assert page.locator("#fileManagerRoot .files-workspaces").count() == 1


def test_files_page_has_no_phone_horizontal_overflow(browser):
    page = _open(browser, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page.evaluate("async () => { await switchPanel('files'); }")
    page.wait_for_selector("#fileManagerRoot .file-manager-layout", timeout=15000)
    assert page.evaluate("() => document.getElementById('mainFiles').scrollWidth <= document.getElementById('mainFiles').clientWidth + 1")
