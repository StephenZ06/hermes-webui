"""Scout UI: create/edit/pause/delete Indeed searches; Run is blocked while
Firecrawl is not ready; a job opens its details in the Pipeline drawer."""

import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def _open(pw, view):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(BASE + f"/#jobs/{view}", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('jobs'); }")
    return browser, page


def test_scout_search_lifecycle_and_blocked_run():
    sync_api = pytest.importorskip("playwright.sync_api")
    name = f"Scout {uuid.uuid4().hex[:6]}"
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "scout")
        try:
            page.wait_for_selector('[data-job-os-action="scout-new"]', timeout=20000)
            banner = page.inner_text(".scout-banner") if page.query_selector(".scout-banner") else ""
            page.click('[data-job-os-action="scout-new"]')
            page.click('#job-os-search-form button[type="submit"]')
            page.wait_for_function("() => document.querySelector('#job-os-search-form .job-os-error').textContent.includes('Keywords')", timeout=10000)
            page.fill('input[name="keywords"]', "python backend")
            page.fill('input[name="name"]', name)
            # Choosing the country re-renders the form with that Indeed site; typed values stay.
            page.evaluate("""() => { const s = document.querySelector('#job-os-search-form select[name="country"]');
              s.value = 'my'; s.dispatchEvent(new Event('change', {bubbles: true})); }""")
            page.wait_for_selector('#scout-form code:has-text("malaysia.indeed.com")', timeout=10000)
            kept = page.input_value('input[name="keywords"]')
            page.fill('input[name="locations"]', "Kuala Lumpur, Penang")
            page.evaluate("""() => { const s = document.querySelector('#job-os-search-form select[name="posted_within_days"]'); s.value = '7'; }""")
            page.click('#job-os-search-form button[type="submit"]')
            card = page.wait_for_selector(f'.scout-search:has-text("{name}")', timeout=10000)
            sid = card.get_attribute("data-search-id")
            run_disabled = page.is_disabled(f'[data-job-os-action="scout-run"][data-search-id="{sid}"]')
            chips = card.inner_text()
            page.click(f'label.job-os-toggle:has([data-job-os-action="scout-toggle"][data-search-id="{sid}"])')
            page.wait_for_selector(f'.scout-search.is-off[data-search-id="{sid}"]', timeout=10000)
            page.click(f'[data-job-os-action="scout-edit"][data-search-id="{sid}"]')
            page.fill('input[name="keywords"]', "python platform")
            page.click('#job-os-search-form button[type="submit"]')
            page.wait_for_selector(f'.scout-search[data-search-id="{sid}"]:has-text("python platform")', timeout=10000)
            page.click(f'[data-job-os-action="scout-delete"][data-search-id="{sid}"]', force=True)
            page.wait_for_selector("#appDialogConfirm", state="visible", timeout=10000)
            page.click("#appDialogConfirm")
            page.wait_for_selector(f'.scout-search[data-search-id="{sid}"]', state="detached", timeout=10000)
        finally:
            browser.close()
    assert "Firecrawl" in banner and run_disabled, "Run waits for a ready Firecrawl"
    assert kept == "python backend"
    assert all(word in chips for word in ("Malaysia", "Kuala Lumpur", "Penang", "Last 7 days"))


def test_a_job_opens_its_details_in_pipeline():
    sync_api = pytest.importorskip("playwright.sync_api")
    job = _post("/api/job-os/jobs", {"title": f"Detail {uuid.uuid4().hex[:6]}", "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}", "company": "Acme"})["job"]
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "pipeline")
        try:
            page.evaluate("() => { window.JobOSState.pipelineSource = 'all'; window.JobOSState.pipelineMode = 'board'; return window.JobOS.refresh(); }")
            page.click(f'.pipe-card[data-board-job="{job["id"]}"] .pipe-card-main')
            detail = page.wait_for_selector("#job-os-detail", timeout=15000)
            text = detail.inner_text()
            href = page.get_attribute("#job-os-detail a.job-os-btn", "href")
            page.click('#job-os-detail [data-job-os-action="job-close"]')
            page.wait_for_selector("#job-os-detail", state="detached", timeout=10000)
        finally:
            browser.close()
    assert job["title"] in text and "Acme" in text and href == job["canonical_url"]
