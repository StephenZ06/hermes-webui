"""Dashboard Automations card, and the enter animation when switching Jobs views."""

import pytest

from tests._pytest_port import BASE


def test_dashboard_lists_automations_and_views_animate_in():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(BASE + "/#jobs/dashboard", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(".automations-card .automation-row", timeout=15000)
            rows = page.evaluate("() => [...document.querySelectorAll('.automation-row')].map(r => [r.querySelector('strong').textContent, r.dataset.on])")
            # Each automation opens Settings at the section that configures it.
            page.click(".automation-row[data-section='scout']")
            page.wait_for_selector(".job-os-shell[data-view='settings'] .job-os-content.is-entering", state='attached', timeout=10000)
            page.wait_for_selector("#job-os-settings-scout.is-focus", timeout=10000)
            page.wait_for_timeout(500)
            page.evaluate("() => { window.__before = document.querySelector('.job-os-content'); }")
            page.evaluate("async () => { await window.JobOS.refresh(); }")
            same_view_again = page.evaluate("() => { const now = document.querySelector('.job-os-content'); return now !== window.__before && now.classList.contains('is-entering'); }")
        finally:
            browser.close()
    assert [name for name, _ in rows] == ["Scout searches", "Luna fit analysis", "Match alert emails", "Daily digest", "Reply commands"]
    assert same_view_again is False  # a refresh of the same view does not replay the animation
