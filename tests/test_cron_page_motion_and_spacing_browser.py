"""Scheduled Jobs page: the side list's highlight slides between jobs, and the
detail cards keep their contents equally far from top, bottom and left."""
import json

import pytest

from tests._pytest_port import BASE

_JOBS = [
    {"id": f"job{i}", "name": name, "script": f"{name}.py", "no_agent": True, "skills": [],
     "schedule": schedule, "schedule_display": schedule.get("display", ""), "repeat": {"times": None, "completed": 3},
     "enabled": True, "state": "scheduled", "next_run_at": next_run, "last_run_at": "2026-10-27T21:00:14+00:00",
     "last_status": "error", "last_error": "Script execution failed", "deliver": "local", "profile": "docs-gits"}
    for i, (name, schedule, next_run) in enumerate([
        ("backup", {"kind": "cron", "expr": "0 0 * * *", "display": "every day at 12am"}, None),
        ("refresh", {"kind": "interval", "minutes": 15, "display": "every 15m"}, "2026-10-30T18:00:00+00:00"),
        ("digest", {"kind": "interval", "minutes": 60, "display": "every 60m"}, "2026-10-30T18:00:00+00:00"),
    ])
]


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        body = json.dumps({"jobs": _JOBS, "other_profile_count": 0})
        page.route("**/api/crons", lambda route: route.fulfill(status=200, content_type="application/json", body=body))
        page.route("**/api/crons?*", lambda route: route.fulfill(status=200, content_type="application/json", body=body))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
        page.evaluate("async () => { await switchPanel('tasks'); }")
        page.wait_for_function("() => document.querySelectorAll('.cron-item').length >= 3", timeout=15000)
        try:
            yield page
        finally:
            browser.close()


def test_job_highlight_slides_to_the_next_job(page):
    items = page.locator(".cron-item")
    items.nth(0).click()
    page.wait_for_timeout(500)
    page.mouse.move(900, 880)
    start, end = (items.nth(i).bounding_box()["y"] for i in (0, 2))
    seen = page.evaluate("""async () => {
        const seen = []; let running = true;
        const tick = () => { const g = document.querySelector('.sidebar-highlight-glide');
            if (g) seen.push(g.getBoundingClientRect().top); if (running) requestAnimationFrame(tick); };
        requestAnimationFrame(tick);
        document.querySelectorAll('.cron-item')[2].click();
        await new Promise(r => setTimeout(r, 600)); running = false; return seen;
    }""")
    assert any(start + 4 < top < end - 4 for top in seen), (start, end, seen)
    assert page.evaluate("() => document.querySelectorAll('.cron-item')[2].classList.contains('active')")


def test_detail_cards_have_equal_inner_margins(page):
    page.locator(".cron-item").nth(0).click()
    page.wait_for_selector("#taskDetailBody .cron-attention-panel", timeout=10000)
    page.wait_for_timeout(400)
    insets = page.evaluate("""() => [...document.querySelectorAll('#taskDetailBody .detail-alert, #taskDetailBody .detail-card')].map(card => {
        const box = card.getBoundingClientRect(); let top = 1e9, bottom = -1e9, left = 1e9;
        const range = document.createRange(), walk = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
        const take = r => { if (!r.width) return; top = Math.min(top, r.top); bottom = Math.max(bottom, r.bottom); left = Math.min(left, r.left); };
        while (walk.nextNode()) { if (!walk.currentNode.textContent.trim()) continue; range.selectNodeContents(walk.currentNode); [...range.getClientRects()].forEach(take); }
        card.querySelectorAll('button,.detail-badge,code,pre').forEach(el => take(el.getBoundingClientRect()));
        return {card: card.className, top: top - box.top, bottom: box.bottom - bottom, left: left - box.left};
    })""")
    assert len(insets) >= 3, insets
    for inset in insets:
        assert abs(inset["top"] - inset["bottom"]) <= 1.5 and abs(inset["top"] - inset["left"]) <= 1.5, inset


def test_badges_are_rounded_rectangles_not_pills(page):
    page.locator(".cron-item").nth(0).click()
    page.wait_for_selector("#taskDetailBody .detail-badge", timeout=10000)
    pills = page.evaluate("""() => [...document.querySelectorAll('#panelTasks *, #mainTasks *')].filter(el => {
        const r = el.getBoundingClientRect(); if (r.width < 8 || r.height < 8) return false;
        const c = getComputedStyle(el), radius = parseFloat(c.borderTopLeftRadius);
        const drawn = (parseFloat(c.borderTopWidth) > 0 && c.borderTopColor !== 'rgba(0, 0, 0, 0)') || c.backgroundColor !== 'rgba(0, 0, 0, 0)';
        return drawn && radius > 6 && radius >= Math.min(r.width, r.height) / 2 - 1;
    }).map(el => el.className)""")
    assert pills == [], pills


def test_badge_text_sits_one_pixel_above_centre(page):
    page.locator(".cron-item").nth(0).click()
    page.wait_for_selector("#taskDetailBody .detail-badge", timeout=10000)
    # In the side list a pixel of the top padding moves below the text, so the
    # badge keeps its height and its text is drawn 1px higher than centred;
    # the detail card's badges stay centred.
    shifts = page.evaluate("""() => [...document.querySelectorAll('#panelTasks .cron-profile-badge, #panelTasks .cron-status, #mainTasks .detail-badge')]
        .map(b => { const c = getComputedStyle(b); return [b.className, parseFloat(c.paddingBottom) - parseFloat(c.paddingTop)]; })""")
    assert shifts and all(shift == (0 if cls.startswith('detail-badge') else 2) for cls, shift in shifts), shifts
    # The schedule's code box reaches 2px further below its text than above.
    code = page.evaluate("""() => { const c = getComputedStyle(document.querySelector('#taskDetailBody .detail-row-value code'));
        return parseFloat(c.paddingBottom) - parseFloat(c.paddingTop); }""")
    assert code == 2, code
