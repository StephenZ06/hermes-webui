"""Jobs Settings layout: the section list beside one section at a time, each
section's groups readable at desktop and phone widths."""

import os

import pytest

from tests._pytest_port import BASE

SECTIONS = ("connections", "apify", "scout", "ai", "notifications", "applicant", "apply", "display")


def _open(page):
    page.goto(BASE + "/#jobs/settings", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("async () => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove()); await switchPanel('jobs'); }")
    page.wait_for_selector(".settings-layout", timeout=20000)


@pytest.mark.parametrize("width", [1440, 390])
def test_every_settings_section_fits_without_sideways_scroll(width):
    sync_api = pytest.importorskip("playwright.sync_api")
    shots = os.environ.get("JOB_OS_SHOTS")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": width, "height": 1000})
            _open(page)
            widths = {}
            for key in SECTIONS:
                page.evaluate("(k) => document.querySelector(`[data-job-os-action='settings-section'][data-section='${k}']`).click()", key)
                page.wait_for_selector(f".settings-page[data-page='{key}']", timeout=10000)
                page.wait_for_timeout(250)
                widths[key] = page.evaluate("() => [document.documentElement.scrollWidth, document.querySelector('.settings-page').scrollWidth, document.querySelector('.settings-page').clientWidth]")
                if shots:
                    page.screenshot(path=os.path.join(shots, f"settings-{key}-{width}.png"), full_page=True)
        finally:
            browser.close()
    for key, (doc, inner, client) in widths.items():
        assert doc <= width, (key, doc)
        assert inner <= client + 1, (key, inner, client)
