"""The scheduled-job form's Model picker loads its catalog.

It referenced an undefined `editProfile` (copied from the profile form), so
every open threw "editProfile is not defined" and the picker stayed disabled
on "Default". It now loads the catalog for the profile chosen in the form.
"""
import pytest

from tests._pytest_port import BASE


def test_cron_form_model_picker_loads():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            warnings = []
            page.on("console", lambda m: warnings.append(m.text))
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('tasks'); openCronCreate(); }")
            page.wait_for_selector("#cronFormModel", timeout=10000)
            page.wait_for_timeout(2500)
            state = page.evaluate("""() => { const s = document.getElementById('cronFormModel');
              return {loaded: s.dataset.loaded, disabled: s.disabled}; }""")
        finally:
            browser.close()
    assert not [w for w in warnings if "Failed to load cron model picker" in w], warnings
    assert state == {"loaded": "1", "disabled": False}, state
