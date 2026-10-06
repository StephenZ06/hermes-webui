"""Office: a side-panel slide scales the last frame instead of redrawing it.

Redrawing the bloom pipeline at full drawing-buffer size on every frame of a
slide is the costliest thing the Office does (an integrated GPU drops frames).
Mid-slide the canvas carries a CSS scale matching the framed zoom; the real
frame is drawn once when the slide ends and the scale is dropped.
Opt-in like the other WebGL Office tests (SwiftShader is slow).
"""
import os

import pytest

from tests._pytest_port import BASE

pytestmark = pytest.mark.skipif(os.environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
                                reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1")


def test_office_slide_scales_the_frame_then_settles_unscaled():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader"])
        try:
            # Taller than wide, so the framed zoom is width-limited and a slide changes it.
            page = browser.new_page(viewport={"width": 1180, "height": 1300})
            page.set_default_timeout(240000)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=200)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('office'); }")
            page.wait_for_selector("#officeCanvas", state="attached")
            page.wait_for_timeout(4000)
            page.evaluate("() => { window.__hermesSlideTimeScale = 0.05; toggleSidebar(true); }")
            page.wait_for_function("() => /scale\\(/.test(document.querySelector('#officeCanvas').style.transform)", polling=100)
            mid = page.evaluate("() => document.querySelector('#officeCanvas').style.transform")
            page.evaluate("() => { window.__hermesSlideTimeScale = 1; }")
            page.wait_for_selector(".layout.panel-sliding", state="detached")
            page.wait_for_function("() => document.querySelector('#officeCanvas').style.transform === ''", polling=100)
            settled = page.evaluate("() => document.querySelector('#officeCanvas').style.transform")
        finally:
            browser.close()
    assert mid.startswith("translateX(-50%) scale("), mid
    assert settled == ""
