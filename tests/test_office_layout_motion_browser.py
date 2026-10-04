"""A side-panel slide never resizes the Office's WebGL drawing buffer.

Resizing the buffer reallocates the canvas backbuffer and every bloom render
target (renderer.setSize was effectively the whole cost of an Office sidebar
toggle in a CPU profile). Done after the slide it was a hitch plus a stretched
floor during it; done in the slide's first frame it delayed the slide.

The canvas is now laid out as wide as the stage gets with the sidebar
collapsed and centred in the clipping stage, so both sidebar states use the
same buffer; only the visible framing changes.

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

_SETTLED = "() => !document.getAnimations().some(a => a.playState === 'running')"
_STATE = """() => {
  const canvas = document.querySelector('.office-canvas');
  const stage = document.querySelector('.office-stage');
  const c = canvas.getBoundingClientRect();
  const s = stage.getBoundingClientRect();
  return {
    buffer: [canvas.width, canvas.height],
    stageWidth: Math.round(s.width),
    canvasWidth: Math.round(c.width),
    centreOffset: Math.round((c.left + c.width / 2) - (s.left + s.width / 2)),
    collapsed: document.querySelector('.layout').classList.contains('sidebar-collapsed'),
  };
}"""


def test_sidebar_toggles_keep_the_office_drawing_buffer(base_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    states = []
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
            pg.wait_for_function("() => window.HermesOffice && window.HermesOffice.isRunning()", polling=100, timeout=60000)
            states.append(pg.evaluate(_STATE))
            for _ in range(2):
                pg.evaluate("() => toggleSidebar()")
                pg.wait_for_function(_SETTLED, polling=100, timeout=60000)
                pg.wait_for_function("() => window.HermesOffice.isRunning()", polling=100, timeout=60000)
                states.append(pg.evaluate(_STATE))
        finally:
            b.close()

    assert states[0]["collapsed"] != states[1]["collapsed"], states
    assert states[0]["stageWidth"] != states[1]["stageWidth"], f"the toggle must change the stage: {states}"
    assert len({tuple(s["buffer"]) for s in states}) == 1, (
        f"a sidebar toggle reallocated the WebGL drawing buffer: {states}"
    )
    for state in states:
        assert state["canvasWidth"] >= state["stageWidth"], f"the canvas must cover the stage: {state}"
        assert abs(state["centreOffset"]) <= 1, f"the floor must stay centred in the stage: {state}"
