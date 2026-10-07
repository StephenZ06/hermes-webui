"""Resume Studio match check: the ring shows Luna's score of the master resume
against the picked job, as a percentage, green / yellow / red by band."""

import json
import sqlite3
import time
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE, TEST_STATE_DIR

DB = TEST_STATE_DIR / "webui_state" / "job_os" / "job_os.db"
RESUME = "Jane Doe\nData Analyst\n\n" + "Built SQL and Python dashboards for finance teams over four years. " * 8


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def _scored_job(title, score):
    job = _post("/api/job-os/jobs", {"title": title, "company": "Acme", "description": "SQL, Python, dashboards",
                                     "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})["job"]
    now = int(time.time()) + 3600  # newest, so the match check picks it first
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT INTO job_analyses (job_id, status, fit_score, verdict, data_json, requested_at, finished_at)"
                     " VALUES (?, 'done', ?, '', ?, ?, ?)",
                     (job["id"], score, json.dumps({"summary": f"Summary for {title}", "strengths": ["SQL"], "gaps": ["Banking"]}), now, now))
        conn.execute("UPDATE jobs SET status='analyzed', updated_at=? WHERE id=?", (now, job["id"]))
    return job


def test_the_ring_shows_the_score_and_band_of_the_picked_job():
    sync_api = pytest.importorskip("playwright.sync_api")
    _post("/api/job-os/resume", {"filename": "pasted.txt", "text": RESUME})
    marker = uuid.uuid4().hex[:6]
    weak = _scored_job(f"Weak {marker}", 34)
    fair = _scored_job(f"Fair {marker}", 62)
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(BASE + "/#jobs/resume-studio", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(".match-ring[data-band]", timeout=20000)
            page.evaluate("""(id) => { const s = document.querySelector('select[data-job-os-change="match-job"]');
              s.value = id; s.dispatchEvent(new Event('change', {bubbles: true})); }""", fair["id"])
            page.wait_for_selector('.match-ring[data-band="fair"]', timeout=15000)
            fair_ring = page.inner_text(".match-ring")
            fair_color = page.evaluate("() => getComputedStyle(document.querySelector('.match-ring')).getPropertyValue('--ring').trim()")
            summary = page.inner_text(".match-detail")
            page.evaluate("""(id) => { const s = document.querySelector('select[data-job-os-change="match-job"]');
              s.value = id; s.dispatchEvent(new Event('change', {bubbles: true})); }""", weak["id"])
            page.wait_for_selector('.match-ring[data-band="poor"]', timeout=15000)
            poor_ring = page.inner_text(".match-ring")
            poor_color = page.evaluate("() => getComputedStyle(document.querySelector('.match-ring')).getPropertyValue('--ring').trim()")
            theme = page.evaluate("""() => { const r = getComputedStyle(document.querySelector('.match-ring'));
              return {warning: r.getPropertyValue('--warning').trim(), error: r.getPropertyValue('--error').trim()}; }""")
        finally:
            browser.close()
    assert fair_ring.split() == ["62%", "Needs", "improvement"]
    assert poor_ring.split() == ["34%", "Terrible", "match"]
    assert fair_color == theme["warning"] and poor_color == theme["error"]  # the theme's yellow and red
    assert f"Summary for Fair {marker}" in summary
