"""Resume Studio: tailored versions list, editor, unverified-number warning, save, export."""

import json
import sqlite3
import time
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE, TEST_STATE_DIR

DB = TEST_STATE_DIR / "webui_state" / "job_os" / "job_os.db"


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def test_studio_flags_unverified_numbers_and_saves_a_fix():
    sync_api = pytest.importorskip("playwright.sync_api")
    _post("/api/job-os/resume", {"filename": "cv.md", "text": "Jane Doe\n" + "Built Python services for 8 years. " * 12})
    title = f"Studio {uuid.uuid4().hex[:6]}"
    job = _post("/api/job-os/jobs", {"title": title, "company": "Acme", "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})["job"]
    now = int(time.time())
    with sqlite3.connect(DB) as conn:  # seed a finished tailoring (the test server has no AI model)
        conn.execute("UPDATE jobs SET status='resume_ready' WHERE id=?", (job["id"],))
        conn.execute("INSERT INTO job_documents (id, job_id, kind, status, content, notes_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                     (uuid.uuid4().hex, job["id"], "resume", "needs_review", "# Jane Doe\n- Led 15 engineers.\n- Python for 8 years.",
                      json.dumps({"unverified": ["15"], "coverage": {"found": ["Python"], "missing": ["Go"], "score": 50},
                                  "changes": [{"what": "Led with Python", "why": "Must-have"}]}), now, now))
        conn.execute("INSERT INTO job_documents (id, job_id, kind, status, content, notes_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                     (uuid.uuid4().hex, job["id"], "cover_letter", "ready", "Dear Acme team,", "{}", now, now))
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(BASE + "/#jobs/resume-studio", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.click(f'.studio-item[data-job-id="{job["id"]}"]')
            page.wait_for_selector("#studio-text", timeout=15000)
            warning = page.inner_text(".studio-warning")
            marked = page.inner_text(".studio-preview mark")
            coverage = page.inner_text(".cov-score")
            save_disabled = page.is_disabled('[data-job-os-action="studio-save"]')
            page.fill("#studio-text", "# Jane Doe\n- Led engineers.\n- Python for 8 years.")
            page.click('[data-job-os-action="studio-save"]')
            page.wait_for_selector(".studio-warning", state="detached", timeout=10000)
            response = page.request.get(BASE + page.get_attribute('a.job-os-btn[href*="format=docx"]', "href"))
            docx = (response.status, response.body()[:2])
            page.click('[data-job-os-action="studio-ready"]')
            page.wait_for_function("() => !document.querySelector('[data-job-os-action=\"studio-ready\"]')", timeout=10000)
        finally:
            browser.close()
    status = _post_get(f"/api/job-os/jobs/{job['id']}")["job"]["status"]
    assert "15" in warning and marked == "15" and coverage == "50%" and save_disabled
    assert docx == (200, b"PK")
    assert status == "application_ready"


def _post_get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=20).read())
