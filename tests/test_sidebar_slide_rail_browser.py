"""The side panel slides under the icon rail, never over it.

During a sidebar slide the panel is pinned (position:fixed, z-index 6) and
translated by its own width, so it crosses the rail. With no stacking order
of its own the rail was painted under it: the icons looked pushed away and
reappeared once the slide finished.
"""
import pytest

from tests._pytest_port import BASE

_RAIL_ON_TOP = """() => {
  const rail = document.querySelector('.rail').getBoundingClientRect();
  const hits = [0.25, 0.5, 0.75].map(f => document.elementFromPoint(rail.left + rail.width / 2, rail.top + rail.height * f));
  return hits.every(el => el && el.closest('.rail'));
}"""


def test_the_rail_stays_on_top_through_collapse_and_expand():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            cdp = page.context.new_cdp_session(page)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('tasks'); }")
            cdp.send("Animation.enable")
            results = {}
            for label in ("collapse", "expand"):
                # Freeze the slide part-way so the crossing can be inspected.
                cdp.send("Animation.setPlaybackRate", {"playbackRate": 0.02})
                page.evaluate("() => toggleSidebar()")
                page.wait_for_function("() => document.getAnimations().some(a => a.playState === 'running')",
                                       polling=50, timeout=10000)
                page.wait_for_timeout(1500)
                results[label] = {
                    "railOnTop": page.evaluate(_RAIL_ON_TOP),
                    "sliding": page.evaluate("() => document.getAnimations().some(a => a.playState === 'running')"),
                }
                cdp.send("Animation.setPlaybackRate", {"playbackRate": 1})
                page.wait_for_function("() => !document.getAnimations().some(a => a.playState === 'running')",
                                       polling=50, timeout=10000)
        finally:
            browser.close()

    for label, state in results.items():
        assert state["sliding"], f"{label}: precondition, the slide is still running"
        assert state["railOnTop"], f"{label}: the sliding panel covered the icon rail"


def test_the_side_panel_has_one_fixed_width_on_every_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.add_init_script("try { localStorage.setItem('hermes-sidebar-w', '410'); } catch (e) {}")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            widths = {}
            for panel in ("chat", "notes", "office", "tasks", "agents", "workspaces", "jobs"):
                page.evaluate(f"async () => {{ await switchPanel('{panel}'); }}")
                page.wait_for_timeout(250)
                widths[panel] = round(page.evaluate("() => document.querySelector('.sidebar').getBoundingClientRect().width"))
            handle = page.evaluate("() => !!document.getElementById('sidebarResize')")
            saved = page.evaluate("() => localStorage.getItem('hermes-sidebar-w')")
        finally:
            browser.close()
    assert set(widths.values()) == {300}, widths
    assert not handle, "no drag handle on the side panel"
    assert saved is None, "a width saved by the old handle is dropped"


def test_sidebar_slide_stays_transform_only_without_web_animations():
    """Old embedded WebViews can lack both Motion and Element.animate.

    That environment must still pin the panel and animate a compositor-only
    transform. Falling through to the stylesheet's width transition makes the
    heavier Office layout reflow on every frame and visibly stutter.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => typeof S !== 'undefined' && S._bootReady === true",
                polling=100,
                timeout=30000,
            )
            page.evaluate(
                "() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())"
            )
            page.evaluate("async () => { await switchPanel('office'); }")
            state = page.evaluate("""() => {
              window.MotionUI = null;
              Object.defineProperty(Element.prototype, 'animate', {
                configurable: true,
                value: undefined,
              });
              toggleSidebar();
              const panel = document.querySelector('.sidebar');
              return {
                collapsed: document.querySelector('.layout').classList.contains('sidebar-collapsed'),
                position: panel.style.getPropertyValue('position'),
                transition: panel.style.getPropertyValue('transition'),
                transform: panel.style.getPropertyValue('transform'),
              };
            }""")
            page.wait_for_timeout(320)
            settled = page.evaluate("""() => {
              const panel = document.querySelector('.sidebar');
              return {
                position: panel.style.getPropertyValue('position'),
                width: Math.round(panel.getBoundingClientRect().width),
              };
            }""")
        finally:
            browser.close()

    assert state["collapsed"] is True
    assert state["position"] == "fixed", state
    assert state["transition"].startswith("transform 240ms"), state
    assert "width" not in state["transition"], state
    assert state["transform"], state
    assert settled["position"] == "", settled
    assert settled["width"] <= 1, settled


def test_sidebar_slide_moves_main_as_one_rigid_body():
    """Main glides by translation only: its position moves, its width never does.

    Scaling main to interpolate its width stretched every glyph and card for
    the whole slide, which read as a wobble. The page keeps its final layout
    width and slides into place.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            cdp = page.context.new_cdp_session(page)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('tasks'); }")
            cdp.send("Animation.enable")
            results = {}
            for label in ("collapse", "expand"):
                before = page.evaluate("() => { const r = document.querySelector('.main').getBoundingClientRect(); return {left: r.left, width: r.width}; }")
                cdp.send("Animation.setPlaybackRate", {"playbackRate": 0.02})
                page.evaluate("() => toggleSidebar()")
                page.wait_for_function("() => document.querySelector('.main').getAnimations().some(a => a.playState === 'running')",
                                       polling=50, timeout=10000)
                page.wait_for_timeout(800)
                moving = page.evaluate("""() => ({
                  panelPosition: document.querySelector('.sidebar').style.getPropertyValue('position'),
                  matrix: getComputedStyle(document.querySelector('.main')).transform,
                  rect: (() => { const r = document.querySelector('.main').getBoundingClientRect(); return {left: r.left, width: r.width}; })(),
                })""")
                cdp.send("Animation.setPlaybackRate", {"playbackRate": 1})
                page.wait_for_function("() => !document.querySelector('.main').getAnimations().length", polling=50, timeout=10000)
                settled = page.evaluate("() => { const r = document.querySelector('.main').getBoundingClientRect(); return {left: r.left, width: r.width}; }")
                results[label] = (before, moving, settled)
        finally:
            browser.close()

    for label, (before, moving, settled) in results.items():
        assert moving["matrix"].startswith("matrix(1, 0, 0, 1,"), (label, moving)  # translate only, no scale
        assert abs(moving["rect"]["width"] - settled["width"]) < 2, (label, moving, settled)  # width never interpolates
        low, high = sorted((before["left"], settled["left"]))
        assert low + 1 < moving["rect"]["left"] < high - 1, (label, before, moving, settled)  # but position does
    assert results["collapse"][1]["panelPosition"] == "fixed"


def test_expanding_the_sidebar_slides_main_to_its_final_place_without_a_late_jump():
    """On expand, main must already sit at its expanded layout box during the slide.

    The FLIP transform on main is measured against the expanded layout. If the
    panel is pinned out of the flex row, main sits at the *collapsed* box for
    the whole slide and snaps right when the pin is dropped: the page glides
    to the left edge, then jumps to where it belongs.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    # Scoped to the two sliding elements: the Jobs page has endless pulse animations.
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            cdp = page.context.new_cdp_session(page)
            page.goto(BASE + "/#jobs/dashboard", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(".job-os-shell", timeout=15000)
            expanded = page.evaluate("() => { const m = document.querySelector('.main'); return [m.offsetLeft, m.offsetWidth]; }")
            page.evaluate("() => toggleSidebar(true)")
            page.wait_for_function("() => ![...document.querySelector('.sidebar').getAnimations(), ...document.querySelector('.main').getAnimations()].some(a => a.playState === 'running')", polling=50, timeout=10000)
            collapsed = page.evaluate("() => { const m = document.querySelector('.main'); return [m.offsetLeft, m.offsetWidth]; }")
            cdp.send("Animation.enable")
            cdp.send("Animation.setPlaybackRate", {"playbackRate": 0.02})
            page.evaluate("() => toggleSidebar(false)")
            page.wait_for_function("() => [...document.querySelector('.sidebar').getAnimations(), ...document.querySelector('.main').getAnimations()].some(a => a.playState === 'running')", polling=50, timeout=10000)
            page.wait_for_timeout(800)
            during = page.evaluate("""() => {
              const m = document.querySelector('.main');
              return {box: [m.offsetLeft, m.offsetWidth], visibleLeft: m.getBoundingClientRect().left,
                      panelPosition: document.querySelector('.sidebar').style.getPropertyValue('position')};
            }""")
            cdp.send("Animation.setPlaybackRate", {"playbackRate": 1})
            page.wait_for_function("() => ![...document.querySelector('.sidebar').getAnimations(), ...document.querySelector('.main').getAnimations()].some(a => a.playState === 'running')", polling=50, timeout=10000)
            settled = page.evaluate("() => { const m = document.querySelector('.main'); return [m.offsetLeft, m.offsetWidth]; }")
        finally:
            browser.close()

    assert collapsed != expanded, "precondition: the sidebar changes main's box"
    assert settled == expanded, settled
    assert during["box"] == expanded, during  # main already at its final box mid-slide
    assert collapsed[0] < during["visibleLeft"] < expanded[0], during  # and gliding toward it
    assert during["panelPosition"] != "fixed", during  # an expanding panel keeps its flex slot
