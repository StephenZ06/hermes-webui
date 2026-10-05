"""Applications board: Apply opens the posting, records the application, and moves the card."""

import json
import sqlite3
import urllib.error
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


def test_board_apply_records_the_application_and_moves_the_card():
    sync_api = pytest.importorskip("playwright.sync_api")
    url = f"https://jobs.example.test/{uuid.uuid4().hex}"
    job = _post("/api/job-os/jobs", {"title": f"Board {uuid.uuid4().hex[:6]}", "company": "Acme", "canonical_url": url})["job"]
    with sqlite3.connect(DB) as conn:  # a job whose resume is tailored and approved
        conn.execute("UPDATE jobs SET status='application_ready' WHERE id=?", (job["id"],))
    card = f'.board-card[data-board-job="{job["id"]}"]'
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.add_init_script("window.__opened = []; window.open = (u) => { window.__opened.push(u); return null; };")
            page.goto(BASE + "/#jobs/applications", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(f'.board-col[data-col="ready"] {card}', timeout=15000)
            page.click(f'{card} [data-job-os-action="board-apply"]')
            page.click("#appDialogConfirm")
            page.wait_for_selector(f'.board-col[data-col="applied"] {card}', timeout=15000)
            opened = page.evaluate("() => window.__opened")
            meta = page.inner_text(f"{card} .board-meta")
            page.select_option(f'{card} select[data-job-os-change="board-outcome"]', "screening")
            page.wait_for_selector(f'.board-col[data-col="interviewing"] {card}', timeout=15000)
            view = page.evaluate("() => window.JobOSState.activeView")
        finally:
            browser.close()
    timeline = _get(f"/api/job-os/jobs/{job['id']}/timeline")
    assert opened == [url]
    assert meta.startswith("Applied")
    assert view == "applications"  # the outcome select does not open the job
    assert any(e["type"] == "application_submitted" and e["data"]["method"] == "manual" for e in timeline["timeline"])


def test_awaiting_approval_card_shows_the_filled_form_and_can_be_cancelled():
    sync_api = pytest.importorskip("playwright.sync_api")
    import base64
    import time

    job = _post("/api/job-os/jobs", {"title": f"Auto {uuid.uuid4().hex[:6]}", "company": "Acme",
                                     "canonical_url": f"https://jobs.lever.co/acme/{uuid.uuid4().hex}"})["job"]
    shot = "20261006-101010-preview-filled.png"
    proof = TEST_STATE_DIR / "webui_state" / "job_os" / "applications" / job["id"]
    proof.mkdir(parents=True, exist_ok=True)
    (proof / shot).write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
    now = int(time.time())
    with sqlite3.connect(DB) as conn:
        conn.execute("UPDATE jobs SET status='awaiting_approval' WHERE id=?", (job["id"],))
        conn.execute("INSERT INTO apply_runs (id, job_id, mode, ats, trigger, status, result_json, created_at, finished_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (uuid.uuid4().hex, job["id"], "preview", "lever", "manual", "filled",
                      json.dumps({"screenshots": [shot], "filled": [{"field": "email", "label": "Email"}]}), now, now))
    card = f'.board-card[data-board-job="{job["id"]}"]'
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(BASE + "/#jobs/applications", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(f'.board-col[data-col="attention"] {card} .board-proof img', timeout=15000)
            page.wait_for_function(f"() => document.querySelector('{card} .board-proof img').naturalWidth === 1", timeout=10000)
            has_send = page.is_visible(f'{card} [data-job-os-action="board-approve"]')
            page.click(f'{card} [data-job-os-action="board-cancel-apply"]')
            page.wait_for_selector(f'.board-col[data-col="attention"] {card}, .board-col[data-col="ready"] {card}', timeout=15000)
            page.wait_for_function(f"() => !document.querySelector('{card} [data-job-os-action=\"board-approve\"]')", timeout=15000)
        finally:
            browser.close()
    assert has_send
    for bad in ("..%2F..%2Fsettings.json", "x.png", shot.replace(".png", ".txt")):
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(f"{BASE}/api/job-os/jobs/{job['id']}/proof/{bad}", timeout=20)
        assert missing.value.code == 404
    assert _get(f"/api/job-os/jobs/{job['id']}")["job"]["status"] == "application_ready"
