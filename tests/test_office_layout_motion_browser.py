"""The Office floor stays undistorted while a side panel slides.

A panel collapse/expand commits the new layout at once and slides the content
with a transform (FLIP). The Office pauses its render loop for that slide, but
it used to skip the resize too, so the stale drawing buffer was stretched over
the new canvas box for the whole slide (~27% wider on a sidebar collapse) and
the floor, framing and pod cards snapped into place only after it settled.
The resize and one redraw now happen in the first frame of the slide.

Opt-in like the other WebGL checks: HERMES_WEBUI_BROWSER_TESTS=1.
"""
import os
import shutil

import pytest

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
        reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1",
    ),
    pytest.mark.skipif(
        not (shutil.which("chromium") or shutil.which("chromium-browser")),
        reason="needs a chromium",
    ),
]


def test_paused_office_redraws_at_the_new_size_when_a_panel_slides(base_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        ])
        try:
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(base_url, wait_until="load")
            pg.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            pg.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            pg.evaluate("() => window.switchPanel('office')")
            pg.wait_for_selector(".office-canvas", timeout=30000)
            pg.wait_for_function("() => window.HermesOffice && window.HermesOffice.isRunning()", polling=100, timeout=30000)

            result = pg.evaluate("""() => new Promise(resolve => {
              const canvas = document.querySelector('.office-canvas');
              const layout = document.querySelector('.layout');
              const before = canvas.width;
              const sidebar = document.querySelector('.sidebar');
              // What the shared slide does: pause, suppress the CSS width
              // transition, then commit the final layout in one step.
              window.HermesOffice.pauseForLayoutMotion();
              sidebar.style.setProperty('transition', 'none', 'important');
              layout.classList.toggle('sidebar-collapsed');
              requestAnimationFrame(() => requestAnimationFrame(() => {
                const box = Math.round(canvas.clientWidth * Math.min(devicePixelRatio || 1, 2));
                const out = {before, buffer: canvas.width, box, runningWhilePaused: window.HermesOffice.isRunning()};
                window.HermesOffice.resumeAfterLayoutMotion();
                layout.classList.toggle('sidebar-collapsed');
                sidebar.style.removeProperty('transition');
                resolve(out);
              }));
            })""")
        finally:
            b.close()

    assert result["box"] != result["before"], f"the layout change must resize the canvas box: {result}"
    assert abs(result["buffer"] - result["box"]) <= 1, (
        f"the paused Office kept a stale drawing buffer stretched over the new box: {result}"
    )
    assert result["runningWhilePaused"] is False, "the render loop stays paused for the slide"
