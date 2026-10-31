"""Jobs pages: artwork, compact rectangles, spacing and loading states.

- Cards and Scout tiles show the artwork in static/job-os/icons; Action
  centre shows an IT picture for IT jobs and a tick for new good matches.
- Page descriptions end without a full stop.
- No pill shapes (on/off switches aside): badges, chips and counts are
  compact rounded rectangles; Activity marks each calendar with a small
  coloured square instead of an icon.
- The four dashboard pictures show a loading shimmer until they (and the
  numbers) are in.
- Artwork URLs carry the build version (cached for good) and fade in over a
  shimmer; Action centre shows an arrow under its list while rows lie below.
- Scrollbars are 4px; dashboard capitals titles keep even letter gaps; a
  title's count is a rounded square; Automation titles are not clipped.
- Spacing: side buttons as tall as folder rows elsewhere, the gap between
  Action centre and Automations equal to the column gap, funnel bars as far
  from their widest label as from their widest number, Automation cards
  with the same inset on every side.
"""
import json
import time

import pytest

from tests._pytest_port import BASE

_DAY = {"day": "2026-10-30", "state": "ok", "ok": 1, "failed": 0}
DASHBOARD = {
    "total_jobs": 155, "active_work": 3, "needs_attention": 2, "by_status": {"scraped": 147, "submitted": 1},
    "actions": [
        {"job_id": "it-job", "title": "IT Help Desk Analyst (Level 1)", "company": "CVS", "status": "resume_ready", "reason": "Check numbers", "kind": "review"},
        {"job_id": "chef-job", "title": "Pastry Chef", "company": "Cafe", "status": "submitted", "reason": "Follow up?", "kind": "follow_up"},
    ],
    "funnel": [{"key": "found", "label": "Found", "count": 155}, {"key": "analysed", "label": "Analysed", "count": 113},
               {"key": "applied", "label": "Applied", "count": 1}, {"key": "offers", "label": "Offers", "count": 0}],
    "activity": {"today": "2026-10-31", "days": {"2026-10-08": {"found": 11}}},
    "calibration": None, "site_health": [],
}
AUTOMATIONS = {"automations": [
    {"key": k, "label": label, "on": on, "schedule": "Daily at 08:00", "last": None, "next": None,
     "off_reason": "Turn it on in Settings", "detail": "", "history": [_DAY] * 14}
    for k, label, on in [("scout", "Scout searches", False), ("analysis", "Luna fit analysis", True),
                         ("alerts", "Match alert emails", False), ("digest", "Daily digest", False), ("replies", "Reply commands", False)]]}


def _boot(pw, dashboard_delay=0.0, payload=None):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1500, "height": 1000})

    def dashboard(route):
        if dashboard_delay:
            time.sleep(dashboard_delay)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload or DASHBOARD))

    page.route("**/api/job-os/dashboard", dashboard)
    page.route("**/api/job-os/automations", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(AUTOMATIONS)))
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return browser, page


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _boot(pw)
        page.evaluate("async () => { await switchPanel('jobs'); }")
        page.wait_for_selector("#jobOsRoot .dash-side .automation-row", timeout=20000)
        page.wait_for_timeout(600)
        try:
            yield page
        finally:
            browser.close()


def test_cards_and_action_rows_show_their_artwork(page):
    out = page.evaluate("""() => ({
        cards: [...document.querySelectorAll('#jobOsRoot .card-icon.has-art img')].map(i => i.getAttribute('src').split('?')[0].split('/').pop()),
        rows: [...document.querySelectorAll('#jobOsRoot .action-row')].map(r => [r.querySelector('strong').textContent,
            (r.querySelector('.action-icon img') || {getAttribute: () => 'svg'}).getAttribute('src').split('?')[0].split('/').pop()]),
    })""")
    for art in ("application-funnel-26.webp", "action-centre-26.webp", "automations-26.webp", "recent-jobs-26.webp"):
        assert art in out["cards"], out
    # Every picture is drawn at the size its file was made for (no browser scaling).
    sizes = page.evaluate("""() => [...document.querySelectorAll('#jobOsRoot img.job-os-art')].map(i => {
        const r = i.getBoundingClientRect(); return [i.getAttribute('src').match(/-(\\d+)\\.webp(\\?|$)/)[1], r.width, r.height, i.naturalWidth]; })""")
    assert sizes and all(float(n) == w == h == nat for n, w, h, nat in sizes), sizes
    rows = dict(out["rows"])
    assert rows["IT Help Desk Analyst (Level 1)"].startswith("it-"), rows
    assert rows["Pastry Chef"] == "svg", rows


def test_page_descriptions_have_no_trailing_full_stop(page):
    seen = []
    for view in ("dashboard", "scout", "pipeline", "resume-studio", "settings"):
        page.click(f"#jobOsSidebar [data-job-os-view='{view}']")
        page.wait_for_function("(v) => document.querySelector(`#jobOsRoot .job-os-shell[data-view='${v}'] .job-os-header p`)", arg=view, timeout=10000)
        seen.append(page.evaluate("() => document.querySelector('#jobOsRoot .job-os-header p').textContent"))
    assert seen and all(text and not text.rstrip().endswith(".") for text in seen), seen


def test_no_pill_shapes_and_activity_uses_colour_squares(page):
    out = page.evaluate("""() => {
        const pills = [];
        for (const root of [document.getElementById('jobOsRoot'), document.getElementById('jobOsSidebar')])
          for (const el of root.querySelectorAll('*')) {
            if (el.closest('.job-os-toggle-track')) continue;
            const r = el.getBoundingClientRect(); if (r.width < 8 || r.height < 8) continue;
            const c = getComputedStyle(el), radius = parseFloat(c.borderTopLeftRadius);
            const drawn = (parseFloat(c.borderTopWidth) > 0 && c.borderTopColor !== 'rgba(0, 0, 0, 0)') || c.backgroundColor !== 'rgba(0, 0, 0, 0)';
            if (drawn && radius > 6 && radius >= Math.min(r.width, r.height) / 2 - 1 && Math.abs(r.width - r.height) > 2) pills.push(el.className);
          }
        const swatches = [...document.querySelectorAll('#jobOsRoot .cal-title .cal-swatch')].map(s => {
          const r = s.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height), getComputedStyle(s).backgroundColor]; });
        return {pills, swatches, icons: document.querySelectorAll('#jobOsRoot .cal-title svg').length};
    }""")
    assert out["pills"] == [], out
    assert len(out["swatches"]) == 3 and all(w == h == 10 and bg != "rgba(0, 0, 0, 0)" for w, h, bg in out["swatches"]), out
    assert out["icons"] == 0, out


def test_dashboard_spacing(page):
    out = page.evaluate("""() => {
        const box = s => document.querySelector(s).getBoundingClientRect();
        const funnel = box('.dash-main .funnel-card'), action = box('.action-centre'), autos = box('.automations-card');
        const text = el => { const r = document.createRange(); r.selectNodeContents(el); return r.getBoundingClientRect(); };
        const labels = [...document.querySelectorAll('.funnel-row > span')].map(text);
        const values = [...document.querySelectorAll('.funnel-row > strong')].map(text);
        const track = document.querySelector('.funnel-track').getBoundingClientRect();
        const insets = [...document.querySelectorAll('.dash-side .automation-row')].map(row => {
          const R = row.getBoundingClientRect(); const dot = row.querySelector('.automation-dot').getBoundingClientRect();
          const chip = row.querySelector('.automation-state').getBoundingClientRect();
          const ticks = [...row.querySelectorAll('.automation-ticks i')].map(i => i.getBoundingClientRect());
          return {top: Math.min(chip.top, dot.top) - R.top, bottom: R.bottom - Math.max(...ticks.map(t => t.bottom)),
                  left: Math.min(dot.left, ...ticks.map(t => t.left)) - R.left, right: R.right - Math.max(chip.right, ...ticks.map(t => t.right))};
        });
        return {columnGap: action.left - funnel.right, sideGap: autos.top - action.bottom,
          gapLeft: track.left - Math.max(...labels.map(r => r.right)), gapRight: Math.min(...values.map(r => r.left)) - track.right,
          nav: [...document.querySelectorAll('#jobOsSidebar .job-os-side-nav .side-menu-item')].map(e => e.getBoundingClientRect().height),
          insets, actionList: [document.querySelector('.action-list').scrollHeight, document.querySelector('.action-list').clientHeight]};
    }""")
    assert abs(out["sideGap"] - out["columnGap"]) < 0.5, out
    assert abs(out["gapLeft"] - out["gapRight"]) < 1, out
    assert out["nav"] and all(abs(h - 34) < 0.5 for h in out["nav"]), out
    stage = page.evaluate("() => [...document.querySelectorAll('#jobOsSidebar .job-os-stage .side-menu-label')].map(l => getComputedStyle(l).top)")
    assert stage and all(top == "1px" for top in stage), stage
    assert out["actionList"][0] <= out["actionList"][1], out
    for inset in out["insets"]:
        values = [inset["bottom"], inset["left"], inset["right"]]
        assert max(values) - min(values) < 1.5, out["insets"]
        # The dot and On chip were lifted on request, so the top inset sits up to 3px tighter.
        assert 0 <= min(values) - inset["top"] <= 3, out["insets"]


def test_metric_pictures_and_numbers_show_a_loading_shimmer_first():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _boot(pw, dashboard_delay=1.5)
        try:
            page.evaluate("() => { switchPanel('jobs'); }")
            page.wait_for_selector("#jobOsRoot .job-os-metric", timeout=20000)
            loading = page.evaluate("() => [...document.querySelectorAll('#jobOsRoot .job-os-metric')].map(m => m.classList.contains('is-loading') && m.querySelector('strong').textContent === '')")
            assert loading and all(loading), loading
            page.wait_for_function("() => document.querySelector('#jobOsRoot .job-os-metric strong').textContent === '155'", timeout=15000)
            page.wait_for_function("() => [...document.querySelectorAll('#jobOsRoot .job-os-metric-art')].every(a => a.classList.contains('is-ready'))", timeout=10000)
            sizes = page.evaluate("() => [...document.querySelectorAll('#jobOsRoot .job-os-metric-icon')].map(i => [i.naturalWidth > 0, Math.round(i.getBoundingClientRect().width)])")
            assert all(ok and w == 40 for ok, w in sizes), sizes
        finally:
            browser.close()


def test_a_modal_opens_and_closes_with_an_animation(page):
    page.click("#jobOsSidebar [data-job-os-view='pipeline']")
    page.click("#jobOsRoot [data-job-os-action='job-form-new'] >> nth=0")
    page.wait_for_selector("#jobOsRoot .job-form-modal", timeout=10000)
    opening = page.evaluate("() => getComputedStyle(document.querySelector('#jobOsRoot .job-form-modal')).animationName")
    assert opening == "job-modal-in", opening
    closing = page.evaluate("""() => {
        document.querySelector('#jobOsRoot .job-form-modal [data-job-os-action="job-form-close"]').click();
        return [...document.querySelectorAll('#jobOsRoot .is-closing')].map(n => [n.className, getComputedStyle(n).animationName]);
    }""")
    kinds = dict(closing)
    assert any("job-form-modal" in k and v == "job-modal-out" for k, v in kinds.items()), closing
    assert any("job-modal-backdrop" in k and v == "job-overlay-fade-out" for k, v in kinds.items()), closing
    page.wait_for_function("() => !document.querySelector('#jobOsRoot .is-closing')", timeout=2000)
    assert page.evaluate("() => !document.querySelector('#jobOsRoot .job-form-modal')")


def test_scrolling_lists_reach_the_card_edge_without_moving_their_rows(page):
    out = page.evaluate("""() => {
        const card = document.querySelector('#jobOsRoot .action-centre'), list = card.querySelector('.action-list');
        const c = card.getBoundingClientRect(), l = list.getBoundingClientRect(), row = list.querySelector('.action-row').getBoundingClientRect();
        const pad = parseFloat(getComputedStyle(card).paddingRight), border = parseFloat(getComputedStyle(card).borderRightWidth);
        return {listGap: c.right - border - l.right, rowGap: c.right - border - pad - row.right};
    }""")
    assert abs(out["listGap"]) < 0.5 and abs(out["rowGap"]) < 0.5, out


def test_artwork_is_versioned_and_fades_in_over_a_shimmer(page):
    out = page.evaluate("""() => [...document.querySelectorAll('#jobOsRoot .job-os-art, #jobOsRoot .job-os-metric-icon')].map(i => ({
        v: new URL(i.currentSrc || i.src).searchParams.get('v'), ready: i.classList.contains('is-ready') || i.closest('.is-ready') !== null,
        opacity: getComputedStyle(i).opacity}))""")
    assert out and all(o["v"] for o in out), out
    assert all(o["ready"] and o["opacity"] == "1" for o in out), out
    shimmer = page.evaluate("""() => {
        const img = document.querySelector('#jobOsRoot .card-icon.has-art .job-os-art');
        img.classList.remove('is-ready');
        const wrap = getComputedStyle(img.parentElement), pic = getComputedStyle(img);
        return {animation: wrap.animationName, opacity: pic.opacity};
    }""")
    assert shimmer["animation"] == "job-os-shimmer", shimmer


def test_scrollbars_are_four_pixels_wide(page):
    widths = page.evaluate("""() => {
        const box = document.createElement('div');
        // Headless Chromium hides scrollbars, but a stable gutter still takes their width.
        box.style.cssText = 'position:fixed;top:0;left:0;width:120px;height:60px;overflow:auto;scrollbar-gutter:stable';
        box.innerHTML = '<div style="height:400px"></div>';
        document.body.appendChild(box);
        const w = [box.offsetWidth - box.clientWidth, box.offsetWidth - box.clientWidth];
        box.remove();
        return w;
    }""")
    assert widths == [4, 4], widths


def test_titles_counts_and_automation_names_are_drawn_whole(page):
    out = page.evaluate("""() => {
        const title = document.querySelector('#jobOsRoot .action-centre .card-title');
        const cs = getComputedStyle(title), advance = parseFloat(cs.fontSize) * 0.6 + parseFloat(cs.letterSpacing);
        const count = document.querySelector('#jobOsRoot .action-centre .job-os-count').getBoundingClientRect();
        const names = [...document.querySelectorAll('#jobOsRoot .automation-title')].map(t => {
            const r = t.getBoundingClientRect(); return {h: r.height, size: parseFloat(getComputedStyle(t).fontSize)};
        });
        return {advance, capI: title.querySelectorAll('.cap-i').length, count: [count.width, count.height], names};
    }""")
    assert abs(out["advance"] - round(out["advance"])) < 0.01, out
    assert out["capI"] == 1 and out["count"][0] == out["count"][1], out
    assert all(n["h"] >= n["size"] for n in out["names"]), out


def test_activity_cards_have_as_much_room_above_the_title_as_beside_it(page):
    out = page.evaluate("""() => {
        const cal = document.querySelector('#jobOsRoot .cal'), sw = cal.querySelector('.cal-swatch');
        const c = cal.getBoundingClientRect(), s = sw.getBoundingClientRect();
        return {left: s.left - c.left, top: s.top - c.top};
    }""")
    # Layout boxes; the pixel ink of the swatch measured 12px on both sides.
    assert abs(out["left"] - out["top"]) < 1.5, out


def test_action_centre_shows_an_arrow_while_rows_lie_below():
    sync_api = pytest.importorskip("playwright.sync_api")
    many = dict(DASHBOARD, actions=[dict(DASHBOARD["actions"][1], job_id=f"job-{n}", title=f"Analyst {n}") for n in range(6)])
    with sync_api.sync_playwright() as pw:
        browser, page = _boot(pw, payload=many)
        try:
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector("#jobOsRoot .action-centre.has-more", timeout=20000)
            page.wait_for_timeout(400)
            out = page.evaluate("""() => {
                const card = document.querySelector('#jobOsRoot .action-centre'), list = card.querySelector('.action-list');
                const arrow = card.querySelector('.action-more').getBoundingClientRect(), c = card.getBoundingClientRect();
                const border = parseFloat(getComputedStyle(card).borderBottomWidth);
                return {below: card.classList.contains('more-below'), opacity: getComputedStyle(card.querySelector('.action-more')).opacity,
                        above: arrow.top - list.getBoundingClientRect().bottom, under: c.bottom - border - arrow.bottom};
            }""")

            assert out["below"] and out["opacity"] == "1", out
            assert abs(out["above"] - out["under"]) < 1.01, out
            for _ in range(6):  # each click scrolls about a list's height
                page.click("#jobOsRoot .action-more")
                page.wait_for_timeout(500)
                if not page.evaluate("() => document.querySelector('#jobOsRoot .action-centre').classList.contains('more-below')"):
                    break
            assert page.evaluate("() => { const l = document.querySelector('#jobOsRoot .action-list'); return l.scrollTop > 0 && l.scrollHeight - l.clientHeight - l.scrollTop <= 2; }")
            page.wait_for_timeout(300)
            assert page.evaluate("() => getComputedStyle(document.querySelector('#jobOsRoot .action-more')).opacity") == "0.3"
        finally:
            browser.close()


def _post(path, body):
    import urllib.request

    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def test_action_centre_and_automations_are_the_same_height_with_no_blank_strip(page):
    out = page.evaluate("""() => {
        const ac = document.querySelector('#jobOsRoot .action-centre'), au = document.querySelector('#jobOsRoot .automations-card');
        const pad = (card, last) => card.getBoundingClientRect().bottom - parseFloat(getComputedStyle(card).borderBottomWidth) - last.getBoundingClientRect().bottom;
        const rows = ac.querySelectorAll('.action-row'), autos = au.querySelectorAll('.automation-row');
        return {ac: ac.getBoundingClientRect().height, au: au.getBoundingClientRect().height,
                acPad: parseFloat(getComputedStyle(ac).paddingBottom), acGap: pad(ac, rows[rows.length - 1]),
                auPad: parseFloat(getComputedStyle(au).paddingBottom), auGap: pad(au, autos[autos.length - 1])};
    }""")
    assert abs(out["ac"] - out["au"]) < 1, out
    assert abs(out["acGap"] - out["acPad"]) < 1 and abs(out["auGap"] - out["auPad"]) < 1, out


def test_automation_cards_have_no_edit_button_and_keep_their_state_on_hover(page):
    page.hover("#jobOsRoot .dash-side .automation-row")
    page.wait_for_timeout(300)
    out = page.evaluate("""() => {
        const row = document.querySelector('#jobOsRoot .dash-side .automation-row');
        const dot = row.querySelector('.automation-dot'), main = row.querySelector('.automation-main');
        return {edit: getComputedStyle(row.querySelector('.automation-edit')).display, state: getComputedStyle(row.querySelector('.automation-state')).opacity,
                dotTop: getComputedStyle(dot).top, mainTop: getComputedStyle(main).top,
                titleTop: getComputedStyle(row.querySelector('.automation-title')).top, endTop: getComputedStyle(row.querySelector('.automation-end')).top};
    }""")
    assert out == {"edit": "none", "state": "1", "dotTop": "-3px", "mainTop": "-4px", "titleTop": "-2px", "endTop": "-2px"}, out


def test_capitals_titles_letters_are_not_flex_items(page):
    parents = page.evaluate("""() => [...document.querySelectorAll('#jobOsRoot .cap-i')].map(i => getComputedStyle(i.parentElement).display)""")
    assert parents and not [d for d in parents if "flex" in d or "grid" in d], parents
    assert page.evaluate("() => document.querySelector('#jobOsRoot .cal[data-cal=applied] .cal-title').textContent.trim()") == "Applications"


def test_job_cards_are_one_height_with_n_a_for_a_missing_employment_type():
    import uuid

    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    _post("/api/job-os/jobs", {"title": f"Typed {tag}", "company": "Acme", "employment_type": "Full-time",
                               "canonical_url": f"https://jobs.example.test/typed-{tag}"})
    _post("/api/job-os/jobs", {"title": f"Typeless {tag}", "company": "Acme", "canonical_url": f"https://jobs.example.test/bare-{tag}"})
    with sync_api.sync_playwright() as pw:
        browser, page = _boot(pw)
        try:
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(f"#jobOsRoot .job-os-recent .job-os-job-card:has-text('Typeless {tag}')", timeout=20000)
            out = page.evaluate("""(tag) => {
                const cards = [...document.querySelectorAll('#jobOsRoot .job-os-recent .job-os-job-card')];
                const pick = (t) => cards.find(c => c.textContent.includes(t));
                const bare = pick('Typeless ' + tag), typed = pick('Typed ' + tag);
                return {chips: [...bare.querySelectorAll('.job-os-chip')].map(c => c.textContent),
                        heights: [bare.getBoundingClientRect().height, typed.getBoundingClientRect().height],
                        all: [...new Set(cards.map(c => Math.round(c.getBoundingClientRect().height)))]};
            }""", tag)
            assert out["chips"] == ["N/A"], out
            assert abs(out["heights"][0] - out["heights"][1]) < 0.5 and len(out["all"]) == 1, out
        finally:
            browser.close()


def test_the_dashboard_scrolls_past_recent_jobs_by_its_right_hand_room(page):
    out = page.evaluate("""() => {
        const sc = document.getElementById('mainJobs'), card = document.querySelector('#jobOsRoot .job-os-recent');
        sc.scrollTop = sc.scrollHeight;
        const s = sc.getBoundingClientRect(), c = card.getBoundingClientRect();
        return {right: s.right - (sc.offsetWidth - sc.clientWidth) - c.right, bottom: s.bottom - c.bottom};
    }""")
    assert out["right"] > 0 and abs(out["bottom"] - out["right"]) < 1, out


def test_recent_job_status_badges_are_capitals(page):
    out = page.evaluate("""() => [...document.querySelectorAll('#jobOsRoot .job-os-recent .job-os-badge')].map(b => ({
        caps: getComputedStyle(b).textTransform, text: b.innerText.trim(), capI: b.querySelectorAll('.cap-i').length}))""")
    assert out and all(b["caps"] == "uppercase" and b["text"] == b["text"].upper() for b in out), out
    assert any(b["capI"] for b in out) or not any("I" in b["text"] for b in out), out


def test_resume_ready_sits_1px_higher_than_other_recent_badges(page):
    out = page.evaluate("""() => {
        const card = document.querySelector('#jobOsRoot .job-os-recent .job-os-job-card'), shown = card.querySelector('.job-os-badge');
        const probe = document.createElement('span');
        probe.className = 'job-os-badge'; probe.dataset.tone = 'accent'; probe.dataset.status = 'resume_ready'; probe.textContent = 'Resume ready';
        card.appendChild(probe);
        const pad = (e) => [getComputedStyle(e).paddingTop, getComputedStyle(e).paddingBottom];
        const r = {shown: pad(shown), status: shown.dataset.status, ready: pad(probe)};
        probe.remove();
        return r;
    }""")
    assert out["status"] and out["shown"] == ["2px", "1px"] and out["ready"] == ["1px", "2px"], out


def test_scrollbar_thumbs_are_grey_on_every_page(page):
    out = page.evaluate("""() => ['', 'dash-card-body is-scrolling', 'cron-run-list is-capped', 'pipe-col-cards is-scrolling'].map(cls => {
        const box = document.createElement('div');
        box.className = cls;
        document.getElementById('jobOsRoot').appendChild(box);
        const colour = getComputedStyle(box, '::-webkit-scrollbar-thumb').backgroundColor;
        box.remove();
        return colour;
    }).concat([getComputedStyle(document.querySelector('#jobOsRoot .action-centre .action-list'), '::-webkit-scrollbar-thumb').backgroundColor])""")
    assert len(set(out)) == 1, out
    rgb = [int(v) for v in out[0][out[0].index("(") + 1:].split(",")[:3]]
    assert len(set(rgb)) == 1, out  # grey, not tinted by the theme's accent
