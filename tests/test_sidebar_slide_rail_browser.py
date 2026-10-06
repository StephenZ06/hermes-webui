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
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('tasks'); }")
            results = {}
            for label in ("collapse", "expand"):
                # Slow the slide right down so the crossing can be inspected part-way.
                page.evaluate("() => { window.__hermesSlideTimeScale = 0.02; toggleSidebar(); }")
                page.wait_for_selector(".layout.panel-sliding", state="attached", timeout=10000)
                page.wait_for_timeout(1500)
                results[label] = {
                    "railOnTop": page.evaluate(_RAIL_ON_TOP),
                    "sliding": page.evaluate("() => document.querySelector('.layout').classList.contains('panel-sliding')"),
                }
                page.evaluate("() => { window.__hermesSlideTimeScale = 1; }")
                page.wait_for_selector(".layout.panel-sliding", state="detached", timeout=10000)
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
            page.evaluate("async () => { await switchPanel('tasks'); }")
            state = page.evaluate("""() => {
              // An iframe keeps the page on the single-layout compositor slide.
              document.querySelector('#mainTasks').appendChild(document.createElement('iframe'));
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


_SAMPLE_SLIDE = """(direction) => new Promise((resolve) => {
  const main = document.querySelector('.main');
  const layout = document.querySelector('.layout');
  const read = () => { const r = main.getBoundingClientRect(); return {left: r.left, width: r.width, center: r.left + r.width / 2, transform: getComputedStyle(main).transform}; };
  const before = read();
  const frames = [];
  toggleSidebar(direction === 'collapse');
  const tick = () => {
    frames.push(read());
    if (layout.classList.contains('panel-sliding') || frames.length < 3) requestAnimationFrame(tick);
    else resolve({before, frames, settled: read()});
  };
  requestAnimationFrame(tick);
})"""


def _slide(page, direction):
    return page.evaluate(_SAMPLE_SLIDE, direction)


def _open(page, panel):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate(f"async () => {{ await switchPanel('{panel}'); }}")
    page.wait_for_timeout(300)


def test_main_is_laid_out_at_every_width_while_the_sidebar_slides():
    """The page follows the sidebar by real layout, not by a transform.

    A single transform on <main> can't be right for everything inside it:
    translating by the left-edge delta sent centred content ~150px the wrong
    way on the first frame, and scaling stretched every glyph. So <main> gets
    the space the panel vacates as a margin on the same curve, and the page is
    laid out at each in-between width: width and position both interpolate,
    and no transform is involved.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open(page, "tasks")
            runs = {d: _slide(page, d) for d in ("collapse", "expand")}
        finally:
            browser.close()

    for direction, run in runs.items():
        before, frames, settled = run["before"], run["frames"], run["settled"]
        assert abs(before["width"] - settled["width"]) > 100, "precondition: the sidebar changes main's width"
        assert all(f["transform"] == "none" for f in frames), (direction, frames[:3])
        for field in ("left", "width"):
            low, high = sorted((before[field], settled[field]))
            between = [f for f in frames if low + 3 < f[field] < high - 3]
            assert len(between) >= 5, (direction, field, "layout should pass through intermediate values", len(between))
        # Settling hands the space back to the flex row: no jump at the end.
        assert abs(frames[-1]["left"] - settled["left"]) < 3 and abs(frames[-1]["width"] - settled["width"]) < 3, (direction, frames[-2:], settled)


def test_centred_content_moves_one_way_when_the_sidebar_slides():
    """Centred content must glide from its old centre to its new one.

    Regression: with <main> moved by one transform, expanding made the page
    centre jump ~150px left on frame one and then travel ~300px right.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open(page, "tasks")
            collapse = _slide(page, "collapse")
            page.wait_for_timeout(200)
            expand = _slide(page, "expand")
        finally:
            browser.close()

    for direction, run, sign in (("expand", expand, 1), ("collapse", collapse, -1)):
        centres = [run["before"]["center"]] + [f["center"] for f in run["frames"]] + [run["settled"]["center"]]
        steps = [(b - a) * sign for a, b in zip(centres, centres[1:])]
        assert min(steps) >= -1.5, (direction, "page centre stepped backwards", [round(c) for c in centres])
        assert abs(centres[1] - centres[0]) < 60, (direction, "first frame must start where the page was", centres[:3])
        assert (centres[-1] - centres[0]) * sign > 100, (direction, "the page centre must travel", centres[0], centres[-1])


def test_the_panel_leaves_the_flex_row_only_while_it_slides():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open(page, "tasks")
            page.evaluate("() => { window.__hermesSlideTimeScale = 0.02; toggleSidebar(); }")
            page.wait_for_selector(".layout.panel-sliding", state="attached", timeout=10000)
            page.wait_for_timeout(400)
            moving = page.evaluate("""() => { const p = document.querySelector('.sidebar'); return {position: p.style.getPropertyValue('position'), margin: document.querySelector('.main').style.getPropertyValue('margin-left')}; }""")
            page.evaluate("() => { window.__hermesSlideTimeScale = 1; }")
            page.wait_for_selector(".layout.panel-sliding", state="detached", timeout=10000)
            settled = page.evaluate("""() => { const p = document.querySelector('.sidebar'); return {position: p.style.getPropertyValue('position'), transform: p.style.getPropertyValue('transform'), margin: document.querySelector('.main').style.getPropertyValue('margin-left')}; }""")
        finally:
            browser.close()
    assert moving["position"] == "fixed" and moving["margin"].endswith("px"), moving
    assert settled == {"position": "", "transform": "", "margin": ""}, settled


def test_toggling_again_mid_slide_reverses_from_where_the_page_is():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open(page, "tasks")
            result = page.evaluate("""() => new Promise((resolve) => {
              const main = document.querySelector('.main');
              const layout = document.querySelector('.layout');
              toggleSidebar(true);                     // collapse...
              setTimeout(() => {
                const mid = main.getBoundingClientRect().left;
                toggleSidebar(false);                  // ...reverse part-way
                const frames = [];
                const tick = () => {
                  frames.push(main.getBoundingClientRect().left);
                  if (layout.classList.contains('panel-sliding')) requestAnimationFrame(tick);
                  else resolve({mid, frames, collapsed: layout.classList.contains('sidebar-collapsed'),
                                margin: main.style.getPropertyValue('margin-left'),
                                panel: document.querySelector('.sidebar').style.getPropertyValue('position'),
                                left: main.getBoundingClientRect().left});
                };
                requestAnimationFrame(tick);
              }, 90);
            })""")
        finally:
            browser.close()
    assert result["collapsed"] is False, result
    assert result["margin"] == "" and result["panel"] == "", result
    # It continued from the mid-slide position (no snap back to either end)...
    assert abs(result["frames"][0] - result["mid"]) < 40, result
    # ...and finished at the expanded layout.
    assert result["left"] > 300, result


def test_a_long_first_frame_does_not_swallow_the_slide():
    """A stall right after the toggle (first raster of a big sidebar, a heavy
    reflow) must not use up the curve: the page would just appear expanded.
    Animation time advances by at most one slow frame per callback."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open(page, "tasks")
            page.evaluate("() => toggleSidebar(true)")
            page.wait_for_selector(".layout.panel-sliding", state="detached", timeout=10000)
            result = page.evaluate("""() => new Promise((resolve) => {
              const main = document.querySelector('.main');
              const start = main.getBoundingClientRect().left;
              toggleSidebar(false);
              const t = performance.now();
              while (performance.now() - t < 400) {}          // a 400ms stall
              requestAnimationFrame(() => requestAnimationFrame(() => {
                const after = main.getBoundingClientRect().left;
                resolve({start, after, sliding: document.querySelector('.layout').classList.contains('panel-sliding')});
              }));
            })""")
        finally:
            browser.close()
    travel = 348 - result["start"]
    assert result["sliding"], result  # still gliding after the stall...
    assert (result["after"] - result["start"]) < 0.6 * travel, result  # ...not already at the end


def test_only_slide_safe_canvases_keep_the_page_on_the_layout_driven_slide():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open(page, "tasks")
            outcome = {}
            for label, wrapper in (("plain", "<div></div>"), ("safe", "<div data-slide-safe></div>")):
                page.evaluate("""(html) => {
                  document.querySelectorAll('#mainTasks .__probe').forEach(e => e.remove());
                  const box = document.createElement('div'); box.className = '__probe'; box.innerHTML = html;
                  box.firstChild.appendChild(document.createElement('canvas'));
                  document.querySelector('#mainTasks').appendChild(box);
                }""", wrapper)
                outcome[label] = page.evaluate("""() => new Promise((resolve) => {
                  const layout = document.querySelector('.layout');
                  toggleSidebar();
                  requestAnimationFrame(() => requestAnimationFrame(() => {
                    resolve(layout.classList.contains('panel-sliding'));
                  }));
                })""")
                page.wait_for_timeout(700)
        finally:
            browser.close()
    assert outcome == {"plain": False, "safe": True}, outcome


def test_work_hub_rail_click_expand_glides_instead_of_stalling():
    """Opening Work Hub also closes the workspace panel (a second slide on the
    other side). That call used to take over the sidebar's in-flight slide, so
    the sidebar's expand sat still for the whole slide and then snapped."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open(page, "notes")
            page.evaluate("() => toggleSidebar(true)")
            page.wait_for_selector(".layout.panel-sliding", state="detached", timeout=10000)
            frames = page.evaluate("""() => new Promise((resolve) => {
              const main = document.querySelector('.main');
              const layout = document.querySelector('.layout');
              const lefts = [main.getBoundingClientRect().left];
              switchPanel('notes', {fromRailClick: true});   // rail click while collapsed
              const tick = () => {
                lefts.push(main.getBoundingClientRect().left);
                if (layout.classList.contains('panel-sliding') || lefts.length < 4) requestAnimationFrame(tick);
                else resolve(lefts);
              };
              requestAnimationFrame(tick);
            })""")
        finally:
            browser.close()
    start, end = frames[0], frames[-1]
    between = [x for x in frames if start + 8 < x < end - 8]
    assert end - start > 200, frames
    assert len(between) >= 5, ("the page should pass through intermediate positions", [round(x) for x in frames])
    assert all(b >= a - 1 for a, b in zip(frames, frames[1:])), [round(x) for x in frames]


def test_two_panels_can_slide_at_once_without_taking_each_other_over():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open(page, "chat")
            page.evaluate("() => toggleSidebar(true)")
            page.wait_for_selector(".layout.panel-sliding", state="detached", timeout=10000)
            state = page.evaluate("""() => new Promise((resolve) => {
              const layout = document.querySelector('.layout');
              toggleSidebar(false);                    // sidebar expands...
              toggleWorkspacePanel(true);              // ...while the workspace panel opens
              const tick = () => {
                if (layout.classList.contains('panel-sliding')) { requestAnimationFrame(tick); return; }
                resolve({sidebarCollapsed: layout.classList.contains('sidebar-collapsed'),
                         panelCollapsed: layout.classList.contains('workspace-panel-collapsed'),
                         left: document.querySelector('.main').style.marginLeft, right: document.querySelector('.main').style.marginRight});
              };
              requestAnimationFrame(tick);
            })""")
        finally:
            browser.close()
    assert state["sidebarCollapsed"] is False, state
    assert state["left"] == "" and state["right"] == "", state
