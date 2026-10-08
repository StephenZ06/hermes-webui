"""Jobs Settings: the header chip reports Firecrawl and opens Settings; edits
are kept while typing, saved with a revision, and survive a reload."""

import json
import urllib.request

import pytest

from tests._pytest_port import BASE


def _settings():
    return json.loads(urllib.request.urlopen(BASE + "/api/job-os/settings", timeout=20).read())


def test_settings_page_saves_and_reloads():
    sync_api = pytest.importorskip("playwright.sync_api")
    before = _settings()["settings"]
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            chip = page.wait_for_selector(".job-os-header .job-os-status[data-fc-state]", timeout=20000)
            chip_text = chip.inner_text()
            chip.click()
            page.wait_for_selector("#job-os-settings-form", timeout=20000)
            save = page.locator('[data-job-os-action="save-settings"]')
            clean_disabled = save.is_disabled()
            # One section shows at a time; an edit in one survives moving to another.
            page.click('.settings-nav-item[data-section="scout"]')
            page.fill('[data-setting="scout.max_results_per_search"]', "9")
            page.click('.settings-nav-item[data-section="ai"]')
            page.locator('label.job-os-toggle:has([data-setting="ai.auto_analyze"])').click()
            page.click('.settings-nav-item[data-section="scout"]')
            kept = page.input_value('[data-setting="scout.max_results_per_search"]')
            dirty = page.get_attribute(".job-os-savebar", "data-dirty")
            focused_kept = page.evaluate("() => !!document.activeElement")
            save.click()
            page.wait_for_function("() => document.querySelector('.job-os-savebar')?.dataset.dirty === 'false'", timeout=10000)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector("#job-os-settings-form", timeout=20000)
            page.click('.settings-nav-item[data-section="scout"]')
            hours = page.input_value('[data-setting="scout.max_results_per_search"]')
            page.click('.settings-nav-item[data-section="ai"]')
            reloaded = {"hours": hours, "auto": page.is_checked('[data-setting="ai.auto_analyze"]')}
        finally:
            browser.close()
    after = _settings()["settings"]
    # Put the shared test server back the way it was.
    urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/job-os/settings",
        data=json.dumps({"settings": {k: v for k, v in before.items() if k != "revision"}, "expected_revision": after["revision"]}).encode(),
        headers={"Content-Type": "application/json", "Origin": BASE}), timeout=20).read()
    assert "Firecrawl" in chip_text
    assert clean_disabled and dirty == "true" and focused_kept and kept == "9"
    assert after["revision"] == before["revision"] + 1
    assert after["scout"]["max_results_per_search"] == 9 and after["ai"]["auto_analyze"] is (not before["ai"]["auto_analyze"])
    assert reloaded == {"hours": "9", "auto": not before["ai"]["auto_analyze"]}
