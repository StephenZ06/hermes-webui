"""Jobs on a phone: hold-to-drag cards, centred close buttons that answer at once,
Settings > Connections layout, fading strips, no highlight left on cards."""

import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE

PHONE = {"viewport": {"width": 430, "height": 932}, "is_mobile": True, "has_touch": True}


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def _job(title=None):
    return _post("/api/job-os/jobs", {"title": title or f"Phone {uuid.uuid4().hex[:6]}", "company": "Acme",
                                      "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})["job"]


def _open(pw, hash_):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(**PHONE)
    page.goto(BASE + "/" + hash_, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("async () => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove()); localStorage.removeItem('hermes-job-os-pipeline'); await switchPanel('jobs'); }")
    page.wait_for_selector(".job-os-content", timeout=20000)
    return browser, page


def _touch(cdp, kind, x, y):
    points = [] if kind == "touchEnd" else [{"x": x, "y": y}]
    cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})


def test_a_held_card_can_be_dragged_to_another_column_with_a_finger():
    sync_api = pytest.importorskip("playwright.sync_api")
    job = _job()
    card = f'.pipe-card[data-board-job="{job["id"]}"]'
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            page.wait_for_selector(card, timeout=15000)
            assert page.get_attribute(card, "draggable") is None, "touch screens use hold-and-drag, not native drag"
            page.evaluate("(sel) => document.querySelector(sel).scrollIntoView({block: 'center'})", card)
            box = page.locator(f"{card} .pipe-card-name").bounding_box()
            # The next column peeks in at the right edge of the screen: drop there.
            next_col = page.evaluate("() => document.querySelectorAll('.pipe-col')[1].dataset.col")
            peek = page.locator(".pipe-col").nth(1).bounding_box()
            cdp = page.context.new_cdp_session(page)
            x, y = box["x"] + 20, box["y"] + 6
            dest = {"x": min(peek["x"] + 12, 425), "y": y + 30, "width": 0}
            _touch(cdp, "touchStart", x, y)
            page.wait_for_timeout(120)
            assert page.evaluate("() => !document.querySelector('.pipe-card-ghost')"), "not lifted before the hold"
            page.wait_for_timeout(450)
            assert page.evaluate("() => !!document.querySelector('.pipe-card-ghost')"), "lifted after the hold"
            steps = 10
            for i in range(1, steps + 1):
                _touch(cdp, "touchMove", x + (dest["x"] - x) * i / steps, y + (dest["y"] - y) * i / steps)
                page.wait_for_timeout(20)
            assert page.evaluate("() => !!document.querySelector('.pipe-col.drop-target')")
            _touch(cdp, "touchEnd", 0, 0)
            col = page.evaluate("(sel) => document.querySelector(sel)?.closest('.pipe-col')?.dataset.col", card)
            assert col == next_col, (col, next_col)
            page.wait_for_function("() => !document.querySelector('.pipe-card-ghost')", timeout=5000)
        finally:
            browser.close()


def test_a_quick_swipe_over_a_card_still_scrolls_and_does_not_lift_it():
    sync_api = pytest.importorskip("playwright.sync_api")
    job = _job()
    card = f'.pipe-card[data-board-job="{job["id"]}"]'
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            page.wait_for_selector(card, timeout=15000)
            box = page.locator(f"{card} .pipe-card-name").bounding_box()
            cdp = page.context.new_cdp_session(page)
            x, y = box["x"] + 20, box["y"] + 6
            _touch(cdp, "touchStart", x, y)
            for i in range(1, 6):
                _touch(cdp, "touchMove", x, y - i * 12)
                page.wait_for_timeout(30)
            page.wait_for_timeout(500)
            assert page.evaluate("() => !document.querySelector('.pipe-card-ghost')")
            _touch(cdp, "touchEnd", 0, 0)
        finally:
            browser.close()


def test_close_buttons_centre_their_icon_and_close_before_the_server_answers():
    sync_api = pytest.importorskip("playwright.sync_api")
    job = _job()
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            page.wait_for_selector(f'.pipe-card[data-board-job="{job["id"]}"]', timeout=15000)
            page.locator(f'.pipe-card[data-board-job="{job["id"]}"] .pipe-card-main').click()
            page.wait_for_selector("#job-os-detail")
            page.wait_for_timeout(500)
            off = page.evaluate("""() => { const b = document.querySelector('.job-os-detail-close').getBoundingClientRect();
              const i = document.querySelector('.job-os-detail-close svg').getBoundingClientRect();
              return [Math.abs(b.x + b.width / 2 - (i.x + i.width / 2)), Math.abs(b.y + b.height / 2 - (i.y + i.height / 2))]; }""")
            assert max(off) < 0.75, off
            # A slow server: the drawer must still go on the first tap.
            page.route("**/api/job-os/**", lambda route: (page.wait_for_timeout(1500), route.continue_()))
            page.tap(".job-os-detail-close")
            page.wait_for_selector("#job-os-detail", state="detached", timeout=700)
            assert page.evaluate("() => !document.querySelector('.pipe-card.is-selected')"), "closed job's card keeps no highlight"
            page.unroute("**/api/job-os/**")
        finally:
            browser.close()


def test_a_job_opens_over_scout_without_leaving_it():
    sync_api = pytest.importorskip("playwright.sync_api")
    job = _job()
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/scout")
        try:
            page.evaluate("(id) => JobOS.openJob(id)", job["id"])
            page.wait_for_selector("#job-os-detail", timeout=10000)
            assert page.evaluate("() => JobOSState.activeView") == "scout"
            assert page.evaluate("() => location.hash").startswith("#jobs/scout")
            page.tap(".job-os-detail-close")
            page.wait_for_selector("#job-os-detail", state="detached", timeout=5000)
        finally:
            browser.close()


def _connections(page):
    page.evaluate("""async () => {
      JobOSState.activeView = 'settings'; JobOSState.settingsSection = 'connections';
      await JobOS.refresh();
      JobOSState.settingsStatus = Object.assign({}, JobOSState.settingsStatus, {gmail: {address: true, app_password: true, address_hint: 'h***@gmail.com', scope: 'shared'}});
      document.getElementById('jobOsRoot').innerHTML = JobOSRender.shell(JobOSState);
    }""")
    page.wait_for_selector("#job-os-gmail .job-os-inline-select")


def test_connections_fill_the_card_and_gmail_actions_sit_below_the_sender_choice():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/settings")
        try:
            _connections(page)
            m = page.evaluate("""() => {
              const box = (el) => { const r = el.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height, r: r.right}; };
              const conn = document.querySelector('#job-os-gmail');
              const pick = conn.querySelector('.job-os-inline-select');
              const trigger = pick.querySelector('.themed-select-trigger') || pick.querySelector('select');
              const buttons = [...conn.querySelectorAll('.job-os-actions .job-os-btn')].map(box);
              return {conn: box(conn), pick: box(pick), trigger: box(trigger), buttons,
                labels: [...conn.querySelectorAll('.job-os-actions .job-os-btn')].map((b) => b.textContent.trim()),
                test: box(document.querySelector('[data-job-os-action="test-firecrawl"]')),
                site: box(document.querySelector('.site-health-row'))};
            }""")
            assert m["labels"] == ["Send test email", "Replace", "Disconnect"]
            assert m["pick"]["y"] + m["pick"]["h"] <= m["buttons"][0]["y"] + 1, "the three buttons come after the sender choice"
            assert len({round(b["y"]) for b in m["buttons"]} ) == 1, "one row"
            assert abs(m["trigger"]["h"] - m["buttons"][0]["h"]) <= 1, (m["trigger"], m["buttons"][0])
            gaps = [round(m["buttons"][i + 1]["x"] - m["buttons"][i]["r"], 1) for i in range(2)]
            assert abs(gaps[0] - gaps[1]) <= 0.6, gaps
            assert abs(m["buttons"][0]["x"] - m["conn"]["x"] - (m["conn"]["r"] - m["buttons"][2]["r"])) <= 1.5, "buttons reach both edges of the card"
            assert abs(m["test"]["w"] - (m["conn"]["w"] - (m["buttons"][0]["x"] - m["conn"]["x"]) * 2)) <= 1.5, "Test connection spans the card"
            assert abs((m["site"]["x"] + m["site"]["w"]) - (m["buttons"][2]["r"])) <= 1.5, "job site rows reach the right edge"
        finally:
            browser.close()


def test_settings_save_bar_never_sits_over_the_last_fields():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/settings")
        try:
            page.evaluate("""async () => { JobOSState.activeView = 'settings'; JobOSState.settingsSection = 'applicant'; JobOSState.settingsDirty = true; await JobOS.refresh();
              JobOSState.settingsDirty = true; document.getElementById('jobOsRoot').innerHTML = JobOSRender.shell(JobOSState);
              const m = document.getElementById('mainJobs'); m.scrollTop = m.scrollHeight; }""")
            page.wait_for_timeout(500)
            gap = page.evaluate("""() => { const bar = document.querySelector('.job-os-savebar').getBoundingClientRect();
              const last = [...document.querySelectorAll('.job-os-settings > *')].filter((e) => !e.classList.contains('job-os-savebar')).pop().getBoundingClientRect();
              return bar.top - last.bottom; }""")
            assert gap >= 0, gap
        finally:
            browser.close()


def test_page_titles_have_no_description_on_a_phone():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/dashboard")
        try:
            assert page.evaluate("() => getComputedStyle(document.querySelector('.job-os-header p')).display") == "none"
        finally:
            browser.close()


def test_the_pipeline_filter_strip_fades_where_more_lies_beyond_the_edge():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            strip = ".pipe-toolbar > .seg:first-child"
            page.wait_for_selector(strip + "[data-scroll-fading]", timeout=10000)
            read = lambda: page.evaluate("""(sel) => { const e = document.querySelector(sel); const s = getComputedStyle(e);
              return [parseFloat(e.style.getPropertyValue('--fade-l')), parseFloat(e.style.getPropertyValue('--fade-r')), (s.maskImage || s.webkitMaskImage || '').slice(0, 15)]; }""", strip)
            left, right, mask = read()
            assert left == 0 and right > 20 and mask.startswith("linear-gradient"), (left, right, mask)
            page.evaluate("(sel) => { const e = document.querySelector(sel); e.scrollLeft = 10; }", strip)
            page.wait_for_timeout(100)
            left, right, _ = read()
            assert 8 < left < 12 and right > 20, (left, right)
            page.evaluate("(sel) => { const e = document.querySelector(sel); e.scrollLeft = e.scrollWidth; }", strip)
            page.wait_for_timeout(100)
            left, right, _ = read()
            assert left > 20 and right == 0, (left, right)
        finally:
            browser.close()
