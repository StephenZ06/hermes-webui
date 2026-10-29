"""Chat's jump buttons fade and grow in, and fade out, instead of popping.

Their JS only switches an inline display; the CSS carries the motion
(@starting-style for the entrance, display allow-discrete for the exit).
"""
import pytest

from tests._pytest_port import BASE


@pytest.mark.parametrize("button", ["scrollToBottomBtn", "jumpToSessionStartBtn"])
def test_a_jump_button_fades_in_and_out(button):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1300, "height": 800})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('chat'); }")
            # A copy with the same classes, so the chat's own scroll syncing
            # (which sets the real button's display) does not race the probe.
            page.evaluate(f"""() => {{ const real = document.getElementById('{button}');
                const copy = real.cloneNode(true); copy.id = 'jumpProbe'; copy.removeAttribute('onclick');
                copy.style.display = 'none'; real.parentElement.appendChild(copy); }}""")
            page.wait_for_timeout(300)
            # Sample across the transition: when its first frame lands varies.
            frames = """async (display) => { const node = document.getElementById('jumpProbe'); node.style.display = display;
                const out = []; const start = performance.now();
                while (performance.now() - start < 350) { await new Promise(r => requestAnimationFrame(r));
                    const c = getComputedStyle(node); out.push([c.display, +c.opacity]); }
                return out; }"""
            entering = page.evaluate(frames, "flex")
            leaving = page.evaluate(frames, "none")
        finally:
            browser.close()
    # Partly faded in on the way in, then fully shown.
    assert any(d == "flex" and 0 < o < 0.9 for d, o in entering) and entering[-1] == ["flex", 1], entering
    # Still drawn while it fades out, then hidden.
    assert any(d == "flex" and 0 < o < 1 for d, o in leaving) and leaving[-1][0] == "none", leaving
