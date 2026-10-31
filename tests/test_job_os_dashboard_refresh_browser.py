"""Jobs pages: artwork, compact rectangles, spacing and loading states.

- Cards and Scout tiles show the artwork in static/job-os/icons; Action
  centre shows an IT picture for IT jobs and a tick for new good matches.
- Page descriptions end without a full stop.
- No pill shapes (on/off switches aside): badges, chips and counts are
  compact rounded rectangles; Activity marks each calendar with a small
  coloured square instead of an icon.
- The four dashboard pictures show a loading shimmer until they (and the
  numbers) are in.
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


def _boot(pw, dashboard_delay=0.0):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1500, "height": 1000})

    def dashboard(route):
        if dashboard_delay:
            time.sleep(dashboard_delay)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(DASHBOARD))

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
        cards: [...document.querySelectorAll('#jobOsRoot .card-icon.has-art img')].map(i => i.getAttribute('src').split('/').pop()),
        rows: [...document.querySelectorAll('#jobOsRoot .action-row')].map(r => [r.querySelector('strong').textContent,
            (r.querySelector('.action-icon img') || {getAttribute: () => 'svg'}).getAttribute('src').split('/').pop()]),
    })""")
    for art in ("application-funnel-32.webp", "action-centre-32.webp", "automations-32.webp", "recent-jobs-32.webp"):
        assert art in out["cards"], out
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
        values = [inset["top"], inset["bottom"], inset["left"], inset["right"]]
        assert max(values) - min(values) < 1.5, out["insets"]


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
