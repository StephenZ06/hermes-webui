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


def test_workspace_pin_glide_draws_the_final_frame_first_and_lands_without_a_redraw():
    """Pinning the workspace panel: the floor's final frame is drawn as the glide starts, and the
    canvas box holds its size meanwhile (no stretched buffer), so landing has nothing to change."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader"])
        try:
            page = browser.new_page(viewport={"width": 1500, "height": 860})
            page.set_default_timeout(240000)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.evaluate("() => { try { localStorage.setItem('hermes-webui-workspace-pinned', '0'); } catch (e) {} }")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=200)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("() => { toggleWorkspacePanel(true); switchWorkspacePanelTab('office'); }")
            page.wait_for_selector(".rightpanel #officeCanvas", state="attached")
            page.wait_for_selector(".layout.panel-sliding", state="detached")
            page.wait_for_timeout(4000)
            start = page.evaluate("""() => { const c = document.querySelector('.rightpanel #officeCanvas');
                const before = c.width; toggleWorkspacePin(true);
                return {before, buffer: c.width, box: c.style.width, boxPx: c.clientWidth}; }""")
            page.wait_for_function("() => !document.querySelector('.rightpanel.workspace-pin-gliding')", polling=100)
            page.wait_for_function("() => document.querySelector('.rightpanel #officeCanvas').style.transform === ''", polling=100)
            page.wait_for_timeout(300)
            end = page.evaluate("""() => { const c = document.querySelector('.rightpanel #officeCanvas');
                return {buffer: c.width, box: c.style.width, boxPx: c.clientWidth}; }""")
        finally:
            browser.close()
    assert start["buffer"] > start["before"], start          # the wider final frame is drawn up front
    assert start["box"] == f"{start['boxPx']}px", start      # and the canvas box is held while the panel glides
    assert end["buffer"] == start["buffer"], (start, end)    # landing reallocates nothing
    assert end["box"] == "" and end["boxPx"] == start["boxPx"], (start, end)


def test_closing_and_reopening_the_workspace_panel_keeps_the_office_canvas():
    """A closed panel collapses the Office stage to nothing; the floor must not shrink its canvas to
    fit that, or reopening the panel has to resize it a second time."""
    sync_api = pytest.importorskip("playwright.sync_api")
    state = """() => { const c = document.querySelector('.rightpanel #officeCanvas');
        return [c.width, c.clientWidth, c.parentElement.clientWidth]; }"""
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader"])
        try:
            page = browser.new_page(viewport={"width": 1500, "height": 860})
            page.set_default_timeout(240000)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.evaluate("() => { try { localStorage.setItem('hermes-webui-workspace-pinned', '0'); } catch (e) {} }")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=200)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("() => { toggleWorkspacePanel(true); switchWorkspacePanelTab('office'); }")
            page.wait_for_selector(".rightpanel #officeCanvas", state="attached")
            page.wait_for_selector(".layout.panel-sliding", state="detached")
            page.wait_for_timeout(4000)
            opened = page.evaluate(state)
            page.evaluate("() => toggleWorkspacePanel(false)")
            page.wait_for_selector(".layout.panel-sliding", state="detached")
            page.wait_for_timeout(1500)
            closed = page.evaluate(state)
            page.evaluate("() => toggleWorkspacePanel(true)")
            page.wait_for_selector(".layout.panel-sliding", state="detached")
            page.wait_for_timeout(1500)
            reopened = page.evaluate(state)
        finally:
            browser.close()
    assert closed[2] < 2, closed                        # the stage really is collapsed while closed
    assert closed[:2] == opened[:2], (opened, closed)    # yet the canvas and its buffer are untouched
    assert reopened == opened, (opened, reopened)


def test_a_hidden_office_stops_drawing_and_reopens_at_its_remembered_size():
    """Closing the panel stops the floor's render loop (nobody can see it), opening it restarts the loop,
    and a floor mounted on a fresh page starts at the canvas size it last had in the panel."""
    sync_api = pytest.importorskip("playwright.sync_api")
    boot = "() => typeof S !== 'undefined' && S._bootReady === true"
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
                                           "--enable-unsafe-swiftshader"])
        try:
            context = browser.new_context(viewport={"width": 1500, "height": 860})
            page = context.new_page()
            page.set_default_timeout(240000)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.evaluate("() => { try { localStorage.setItem('hermes-webui-workspace-pinned', '0'); } catch (e) {} }")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function(boot, polling=200)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("() => { toggleWorkspacePanel(true); switchWorkspacePanelTab('office'); }")
            page.wait_for_function("() => window.HermesOffice && window.HermesOffice.isRunning()", polling=200)
            page.wait_for_selector(".layout.panel-sliding", state="detached")
            page.wait_for_timeout(3000)
            width = page.evaluate("() => document.querySelector('.rightpanel #officeCanvas').clientWidth")
            page.evaluate("() => toggleWorkspacePanel(false)")
            page.wait_for_selector(".layout.panel-sliding", state="detached")
            page.wait_for_timeout(1500)
            stopped = page.evaluate("() => window.HermesOffice.isRunning()")
            page.evaluate("() => toggleWorkspacePanel(true)")
            page.wait_for_function("() => window.HermesOffice.isRunning()", polling=200)
            page.close()

            fresh = context.new_page()
            fresh.set_default_timeout(240000)
            fresh.goto(BASE + "/", wait_until="domcontentloaded")
            fresh.wait_for_function(boot, polling=200)
            fresh.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            fresh.evaluate("() => { if (document.documentElement.dataset.workspacePanel !== 'closed') toggleWorkspacePanel(false); }")
            fresh.wait_for_timeout(1000)
            fresh.evaluate("""() => { window.__firstWidth = null;
                new MutationObserver((_, obs) => { const c = document.querySelector('.rightpanel #officeCanvas');
                    if (c) { window.__firstWidth = c.clientWidth; obs.disconnect(); } }).observe(document.body, {subtree: true, childList: true});
                toggleWorkspacePanel(true); switchWorkspacePanelTab('office'); }""")
            fresh.wait_for_function("() => window.__firstWidth !== null", polling=100)
            first = fresh.evaluate("() => window.__firstWidth")
        finally:
            browser.close()
    assert stopped is False
    assert first == width, (first, width)   # no collapsed canvas growing into place
