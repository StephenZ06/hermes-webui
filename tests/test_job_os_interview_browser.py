"""Job detail shows a finished interview prep and offers it as a download."""

import json
import sqlite3
import time
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE, TEST_STATE_DIR

DB = TEST_STATE_DIR / "webui_state" / "job_os" / "job_os.db"


def test_interview_prep_panel_and_download():
    sync_api = pytest.importorskip("playwright.sync_api")
    req = urllib.request.Request(BASE + "/api/job-os/jobs", data=json.dumps({"title": f"Prep {uuid.uuid4().hex[:6]}", "company": "Acme",
                                 "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"}).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    job = json.loads(urllib.request.urlopen(req, timeout=20).read())["job"]
    data = {"questions": [{"question": "Why payments?", "why": "Motivation", "outline": "Five years at Acme", "supported": True},
                          {"question": "Kubernetes?", "why": "Infra", "outline": "Study the basics", "supported": False}],
            "stories": [], "ask_them": ["On-call?"], "research": [], "watch_outs": [], "markdown": "# Interview prep\n## Likely questions\n"}
    with sqlite3.connect(DB) as conn:
        conn.execute("UPDATE jobs SET status='interviewing' WHERE id=?", (job["id"],))
        conn.execute("INSERT INTO interview_preps (job_id, status, data_json, requested_at, finished_at) VALUES (?, 'done', ?, ?, ?)",
                     (job["id"], json.dumps(data), int(time.time()), int(time.time())))
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 1000})
            page.goto(BASE + "/#jobs/pipeline", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.evaluate(f"() => window.JobOS.openJob('{job['id']}')")
            page.wait_for_selector(".job-os-prep .prep-q", timeout=15000)
            gaps = page.locator('.prep-q[data-gap="true"]').count()
            button = page.inner_text('[data-job-os-action="job-interview"]')
            href = page.get_attribute(".job-os-prep a[download]", "href")
            response = page.request.get(BASE + href)
            download = (response.status, response.text()[:16])
        finally:
            browser.close()
    assert gaps == 1 and button == "Refresh interview prep"
    assert download == (200, "# Interview prep")
