"""Scout page layout: artwork, the four tiles, capitals titles, good matches
beside the saved searches (ten matches, then the list scrolls), the schedule's
clocks and the saved-search buttons."""
import json

import pytest

from tests._pytest_port import BASE

SEARCH = {"keywords": "SOC Analyst, IT Analyst", "locations": [], "sites": ["indeed", "linkedin", "bayt"], "title_filter": [],
          "related_titles": ["Security Analyst"], "strict_titles": True, "queries": ["SOC Analyst"], "posted_within_days": 1,
          "remote_only": False, "enabled": True, "revision": 0, "last_run_at": None, "last_new": 0, "next_run_at": None, "off_target": 0}
SEARCHES = {
    "searches": [dict(SEARCH, id="s-my", name="Analyst roles — Malaysia", country="my", country_name="Malaysia"),
                 dict(SEARCH, id="s-qa", name="Analyst roles — Qatar", country="qa", country_name="Qatar")],
    "search_provider": "firecrawl", "apify": {"active": False, "indeed_fallback": False}, "countries": [],
    "posted_within_days": [0, 1, 3, 7, 14], "sites": [],
    "schedule": {"enabled": False, "hours": 6, "summary": "At 12:30 and 18:30 GMT+8 / GMT+3, Saturday once"},
}
MATCHES = {"matches": {"waiting": 0, "release_count": 5, "min_fit_score": 65, "release_cutoff_hour": 20, "released": [
    {"id": f"m-{n}", "title": f"Analyst {n}", "company": "Acme", "location": "Kuala Lumpur", "country": "Malaysia", "source": "linkedin",
     "salary_text": "", "workplace": "", "status": "submitted" if n == 2 else "analyzed", "fit_score": 90 - n, "released_at": 1793102422}
    for n in range(14)]}}


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1899, "height": 990})
        page.route("**/api/job-os/searches", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(SEARCHES)))
        page.route("**/api/job-os/matches", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(MATCHES)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
        page.evaluate("async () => { await switchPanel('jobs'); }")
        page.wait_for_selector("#jobOsRoot .dash-main", timeout=30000)
        page.evaluate("() => document.querySelector('[data-job-os-view=scout]').click()")
        page.wait_for_selector("#jobOsRoot .match-inbox.has-more", timeout=30000)
        page.wait_for_timeout(500)
        try:
            yield page
        finally:
            browser.close()


def test_cards_show_their_new_artwork_at_the_size_they_are_drawn(page):
    out = page.evaluate("""() => {
        const pic = (sel) => [...document.querySelectorAll('#jobOsRoot ' + sel)].map(i => {
            const r = i.getBoundingClientRect(); return [i.getAttribute('src').split('?')[0].split('/').pop(), r.width, r.height]; });
        return {heads: pic('.match-inbox .job-os-card-head .job-os-art, .scout-saved .section-bar .job-os-art'),
                tiles: pic('.scout-tile .job-os-art'), searches: pic('.scout-search-head .job-os-art')};
    }""")
    assert out["heads"] == [["new-good-matches-26.webp", 26, 26], ["saved-searches-26.webp", 26, 26]], out
    assert [t[0] for t in out["tiles"]] == ["apify-40.webp", "schedule-40.webp", "next-run-40.webp", "searches-40.webp"], out
    assert all(t[1:] == [40, 40] for t in out["tiles"]), out
    assert out["searches"] == [["saved-searches-36.webp", 36, 36]] * 2, out


def test_tiles_centre_their_artwork_beside_three_evenly_spaced_lines(page):
    out = page.evaluate("""() => [...document.querySelectorAll('#jobOsRoot .scout-tile')].map(t => {
        const c = (e) => { const r = e.getBoundingClientRect(); return (r.top + r.bottom) / 2; };
        const lines = [...t.querySelectorAll('.scout-tile-body > *')].map(e => e.getBoundingClientRect());
        const tile = t.getBoundingClientRect();
        return {icon: c(t.querySelector('.card-icon')), body: c(t.querySelector('.scout-tile-body')),
                label: parseFloat(getComputedStyle(t.querySelector('small')).fontSize), height: tile.height, lines: lines.length};
    })""")
    assert len(out) == 4 and all(abs(t["icon"] - t["body"]) < 1.5 and t["lines"] == 3 for t in out), out
    assert all(t["label"] >= 13 and t["height"] <= 80 for t in out), out


def test_the_schedule_tile_names_the_clocks(page):
    text = page.evaluate("() => document.querySelectorAll('#jobOsRoot .scout-tile')[1].querySelector('.scout-tile-body > span').textContent")
    assert text == "At 12:30 and 18:30 GMT+8 / GMT+3", text


def test_matches_sit_beside_one_search_a_row_and_show_ten_then_scroll(page):
    out = page.evaluate("""() => {
        const inbox = document.querySelector('#jobOsRoot .match-inbox'), saved = document.querySelector('#jobOsRoot .scout-saved');
        const a = inbox.getBoundingClientRect(), b = saved.getBoundingClientRect();
        const cards = [...saved.querySelectorAll('.scout-search')].map(c => c.getBoundingClientRect().left);
        const list = inbox.querySelector('.match-list'), rows = [...list.children];
        const fully = rows.filter(r => r.getBoundingClientRect().bottom <= list.getBoundingClientRect().bottom + 0.5 && r.getBoundingClientRect().top >= list.getBoundingClientRect().top - 0.5).length;
        return {ratio: a.width / b.width, sameRow: Math.abs(a.top - b.top) < 60, oneColumn: new Set(cards.map(Math.round)).size === 1,
                fully, total: rows.length, scrolls: list.scrollHeight > list.clientHeight, arrow: inbox.classList.contains('more-below'),
                border: getComputedStyle(inbox).borderTopColor, plain: getComputedStyle(document.querySelector('#jobOsRoot .scout-tile')).borderTopColor,
                card: getComputedStyle(document.querySelector('#jobOsRoot .scout-search')).borderTopColor};
    }""")
    assert 2.5 < out["ratio"] < 3.6 and out["sameRow"] and out["oneColumn"], out
    assert out["fully"] == 10 and out["total"] == 14 and out["scrolls"] and out["arrow"], out
    assert out["border"] == out["card"], out


def test_titles_are_capitals_and_the_buttons_read_well(page):
    out = page.evaluate("""() => {
        const t = (sel) => getComputedStyle(document.querySelector('#jobOsRoot ' + sel)).textTransform;
        const run = document.querySelector('#jobOsRoot .scout-search-actions .job-os-btn.primary'), add = document.querySelector('#jobOsRoot .section-bar .job-os-btn.primary');
        const css = (e) => getComputedStyle(e);
        return {caps: [t('.match-inbox .card-title'), t('.scout-saved .section-bar .card-title')], run: run.textContent.trim(),
                pad: [css(run).paddingTop, css(run).paddingBottom, css(add).paddingTop, css(add).paddingBottom], color: css(add).color,
                applied: css(document.querySelector('#jobOsRoot .match-inbox .job-os-badge[data-tone="info"]')).paddingTop};
    }""")
    assert out["caps"] == ["uppercase", "uppercase"] and out["run"] == "Run Now", out
    assert out["pad"] == ["1px", "1px", "1px", "1px"] and out["applied"] == "2px", out
    rgb = page.evaluate("""(c) => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c; x.fillRect(0, 0, 1, 1);
        return [...x.getImageData(0, 0, 1, 1).data].slice(0, 3); }""", out["color"])
    assert min(rgb) > 150, (out, rgb)  # light text, not the dark accent-contrast
