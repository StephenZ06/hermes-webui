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
            page.wait_for_selector(".resume-master, #resume-drop", timeout=20000)
            if page.query_selector(".resume-master"):
                page.click('[data-job-os-action="resume-replace"]')
            page.wait_for_selector("#resume-file", state="attached", timeout=20000)
            page.set_input_files("#resume-file", str(cv))
            card = page.wait_for_selector(".resume-master", timeout=20000)
            chips = card.inner_text()
        finally:
            browser.close()
    assert "cv.md" in chips and "words" in chips


def test_a_bare_job_offers_its_next_step_and_x_skips_it():
    sync_api = pytest.importorskip("playwright.sync_api")
    import sqlite3

    from tests._pytest_port import TEST_STATE_DIR

    tracked = _post("/api/job-os/jobs", {"title": f"Bare {uuid.uuid4().hex[:6]}", "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})["job"]
    found = _post("/api/job-os/jobs", {"title": f"Found {uuid.uuid4().hex[:6]}", "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})["job"]
    with sqlite3.connect(TEST_STATE_DIR / "webui_state" / "job_os" / "job_os.db") as conn:
        conn.execute("UPDATE jobs SET source='indeed' WHERE id=?", (found["id"],))
    card = lambda job: f'.pipe-card[data-board-job="{job["id"]}"]'
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "pipeline")
        try:
            page.evaluate("() => { localStorage.removeItem('hermes-job-os-pipeline'); window.JobOSState.pipelineSource = 'all'; window.JobOSState.pipelineMode = 'board'; return window.JobOS.refresh(); }")
            page.wait_for_selector(card(tracked), timeout=15000)
            # Without a description: a tracked job asks for one, an Indeed find offers to read its posting.
            tracked_step = page.inner_text(f'{card(tracked)} .pipe-card-actions .job-os-btn')
            found_step = page.inner_text(f'{card(found)} .pipe-card-actions .job-os-btn')
            page.click(f'{card(found)} .pipe-card-main')
            page.wait_for_selector("#job-os-detail", timeout=15000)
            has_fetch = bool(page.query_selector('#job-os-detail [data-job-os-action="job-details"]'))
            selected = page.evaluate(f"() => document.querySelector('{card(found)}').classList.contains('is-selected')")
            page.keyboard.press("x")
            page.wait_for_selector(f'.pipe-col[data-col="closed"] {card(found)}', timeout=15000)
        finally:
            browser.close()
    assert tracked_step == "Add description" and found_step == "Fetch details"
    assert has_fetch and selected
