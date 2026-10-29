"""Page switches keep one pace: heavy pages mount after the fade.

Every rail switch fades the side panel and the main view in (page-view-in,
220ms). A page whose mount is heavy (the Office WebGL scene above all) used to
mount in the same task as the click and stall that fade, so Office opened
slower than every other page. Heavy pages now mount once the fade has
finished; their side panel is drawn before it, and a switch away during the
wait never mounts the page it left.
"""
import pytest

from tests._pytest_port import BASE


def _open(pw):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.wait_for_function("() => window.HermesOffice && typeof window.HermesOffice.mount === 'function'", polling=100, timeout=30000)
    return browser, page


# Records when Office mounts and when its side panel is drawn, against the end
# of the page fade that the click started.
_PROBE = """async (leaveEarly) => {
  await switchPanel('chat');
  await new Promise(r => setTimeout(r, 400));
  const O = window.HermesOffice, mount = O.mount, side = O.renderSidebar;
  const log = {mountAt: null, sidebarAt: null, fadeEnd: null};
  O.mount = function () { if (log.mountAt === null) log.mountAt = performance.now(); return mount.apply(this, arguments); };
  O.renderSidebar = function () { if (log.sidebarAt === null) log.sidebarAt = performance.now(); return side.apply(this, arguments); };
  try {
    const t0 = performance.now();
    const switching = switchPanel('office');
    const fades = document.getAnimations().filter(a => a.animationName === 'page-view-in');
    log.fades = fades.length;
    // The fade starts on the click's frame, so it ends one duration later.
    log.fadeEnd = Math.max(...fades.map(a => a.effect.getComputedTiming().endTime));
    if (leaveEarly) await switchPanel('chat');
    await switching;
    await new Promise(r => setTimeout(r, 600));
    log.mountAt = log.mountAt === null ? null : log.mountAt - t0;
    log.sidebarAt = log.sidebarAt === null ? null : log.sidebarAt - t0;
    log.panel = _currentPanel;
  } finally {
    O.mount = mount; O.renderSidebar = side;
  }
  return log;
}"""


def test_office_mounts_after_the_page_fade_with_its_side_panel_drawn_first():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            log = page.evaluate(_PROBE, False)
            assert log["fades"] >= 1
            assert log["mountAt"] is not None
            # Mounted once the fade had run (within a frame of its end).
            assert log["mountAt"] >= log["fadeEnd"] - 20, log
            assert log["sidebarAt"] is not None and log["sidebarAt"] < 20, log
        finally:
            page.evaluate("async () => { await switchPanel('chat'); }")
            browser.close()


def test_leaving_before_the_fade_ends_never_mounts_the_page_left():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            log = page.evaluate(_PROBE, True)
            assert log["panel"] == "chat"
            assert log["mountAt"] is None, log
        finally:
            browser.close()
