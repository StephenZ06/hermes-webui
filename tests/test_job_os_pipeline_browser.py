"""Resume Studio upload and Pipeline triage."""

import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE

RESUME = "Jane Doe\nSenior Backend Engineer\n" + "Built Python services on AWS with Postgres for 8 years. " * 8


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


def test_resume_upload_through_the_file_picker(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    cv = tmp_path / "cv.md"
    cv.write_text(RESUME)
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "resume-studio")
        try:
            if page.query_selector(".resume-master"):
                page.click('[data-job-os-action="resume-replace"]')
            page.wait_for_selector("#resume-file", state="attached", timeout=20000)
            page.set_input_files("#resume-file", str(cv))
            card = page.wait_for_selector(".resume-master", timeout=20000)
            chips = card.inner_text()
        finally:
            browser.close()
    assert "cv.md" in chips and "words" in chips


def test_a_bare_job_offers_fetch_details_and_x_skips_it():
    sync_api = pytest.importorskip("playwright.sync_api")
    job = _post("/api/job-os/jobs", {"title": f"Bare {uuid.uuid4().hex[:6]}", "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})["job"]
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "pipeline")
        try:
            page.click(f'.job-os-job-card[data-job-id="{job["id"]}"]')
            page.wait_for_selector("#job-os-detail", timeout=15000)
            has_fetch = bool(page.query_selector('[data-job-os-action="job-details"]'))
            selected = page.evaluate(f"() => document.querySelector('.job-os-job-card[data-job-id=\"{job['id']}\"]').classList.contains('is-selected')")
            page.keyboard.press("x")
            page.wait_for_function(f"() => document.querySelector('.job-os-job-card[data-job-id=\"{job['id']}\"] .job-os-badge')?.textContent === 'Skipped'", timeout=15000)
        finally:
            browser.close()
    assert has_fetch and selected
