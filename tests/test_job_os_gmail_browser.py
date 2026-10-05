"""Connect Gmail form: errors show inline, the password never stays in the page."""

import json
import urllib.request

import pytest

from tests._pytest_port import BASE


def test_gmail_form_rejects_a_malformed_app_password_inline():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(BASE + "/#jobs/settings", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector("#job-os-gmail-password", timeout=20000)
            page.fill("#job-os-gmail-address", "me@gmail.com")
            page.fill("#job-os-gmail-password", "too-short")
            page.press("#job-os-gmail-password", "Enter")
            page.wait_for_function("() => document.querySelector('.job-os-gmail-msg')?.dataset.tone === 'error'", timeout=10000)
            state = page.evaluate("""() => ({msg: document.querySelector('.job-os-gmail-msg').textContent,
              pw: document.getElementById('job-os-gmail-password').value,
              inState: JSON.stringify(window.JobOSState).includes('too-short'),
              savebarDirty: document.querySelector('.job-os-savebar')?.dataset.dirty})""")
        finally:
            browser.close()
    status = json.loads(urllib.request.urlopen(BASE + "/api/job-os/settings", timeout=20).read())["status"]["gmail"]
    assert "16 letters" in state["msg"]
    assert state["pw"] == "" and not state["inState"], "the password is cleared and never kept in page state"
    assert state["savebarDirty"] == "false", "Gmail fields are not part of the settings draft"
    assert status["address"] is False and status["app_password"] is False
