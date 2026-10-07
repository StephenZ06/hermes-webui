"""Pipeline board: Apply records the application and moves the card; the
source tabs split Scout's Indeed finds from tracked jobs; the Add job form
saves a manual job with its details."""

import json
import sqlite3
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE, TEST_STATE_DIR

DB = TEST_STATE_DIR / "webui_state" / "job_os" / "job_os.db"


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def _get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=20).read())


def _open_jobs(page, hash_="#jobs/pipeline"):
    page.goto(BASE + "/" + hash_, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove()); localStorage.removeItem('hermes-job-os-pipeline'); }")
    page.evaluate("async () => { await switchPanel('jobs'); }")


def _move(page, card, value):
    page.evaluate("""([card, value]) => { const s = document.querySelector(card + ' select[data-job-os-change="board-move"]');
      s.value = value; s.dispatchEvent(new Event('change', {bubbles: true})); }""", [card, value])


def test_board_apply_records_the_application_and_moves_the_card():
    sync_api = pytest.importorskip("playwright.sync_api")
    url = f"https://jobs.example.test/{uuid.uuid4().hex}"
    job = _post("/api/job-os/jobs", {"title": f"Board {uuid.uuid4().hex[:6]}", "company": "Acme", "canonical_url": url})["job"]
    with sqlite3.connect(DB) as conn:  # a job whose resume is tailored and approved
        conn.execute("UPDATE jobs SET status='application_ready' WHERE id=?", (job["id"],))
    card = f'.pipe-card[data-board-job="{job["id"]}"]'
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.add_init_script("window.__opened = []; window.open = (u) => { window.__opened.push(u); return null; };")
            _open_jobs(page, "#jobs/applications")  # the old Applications link lands on the Pipeline board
            page.wait_for_selector(f'.pipe-col[data-col="ready"] {card}', timeout=15000)
            hash_after = page.evaluate("() => location.hash")
            page.click(f'{card} [data-job-os-action="board-apply"]')
            page.click("#appDialogConfirm")
            page.wait_for_selector(f'.pipe-col[data-col="applied"] {card}', timeout=15000)
            opened = page.evaluate("() => window.__opened")
            meta = page.inner_text(f"{card} .pipe-card-meta")
            _move(page, card, "screening")
            page.wait_for_selector(f'.pipe-col[data-col="interviewing"] {card}', timeout=15000)
            drawer = page.evaluate("() => !!document.querySelector('.job-drawer')")
        finally:
            browser.close()
    timeline = _get(f"/api/job-os/jobs/{job['id']}/timeline")
    assert opened == [url]
    assert "applied" in meta.lower()
    assert hash_after.startswith("#jobs/pipeline") or hash_after == "#jobs/applications"
    assert not drawer  # moving a card does not open the job
    assert any(e["type"] == "application_submitted" and e["data"]["method"] == "manual" for e in timeline["timeline"])


def test_source_tabs_and_the_add_job_form():
    sync_api = pytest.importorskip("playwright.sync_api")
    marker = uuid.uuid4().hex[:6]
    found = _post("/api/job-os/jobs", {"title": f"Indeed {marker}", "canonical_url": f"https://jobs.example.test/i-{marker}"})["job"]
    with sqlite3.connect(DB) as conn:  # what Scout saves: an Indeed posting
        conn.execute("UPDATE jobs SET source='indeed', country='Malaysia' WHERE id=?", (found["id"],))
    title = f"Tracked {marker}"
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _open_jobs(page)
            page.wait_for_selector(f'.pipe-card[data-board-job="{found["id"]}"] .pipe-source[data-source="indeed"]', timeout=15000)
            page.click('[data-job-os-action="job-form-new"] >> nth=0')
            page.wait_for_selector("#job-os-job-form", timeout=10000)
            page.fill("#job-os-job-form input[name='title']", title)
            page.fill("#job-os-job-form input[name='company']", "Initech")
            page.fill("#job-os-job-form input[name='canonical_url']", f"https://careers.initech.test/{marker}")
            page.fill("#job-os-job-form input[name='country']", "Singapore")
            page.fill("#job-os-job-form input[name='location']", "Jurong")
            page.fill("#job-os-job-form input[name='salary_text']", "SGD 6,000 / month")
            page.fill("#job-os-job-form textarea[name='description']", "SQL, Python and dashboards.")
            page.fill("#job-os-job-form textarea[name='note']", "Referred by Sam")
            page.click("#job-os-job-form button[type='submit']")
            page.wait_for_function("() => !document.querySelector('#job-os-job-form')", timeout=10000)
            card = page.wait_for_selector(f'.pipe-card:has-text("{title}")', timeout=15000)
            card_text = card.inner_text()
            page.click('[data-job-os-action="pipe-source"][data-source="manual"]')
            page.wait_for_selector('[data-job-os-action="pipe-source"][data-source="manual"].active', timeout=15000)
            page.wait_for_selector(f'.pipe-card:has-text("{title}")', timeout=15000)
            indeed_hidden = page.evaluate(f"() => !document.querySelector('.pipe-card[data-board-job=\"{found['id']}\"]')")
            page.click('[data-job-os-action="pipe-source"][data-source="indeed"]')
            page.wait_for_selector('[data-job-os-action="pipe-source"][data-source="indeed"].active', timeout=15000)
            page.wait_for_selector(f'.pipe-card[data-board-job="{found["id"]}"]', timeout=15000)
            manual_hidden = page.evaluate(f"() => ![...document.querySelectorAll('.pipe-card')].some(c => c.textContent.includes('{title}'))")
            remembered = page.evaluate("() => JSON.parse(localStorage.getItem('hermes-job-os-pipeline')).source")
        finally:
            browser.close()
    saved = next(j for j in _get("/api/job-os/jobs")["jobs"] if j["title"] == title)
    assert saved["source"] == "manual" and saved["status"] == "scraped"
    assert (saved["country"], saved["location"], saved["salary_text"]) == ("Singapore", "Jurong", "SGD 6,000 / month")
    assert "Jurong, Singapore" in card_text and "SGD 6,000 / month" in card_text and "MANUAL" in card_text.upper()
    assert indeed_hidden and manual_hidden and remembered == "indeed"
    notes = [e["data"]["text"] for e in _get(f"/api/job-os/jobs/{saved['id']}/timeline")["timeline"] if e["type"] == "note"]
    assert notes == ["Referred by Sam"]
