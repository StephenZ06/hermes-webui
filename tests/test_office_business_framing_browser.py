"""Office: the Business floor is framed by what the camera actually sees of it.

A circle round the floor left a Business office (a ring of departments plus a
large overflow pod to one side) off-centre: clipped at the side of the narrow
workspace panel, and with The Floor run off the bottom of the Office page.
Opt-in like the other WebGL Office tests (SwiftShader is slow).
"""
import os

import pytest

from tests._pytest_port import BASE

pytestmark = pytest.mark.skipif(os.environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
                                reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1")

CARDS = """() => { const stage = document.querySelector('#officeCanvas').parentElement.getBoundingClientRect();
    return {stage: [stage.left, stage.top, stage.right, stage.bottom],
            cards: [...document.querySelectorAll('.office-dept-card')].filter(c => c.offsetParent).map(c => {
                const r = c.getBoundingClientRect(); return [c.textContent.trim().split(/\\s+/).slice(0, 2).join(' '), r.left, r.top, r.right, r.bottom]; })}; }"""


def _business(page, panel):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.evaluate("(p) => { localStorage.setItem('hermes-webui-workspace-pinned', '0'); localStorage.setItem('hermes-webui-workspace-panel', p ? 'open' : 'closed'); }", panel)
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=200)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    if panel:
        page.evaluate("async () => { await switchPanel('chat'); toggleWorkspacePanel(true); switchWorkspacePanelTab('office'); }")
    else:
        page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_selector("#officeCanvas", state="attached")
    page.wait_for_timeout(4000)
    page.evaluate("() => [...document.querySelectorAll('.office-outlet-btn[data-outlet=business]')].find(b => b.offsetParent).click()")
    # The camera glides to the new frame (slowly under SwiftShader): wait until
    # the department cards, which ride on their pods, stop moving.
    last = None
    for _ in range(90):
        page.wait_for_timeout(1000)
        shot = page.evaluate(CARDS)
        key = [[round(v) for v in card[1:]] for card in shot["cards"]]
        if key and key == last:
            return shot
        last = key
    return shot


def _launch(pw):
    return pw.chromium.launch(args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])


def test_business_floor_fits_the_office_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = _launch(pw)
        try:
            page = browser.new_page(viewport={"width": 1500, "height": 900})
            page.set_default_timeout(240000)
            shot = _business(page, panel=False)
        finally:
            browser.close()
    left, top, right, bottom = shot["stage"]
    floor = [c for c in shot["cards"] if c[0].lower().startswith("the floor")]
    assert floor, shot
    # The Floor's card sits above its pod: the pod needs room below it.
    assert floor[0][4] < bottom - (bottom - top) * 0.15, shot


def test_business_floor_fits_the_narrow_workspace_panel():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = _launch(pw)
        try:
            page = browser.new_page(viewport={"width": 1500, "height": 900})
            page.set_default_timeout(240000)
            shot = _business(page, panel=True)
        finally:
            browser.close()
    left, top, right, bottom = shot["stage"]
    assert len(shot["cards"]) >= 7, shot
    centres = [(l + r) / 2 for _, l, _, r, _ in shot["cards"]]
    assert all(left - 1 <= x <= right + 1 for x in centres), shot   # every department is on the stage
    # and the floor fills the narrow stage instead of sitting small in it
    # (department centres span 0.44 of it framed by the box, 0.38 by the circle)
    assert max(centres) - min(centres) > (right - left) * 0.41, shot
