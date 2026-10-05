"""The app never scrolls sideways at desktop width.

With the workspace panel closed, its slide-out transform left it 14px past
the right edge, so the whole page could be dragged sideways by 14px on
desktop (phones already clipped .layout).
"""
import pytest

from tests._pytest_port import BASE


@pytest.mark.parametrize("width", [1440, 1100])
def test_closed_workspace_panel_does_not_widen_the_page(width):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("() => document.documentElement.dataset.workspacePanel = 'closed'")
            page.wait_for_timeout(600)
            state = page.evaluate("""() => { const de = document.documentElement; window.scrollTo(400, 0);
              return {scrollWidth: de.scrollWidth, clientWidth: de.clientWidth, scrollX: window.scrollX}; }""")
        finally:
            browser.close()
    assert state["scrollWidth"] == state["clientWidth"], state
    assert state["scrollX"] == 0, state
