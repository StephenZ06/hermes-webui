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


def _drag(page, card, column, *, refresh_midway=False):
    """Drag a card onto a column with the mouse, the way a person does. With
    refresh_midway, the page refreshes while the card is in the air."""
    page.evaluate("""([card, column]) => { const target = document.querySelector(`.pipe-col[data-col="${column}"]`);
      target.scrollIntoView({block: 'nearest', inline: 'end'}); document.querySelector(card).scrollIntoView({block: 'nearest', inline: 'nearest'}); }""", [card, column])
    src = page.locator(f"{card} .pipe-card-title").bounding_box()
    page.mouse.move(src["x"] + 10, src["y"] + 5)
    page.mouse.down()
    page.mouse.move(src["x"] + 30, src["y"] + 20, steps=4)
    dst = page.locator(f'.pipe-col[data-col="{column}"] .pipe-col-head').bounding_box()
    page.mouse.move(dst["x"] + dst["width"] / 2, dst["y"] + 40, steps=12)
    if refresh_midway:
        # A job arrives (as from a Scout run) and the page refreshes while the card is held.
        _post("/api/job-os/jobs", {"title": f"Arrived {uuid.uuid4().hex[:6]}", "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})
        page.evaluate("() => window.JobOS.refresh()")
        page.wait_for_timeout(700)
        page.mouse.move(dst["x"] + dst["width"] / 2 + 4, dst["y"] + 44, steps=3)
    page.mouse.up()


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
            # Dragged to Interview with a refresh while it is in the air, then back to Applied.
            _drag(page, card, "interview", refresh_midway=True)
            page.wait_for_selector(f'.pipe-col[data-col="interview"] {card}', timeout=15000)
            page.wait_for_function(f"() => document.querySelector('{card}')?.dataset.status === 'interviewing'", timeout=15000)
            _drag(page, card, "applied")
            page.wait_for_function(f"() => document.querySelector('{card}')?.dataset.status === 'submitted'", timeout=15000)
            back_in_applied = page.evaluate(f"() => !!document.querySelector('.pipe-col[data-col=\"applied\"] {card}')")
            drawer = page.evaluate("() => !!document.querySelector('.job-drawer')")
        finally:
            browser.close()
    timeline = _get(f"/api/job-os/jobs/{job['id']}/timeline")
    assert opened == [url]
    assert "applied" in meta.lower()
    assert hash_after.startswith("#jobs/pipeline") or hash_after == "#jobs/applications"
    assert not drawer  # moving a card does not open the job
    assert back_in_applied, "a card dragged forward can be dragged back"
    moves = [e["data"]["to"] for e in timeline["timeline"] if e["type"] == "status_changed"]
    assert moves[-2:] == ["interviewing", "submitted"]
    assert [e["type"] for e in timeline["timeline"]].count("application_submitted") == 1
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
            # A site tab redraws in the same click, from the board already loaded.
            instant = page.evaluate("""() => { document.querySelector('[data-job-os-action="pipe-source"][data-source="all"]').click();
              return document.querySelector('[data-job-os-action="pipe-source"][data-source="all"]').classList.contains('active'); }""")
            # The search box narrows the board as you type and keeps the focus.
            page.fill("#job-os-pipe-search", title)
            page.wait_for_function(f"() => !document.querySelector('.pipe-card[data-board-job=\"{found['id']}\"]')", timeout=5000)
            searched = page.evaluate(f"""() => ({{shown: [...document.querySelectorAll('.pipe-card')].map(c => c.textContent.includes('{title}')),
              focused: document.activeElement && document.activeElement.id === 'job-os-pipe-search'}})""")
            page.keyboard.press("Escape")
            page.wait_for_selector(f'.pipe-card[data-board-job="{found["id"]}"]', timeout=5000)
        finally:
            browser.close()
    saved = next(j for j in _get("/api/job-os/jobs")["jobs"] if j["title"] == title)
    assert saved["source"] == "manual" and saved["status"] == "scraped"
    assert (saved["country"], saved["location"], saved["salary_text"]) == ("Singapore", "Jurong", "SGD 6,000 / month")
    assert "Jurong, Singapore" in card_text and "SGD 6,000 / month" in card_text and "MANUAL" in card_text.upper()
    assert indeed_hidden and manual_hidden and remembered == "indeed"
    assert instant and searched == {"shown": [True], "focused": True}
    notes = [e["data"]["text"] for e in _get(f"/api/job-os/jobs/{saved['id']}/timeline")["timeline"] if e["type"] == "note"]
    assert notes == ["Referred by Sam"]


def test_the_board_scrolls_from_a_bar_at_the_bottom_of_the_view_and_by_dragging_empty_space():
    sync_api = pytest.importorskip("playwright.sync_api")
    for n in range(10):  # enough cards that the board is taller than the view
        _post("/api/job-os/jobs", {"title": f"Scroll {n} {uuid.uuid4().hex[:6]}", "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"], ignore_default_args=["--hide-scrollbars"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 700})
            _open_jobs(page)
            page.wait_for_selector(".pipe-board .pipe-card", timeout=15000)
            page.wait_for_timeout(400)
            bar = page.locator(".pipe-hscroll").bounding_box()
            board_bottom = page.locator(".pipe-board").bounding_box()
            head = page.locator('.pipe-col[data-col="ready"] .pipe-col-head').bounding_box()
            # Press on empty column space (below the header, no card there) and drag left.
            page.mouse.move(head["x"] + head["width"] / 2, head["y"] + 120)
            page.mouse.down()
            page.mouse.move(head["x"] - 150, head["y"] + 120, steps=10)
            page.mouse.up()
            page.wait_for_timeout(600)
            panned = page.evaluate("() => [document.querySelector('.pipe-board').scrollLeft, document.querySelector('.pipe-hscroll').scrollLeft]")
            page.evaluate("() => { document.querySelector('.pipe-hscroll').scrollLeft = 0; }")
            page.wait_for_function("() => document.querySelector('.pipe-board').scrollLeft === 0", timeout=3000)
            drawer = page.evaluate("() => !!document.querySelector('.job-drawer')")
        finally:
            browser.close()
    assert board_bottom["y"] + board_bottom["height"] > 700, "the board runs below the view"
    assert 650 < bar["y"] + bar["height"] <= 700, bar  # the bar is on screen, at the bottom
    assert panned[0] > 100 and abs(panned[0] - panned[1]) <= 1, panned
    assert not drawer
