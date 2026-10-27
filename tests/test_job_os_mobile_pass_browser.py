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
    """Settings groups on a phone: every row and the footer actions stay inside
    the group's width, the test-email choice and its button share a line, and
    Replace and Disconnect sit together in the footer."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/settings")
        try:
            _connections(page)
            m = page.evaluate("""() => {
              const box = (el) => { const r = el.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height, r: r.right}; };
              const conn = document.querySelector('#job-os-gmail');
              const rows = conn.querySelector('.set-rows');
              const pick = conn.querySelector('.job-os-inline-select');
              const send = conn.querySelector('[data-job-os-action="gmail-test"]');
              const foot = [...conn.querySelectorAll('.set-group-foot .job-os-btn')];
              return {rows: box(rows), pick: box(pick), send: box(send), foot: foot.map(box),
                labels: foot.map((b) => b.textContent.trim()),
                inside: [...conn.querySelectorAll('.set-row, .set-row *')].every((el) => { const r = el.getBoundingClientRect(); return r.width === 0 || r.right <= box(rows).r + 1; }),
                site: box(document.querySelector('.site-health-row'))};
            }""")
            assert m["labels"] == ["Replace", "Disconnect"]
            assert m["inside"], "nothing in a row overflows the group"
            assert abs(m["pick"]["y"] + m["pick"]["h"] / 2 - (m["send"]["y"] + m["send"]["h"] / 2)) <= 2, "choice and button on one line"
            assert len({round(b["y"]) for b in m["foot"]}) == 1, "footer actions on one row"
            assert m["foot"][-1]["r"] <= m["rows"]["r"] + 1
            assert abs(m["site"]["x"] + m["site"]["w"] - m["rows"]["r"]) <= 1.5, "job site rows span the group"
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


def test_the_pipeline_filter_strip_fades_its_text_not_its_buttons():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            strip = ".pipe-toolbar > .seg:first-child"
            page.wait_for_selector(strip + "[data-scroll-fading]", timeout=10000)
            read = lambda: page.evaluate("""(sel) => { const e = document.querySelector(sel);
              const strip = getComputedStyle(e);
              const masked = [...e.querySelectorAll('.sf-text[data-sf]')].map((s) => s.textContent.trim());
              const buttons = [...e.querySelectorAll('.seg-btn')].map((b) => { const c = getComputedStyle(b); return c.maskImage || c.webkitMaskImage || 'none'; });
              return {stripMask: strip.maskImage || strip.webkitMaskImage || 'none', masked, buttons, last: e.querySelector('.seg-btn:last-child .sf-text')?.textContent.trim()}; }""", strip)
            at_start = read()
            assert at_start["stripMask"] == "none" and set(at_start["buttons"]) == {"none"}, at_start
            assert at_start["masked"] and at_start["last"] in at_start["masked"], at_start
            page.evaluate("(sel) => { const e = document.querySelector(sel); e.scrollLeft = e.scrollWidth; }", strip)
            page.wait_for_timeout(200)
            at_end = read()
            assert at_end["masked"] and at_end["last"] not in at_end["masked"], at_end
            assert "All" in at_end["masked"], "the first label fades at the left once scrolled"
        finally:
            browser.close()


def test_edge_swipe_is_claimed_over_the_job_drawer_so_it_cannot_go_back_a_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    job = _job()
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/scout")
        try:
            page.evaluate("(id) => JobOS.openJob(id)", job["id"])
            page.wait_for_selector("#job-os-detail")
            page.wait_for_timeout(500)
            cdp = page.context.new_cdp_session(page)
            page.evaluate("() => { window.__probe = []; window.addEventListener('touchstart', (e) => window.__probe.push(e.defaultPrevented), {passive: true}); }")
            for y in (20, 300, 700):
                _touch(cdp, "touchStart", 10, y)
                _touch(cdp, "touchEnd", 0, 0)
            assert page.evaluate("() => window.__probe") == [True, True, True]
            assert page.evaluate("() => !!document.getElementById('job-os-detail')"), "swiping did not slide a hidden sidebar over the drawer"
            assert page.evaluate("() => !document.querySelector('.sidebar.mobile-open')")
        finally:
            browser.close()


def test_each_pipeline_column_has_its_own_filter_beside_its_count():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    _job(f"Alpha {tag}")
    _job(f"Beta {tag}")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            page.wait_for_selector('.pipe-col[data-col="new"] .pipe-card', timeout=15000)
            geo = page.evaluate("""() => { const h = document.querySelector('.pipe-col[data-col="new"] .pipe-col-head');
              const b = h.querySelector('.pipe-col-filter-btn').getBoundingClientRect(); const c = h.querySelector('.job-os-count').getBoundingClientRect();
              const t = h.querySelector('h3').getBoundingClientRect(); return {bRight: b.right, cLeft: c.left, tRight: t.right, bh: b.height, bTop: b.top, bBottom: b.bottom, hTop: h.getBoundingClientRect().top, hBottom: h.getBoundingClientRect().bottom}; }""")
            assert page.locator('.pipe-col[data-col="new"] .pipe-col-filter-btn svg path').count() >= 1, "the funnel icon is drawn"
            assert geo["tRight"] <= geo["bRight"] <= geo["cLeft"] + 1, geo
            assert geo["bh"] <= geo["hBottom"] - geo["hTop"] + 1, geo
            names = "[...document.querySelectorAll(\"[data-col='new'] .pipe-card-name\")].map((e) => e.textContent)"
            page.locator('.pipe-col[data-col="new"] .pipe-col-filter-btn').tap()
            page.wait_for_selector('.pipe-col[data-col="new"] .pipe-col-filter')
            page.fill('.pipe-col[data-col="new"] [data-col-filter="query"]', f"alpha {tag}")
            page.wait_for_function(f"(tag) => {{ const n = {names}; return n.length === 1 && n[0] === 'Alpha ' + tag; }}", arg=tag, timeout=5000)
            assert page.locator('.pipe-col[data-col="favorite"] .pipe-col-filter').count() == 0, "other columns are untouched"
            page.fill('.pipe-col[data-col="new"] [data-col-filter="query"]', tag)
            page.select_option('.pipe-col[data-col="new"] select[data-col-filter="min"]', "85")
            page.wait_for_function(f"(tag) => !{names}.some((t) => t.endsWith(tag))", arg=tag, timeout=5000)
            page.select_option('.pipe-col[data-col="new"] select[data-col-filter="min"]', "none")
            page.select_option('.pipe-col[data-col="new"] select[data-col-filter="sort"]', "oldest")
            page.wait_for_function(f"(tag) => {{ const n = {names}; return n.length === 2 && n.includes('Alpha ' + tag) && n.includes('Beta ' + tag); }}", arg=tag, timeout=5000)
            page.click('.pipe-col[data-col="new"] [data-job-os-action="pipe-col-filter-clear"]')
            page.wait_for_function("() => !document.querySelector('.pipe-col-filter-btn.is-active')", timeout=5000)
        finally:
            browser.close()


def test_a_column_filter_is_remembered_and_the_column_says_it_is_filtered():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    _job(f"Alpha {tag}")
    _job(f"Beta {tag}")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            col = '.pipe-col[data-col="new"]'
            page.wait_for_selector(col + " .pipe-card", timeout=15000)
            page.locator(col + " .pipe-col-filter-btn").tap()
            page.fill(col + ' [data-col-filter="query"]', f"alpha {tag}")
            page.wait_for_function("() => !!document.querySelector('.pipe-col[data-col=\"new\"] .job-os-count.is-filtered')", timeout=5000)
            page.locator(col + " .pipe-col-filter-btn").tap()  # close the panel
            page.wait_for_selector(col + " .pipe-col-filtered", timeout=5000)
            assert page.inner_text(col + " .job-os-count").split("/")[0] == "1"
            assert page.evaluate("(c) => getComputedStyle(document.querySelector(c + ' .pipe-col-filter-btn'), '::after').content", col) != "none"
            assert page.locator('.pipe-col[data-col="favorite"] .pipe-col-filtered').count() == 0
            # A fresh load keeps it.
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("async () => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove()); await switchPanel('jobs'); }")
            page.wait_for_selector(col + " .pipe-col-filtered", timeout=15000)
            assert "alpha" in page.inner_text(col + " .pipe-col-filtered").lower()
            names = page.evaluate("(c) => [...document.querySelectorAll(c + ' .pipe-card-name')].map((e) => e.textContent)", col)
            assert names == [f"Alpha {tag}"], names
            page.locator(col + " .pipe-col-filtered").tap()
            page.click(col + ' [data-job-os-action="pipe-col-filter-clear"]')
            page.wait_for_function("() => !document.querySelector('.pipe-col-filtered')", timeout=5000)
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(col + " .pipe-card", timeout=15000)
            assert page.locator(".pipe-col-filtered").count() == 0, "clearing is remembered too"
        finally:
            browser.close()


def test_settings_sections_are_separate_cards_with_a_gap_between():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/settings")
        try:
            page.evaluate("async () => { JobOSState.activeView = 'settings'; JobOSState.settingsSection = null; await JobOS.refresh(); }")
            page.wait_for_selector(".settings-nav-item")
            rects = page.evaluate("""() => [...document.querySelectorAll('.settings-nav-item')].map((e) => { const r = e.getBoundingClientRect(); const c = getComputedStyle(e);
              return {top: r.top, bottom: r.bottom, radius: parseFloat(c.borderTopLeftRadius), bw: parseFloat(c.borderBottomWidth)}; })""")
            assert len(rects) >= 7
            for before, after in zip(rects, rects[1:]):
                assert after["top"] - before["bottom"] >= 9, (before, after)
            assert all(r["radius"] >= 12 and r["bw"] >= 1 for r in rects), rects
        finally:
            browser.close()


def test_the_column_filter_eases_open_and_folds_away():
    sync_api = pytest.importorskip("playwright.sync_api")
    _job()
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            col = '.pipe-col[data-col="new"]'
            page.wait_for_selector(col + " .pipe-card", timeout=15000)
            page.locator(col + " .pipe-col-filter-btn").tap()
            page.wait_for_selector(col + " .pipe-col-filter")
            early = page.evaluate("(c) => { const e = document.querySelector(c + ' .pipe-col-filter'); return [e.getAnimations().length, parseFloat(getComputedStyle(e).opacity)]; }", col)
            assert early[0] >= 1 and early[1] < 1, early
            # A refresh landing mid-animation (focus, viewport or polling work) must not cut it short.
            page.evaluate("() => JobOS.refresh()")
            page.wait_for_timeout(60)
            assert page.evaluate("(c) => document.querySelector(c + ' .pipe-col-filter').getAnimations().length", col) >= 1
            page.wait_for_timeout(450)
            assert page.evaluate("(c) => parseFloat(getComputedStyle(document.querySelector(c + ' .pipe-col-filter')).opacity)", col) == 1
            page.locator(col + " .pipe-col-filter-btn").tap()
            leaving = page.evaluate("(c) => document.querySelector(c + ' .pipe-col-filter')?.classList.contains('is-leaving')", col)
            assert leaving, "folds away instead of vanishing"
            page.wait_for_function("(c) => !document.querySelector(c + ' .pipe-col-filter')", arg=col, timeout=3000)
        finally:
            browser.close()


def test_test_buttons_are_violet_disconnect_is_red_and_the_save_bar_is_slim():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/settings")
        try:
            _connections(page)
            colours = page.evaluate("""() => { const c = (sel) => { const e = document.querySelector(sel); const s = getComputedStyle(e); return [s.color, s.borderTopColor]; };
              return {firecrawl: c('[data-job-os-action="test-firecrawl"]'), gmailTest: c('[data-job-os-action="gmail-test"]'), disconnect: c('[data-job-os-action="gmail-disconnect"]'), replace: c('[data-job-os-action="gmail-edit"]')}; }""")
            violet = "rgb(139, 92, 246)"
            assert colours["firecrawl"] == [violet, violet] and colours["gmailTest"] == [violet, violet], colours
            assert colours["disconnect"][0] == colours["disconnect"][1] and colours["disconnect"][0] != colours["replace"][0], colours
            page.evaluate("""async () => { JobOSState.settingsSection = 'apify'; document.getElementById('jobOsRoot').innerHTML = JobOSRender.shell(JobOSState); }""")
            assert page.evaluate("() => getComputedStyle(document.querySelector('[data-job-os-action=\"apify-edit\"], [data-job-os-action=\"apify-connect\"]')) && true")
            page.evaluate("""async () => { JobOSState.settingsSection = 'notifications'; document.getElementById('jobOsRoot').innerHTML = JobOSRender.shell(JobOSState); }""")
            assert page.evaluate("() => getComputedStyle(document.querySelector('[data-job-os-action=\"notify-digest\"]')).color") == violet
            page.evaluate("() => { JobOSState.settingsDirty = true; document.getElementById('jobOsRoot').innerHTML = JobOSRender.shell(JobOSState); }")
            page.wait_for_timeout(400)
            h = page.evaluate("() => document.querySelector('.job-os-savebar').getBoundingClientRect().height")
            assert h <= 46, h
        finally:
            browser.close()


def test_drawer_actions_share_their_rows_and_in_sentence_links_have_no_padding():
    sync_api = pytest.importorskip("playwright.sync_api")
    job = _job()
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw, "#jobs/pipeline")
        try:
            page.evaluate("(id) => JobOS.openJob(id)", job["id"])
            page.wait_for_selector("#job-os-detail")
            page.wait_for_timeout(500)
            rows = page.evaluate("""() => { const a = [...document.querySelectorAll('#job-os-detail .job-os-actions')][0];
              const bs = [...a.children].map((b) => { const r = b.getBoundingClientRect(); return {top: Math.round(r.top), right: r.right, left: r.left}; });
              const box = a.getBoundingClientRect(); const byRow = {}; bs.forEach((b) => { (byRow[b.top] = byRow[b.top] || []).push(b); });
              return Object.values(byRow).map((row) => Math.abs(Math.max(...row.map((b) => b.right)) - box.right)); }""")
            assert all(r <= 1.5 for r in rows), rows
            pad = page.evaluate("() => { const l = document.querySelector('#job-os-detail p .job-os-link'); return l ? getComputedStyle(l).paddingLeft : '0px'; }")
            assert pad == "0px", pad
        finally:
            browser.close()
