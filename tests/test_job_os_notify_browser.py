"""Settings -> Notifications shows email status and refuses manual sends until email is set up."""

import json
import urllib.error
import urllib.request

import pytest

from tests._pytest_port import BASE


def test_notification_status_renders_and_sends_need_setup():
    sync_api = pytest.importorskip("playwright.sync_api")
    req = urllib.request.Request(BASE + "/api/job-os/notifications/digest", data=b"{}",
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(req, timeout=20)
    status = json.loads(urllib.request.urlopen(BASE + "/api/job-os/notifications", timeout=20).read())["notifications"]
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(BASE + "/#jobs/settings", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.click('.settings-nav-item[data-section="notifications"]')
            page.wait_for_selector("#job-os-settings-notifications .job-os-notify-status", timeout=15000)
            note = page.inner_text("#job-os-settings-notifications .job-os-notify-status")
            disabled = page.is_disabled('[data-job-os-action="notify-digest"]') and page.is_disabled('[data-job-os-action="notify-check"]')
            # Employer replies need Gmail too: the switch is there, the check is not offered yet.
            outcomes = page.inner_text("#job-os-outcomes")
            outcomes_disabled = page.is_disabled('[data-job-os-action="notify-outcomes"]')
        finally:
            browser.close()
    assert refused.value.code == 400 and status["ready"] is False
    assert "Replies not checked yet" in note and disabled
    assert "Read employer replies" in outcomes and "forward" in outcomes.lower() and outcomes_disabled
