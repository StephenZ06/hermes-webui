"""Icon-only rail: the rounded hover/active square sits 0.5px further right
while the icon inside it stays where it was."""

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            yield tab
        finally:
            browser.close()


def test_rail_squares_move_right_and_icons_stay(page):
    got = page.evaluate("""() => { const rail = document.querySelector('.rail').getBoundingClientRect();
      return [...document.querySelectorAll('.rail .rail-btn:not([hidden])')].map(b => {
        const r = b.getBoundingClientRect(), i = b.firstElementChild.getBoundingClientRect();
        return {box: r.left - rail.left, icon: i.left + i.width / 2 - rail.left, w: r.width}; }); }""")
    assert got
    for btn in got:
        # Unshifted, the 36px square starts 6px in and its icon is centred on 24px.
        assert btn["box"] == 6.5 and btn["icon"] == 24, btn
    marker = page.evaluate("() => { const b = document.querySelector('.rail .rail-btn.active'); return b ? getComputedStyle(b, '::before').left : null; }")
    assert marker in (None, "-6.5px")
