"""Phone viewports must not scroll horizontally.

The mobile work is mostly media queries, and the failure they exist to prevent
is the one users actually feel: a single unconstrained element widening the
document so the whole page slides sideways under the thumb. Nothing pinned
that property, so a stray fixed width or an un-wrapped code block could
reintroduce it silently.

Deliberately narrow. Elements sitting outside the viewport are NOT asserted
against: the mobile sidebar is an off-canvas drawer, so a large set of
controls is off-screen by design until it opens, and asserting on that would
fail the intended pattern.
"""
import pytest

from tests._pytest_port import BASE

_BROWSER_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

# Small, common, and one deliberately narrow device: 360px is the floor most
# Android phones still report.
_VIEWPORTS = [
    pytest.param(390, 844, id="iphone-13"),
    pytest.param(393, 851, id="pixel-5"),
    pytest.param(360, 800, id="narrow-android"),
]


@pytest.mark.parametrize("width,height", _VIEWPORTS)
def test_no_horizontal_overflow_on_phone_viewports(width, height):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=_BROWSER_ARGS)
        page = browser.new_page(
            viewport={"width": width, "height": height},
            is_mobile=True, has_touch=True, device_scale_factor=2,
        )
        try:
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => typeof S !== 'undefined' && S._bootReady === true", timeout=15000)
            page.wait_for_timeout(400)
            overflow = page.evaluate(
                """() => {
                    const de = document.documentElement, b = document.body;
                    return Math.max(de.scrollWidth, b.scrollWidth) - window.innerWidth;
                }"""
            )
            widest = page.evaluate(
                """() => {
                    let worst = null, worstRight = -Infinity;
                    document.querySelectorAll('*').forEach(el => {
                        const r = el.getBoundingClientRect();
                        const cs = getComputedStyle(el);
                        if (cs.display === 'none' || cs.visibility === 'hidden') return;
                        if (cs.position === 'fixed' || cs.position === 'absolute') return;
                        if (r.width === 0 || r.right <= worstRight) return;
                        worstRight = r.right;
                        worst = (el.id || el.className || el.tagName).toString().slice(0, 60);
                    });
                    return {worst, worstRight: Math.round(worstRight)};
                }"""
            )
        finally:
            browser.close()

    assert overflow <= 0, (
        f"document is {overflow}px wider than the {width}px viewport; widest "
        f"in-flow element: {widest}"
    )
