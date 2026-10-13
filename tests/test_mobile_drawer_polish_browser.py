"""Phone polish: drawer gestures, floating icon bar, toast placement, mic
permission reuse, reload restoring the page, Work Hub list scrolling."""

import json
import time
import urllib.request

import pytest

from tests._pytest_port import BASE

PHONE = {"viewport": {"width": 430, "height": 873}, "is_mobile": True, "has_touch": True}


def _boot(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")


def _touch(cdp, kind, x, y):
    cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y}]})


def _swipe(page, cdp, x0, x1, y=450, probe=None):
    _touch(cdp, "touchStart", x0, y)
    step = 4 if x1 > x0 else -4
    seen = None
    for x in range(x0 + step, x1, step):
        _touch(cdp, "touchMove", x, y)
        if probe and seen is None and abs(x - x0) > 20:
            seen = page.evaluate(probe)
    _touch(cdp, "touchEnd", x1, y)
    time.sleep(0.5)
    return seen


@pytest.fixture()
def phone():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            ctx = browser.new_context(**PHONE)
            page = ctx.new_page()
            yield page, ctx.new_cdp_session(page)
        finally:
            browser.close()


def test_drawer_swipes_own_the_finger_and_the_icon_bar_folds_on_a_short_flick(phone):
    page, cdp = phone
    _boot(page)
    state = "() => _mobileDrawerState()"
    lock = "() => [document.documentElement.classList.contains('drawer-gesture'), getComputedStyle(document.querySelector('main.main')).pointerEvents]"
    assert _swipe(page, cdp, 10, 90, probe=lock) == [True, "none"]
    assert page.evaluate(state) == "icons"
    assert page.evaluate("() => document.documentElement.classList.contains('drawer-gesture')") is False
    # The bar is ~60px wide: a 30px flick that starts on it folds it away.
    _swipe(page, cdp, 40, 10)
    assert page.evaluate(state) == "closed"
    _swipe(page, cdp, 10, 90)
    _swipe(page, cdp, 30, 140)
    assert page.evaluate(state) == "open"
    panel_lock = "() => getComputedStyle(document.querySelector('.sidebar .panel-view.active') || document.querySelector('.sidebar .panel-view')).pointerEvents"
    assert _swipe(page, cdp, 300, 180, y=500, probe=panel_lock) == "none"
    assert page.evaluate(state) == "closed"


def test_open_drawer_edge_zone_blocks_swipe_back_even_between_icons(phone):
    page, _ = phone
    _boot(page)
    page.evaluate("() => _setMobileDrawerState(document.querySelector('.sidebar'), 'open')")
    time.sleep(0.4)
    prevented = page.evaluate("""() => { const div = document.querySelector('.sidebar > .sidebar-nav .sidebar-nav-divider');
        const r = div.getBoundingClientRect();
        const ev = new TouchEvent('touchstart', {bubbles: true, cancelable: true,
          touches: [new Touch({identifier: 1, target: div, clientX: 12, clientY: r.top + 1})]});
        div.dispatchEvent(ev); return ev.defaultPrevented; }""")
    assert prevented is True


def test_icon_bar_floats_and_fits_without_scrolling(phone):
    page, _ = phone
    _boot(page)
    page.evaluate("() => _setMobileDrawerState(document.querySelector('.sidebar'), 'icons')")
    time.sleep(0.6)
    nav = page.evaluate("""() => { const n = document.querySelector('.sidebar > .sidebar-nav'); const s = getComputedStyle(n);
        return {left: n.getBoundingClientRect().left, radius: parseFloat(s.borderTopLeftRadius), fits: n.scrollHeight <= n.clientHeight,
                sidebarBg: getComputedStyle(document.querySelector('.sidebar')).backgroundColor}; }""")
    assert nav["left"] >= 8 and nav["radius"] >= 12 and nav["fits"]
    assert nav["sidebarBg"] == "rgba(0, 0, 0, 0)"


def test_phone_toast_sits_below_the_top_bar(phone):
    page, _ = phone
    _boot(page)
    page.evaluate("() => showToast('Hello')")
    time.sleep(0.6)
    top, bar = page.evaluate("() => [document.getElementById('toast').getBoundingClientRect().top, document.querySelector('.app-titlebar').getBoundingClientRect().bottom]")
    assert top >= bar


def test_reload_keeps_the_page_when_a_stale_conversation_is_cleared(phone):
    page, _ = phone
    _boot(page)
    page.evaluate("async () => { await switchPanel('office'); }")
    time.sleep(1)
    page.evaluate("() => localStorage.setItem('hermes-webui-session', 'deadbeef0000')")
    page.evaluate("() => location.reload()")
    page.wait_for_load_state()
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.wait_for_function("() => _currentPanel === 'office'", timeout=15000)
    assert page.evaluate("() => location.hash") == "#office"


def test_work_hub_list_view_scrolls_on_a_phone(phone):
    page, cdp = phone
    boot = json.loads(urllib.request.urlopen(BASE + "/api/work_hub/bootstrap", timeout=10).read())
    rev = boot.get("revision")
    for i in range(24):
        req = urllib.request.Request(BASE + "/api/work_hub/items/create", method="POST",
                                     data=json.dumps({"item": {"title": f"Scroll {i}", "status": "triage"}, "expected_revision": rev}).encode(),
                                     headers={"Content-Type": "application/json"})
        rev = json.loads(urllib.request.urlopen(req, timeout=10).read()).get("revision", rev)
    _boot(page)
    page.evaluate("async () => { await switchPanel('notes'); }")
    time.sleep(1.5)
    page.evaluate("() => document.querySelector('[data-view=\"list\"]').click()")
    time.sleep(1)
    before = page.evaluate("() => document.getElementById('workHubCanvas').scrollTop")
    _touch(cdp, "touchStart", 215, 650)
    for y in range(640, 250, -15):
        _touch(cdp, "touchMove", 215, y)
    _touch(cdp, "touchEnd", 215, 250)
    time.sleep(0.6)
    assert page.evaluate("() => document.getElementById('workHubCanvas').scrollTop") > before


def test_mic_asks_for_the_microphone_once_per_page_on_a_phone():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage",
                                           "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        try:
            page = browser.new_context(permissions=["microphone"], **PHONE).new_page()
            page.add_init_script("""localStorage.setItem('mic_force_mediarecorder', '1');
              window.__gum = 0; const o = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
              navigator.mediaDevices.getUserMedia = (c) => { window.__gum++; return o(c); };""")
            _boot(page)
            for _ in range(2):
                page.evaluate("() => document.getElementById('btnMic').click()")
                page.wait_for_function("() => !!window._micActive", timeout=10000)
                page.evaluate("() => document.getElementById('btnMic').click()")
                page.wait_for_function("() => !window._micActive", timeout=10000)
            assert page.evaluate("() => window.__gum") == 1
        finally:
            browser.close()


def test_icon_bar_reveal_never_shows_the_panel_and_hide_slides_out(phone):
    page, _ = phone
    _boot(page)
    seen = page.evaluate("""() => new Promise(res => { const sb = document.querySelector('.sidebar');
        const pv = [...sb.querySelectorAll('.panel-view')].find(p => getComputedStyle(p).display !== 'none');
        _setMobileDrawerState(sb, 'icons'); const out = []; const t0 = performance.now();
        (function f() { out.push(getComputedStyle(pv).visibility); if (performance.now() - t0 < 450) requestAnimationFrame(f); else res([...new Set(out)]); })(); })""")
    assert seen == ["hidden"]
    frames = page.evaluate("""() => new Promise(res => { const sb = document.querySelector('.sidebar'); const nav = sb.querySelector('.sidebar-nav');
        closeMobileSidebar(); const out = []; const t0 = performance.now();
        (function f() { out.push([nav.getBoundingClientRect().left, getComputedStyle(nav).borderTopLeftRadius]);
          if (performance.now() - t0 < 300) requestAnimationFrame(f); else res(out); })(); })""")
    lefts = [f[0] for f in frames]
    # Slides through intermediate positions, keeping the bar's rounded look.
    assert any(-60 < x < 8 for x in lefts) and lefts[-1] < -50
    assert frames[1][1] == "15px"


def test_icon_bar_corners_are_concentric_with_its_buttons(phone):
    page, _ = phone
    _boot(page)
    page.evaluate("() => _setMobileDrawerState(document.querySelector('.sidebar'), 'icons')")
    time.sleep(0.6)
    radius, btn, inset = page.evaluate("""() => { const n = document.querySelector('.sidebar > .sidebar-nav'); const t = n.querySelector('.nav-tab');
        return [parseFloat(getComputedStyle(n).borderTopLeftRadius), parseFloat(getComputedStyle(t).borderTopLeftRadius),
                t.getBoundingClientRect().left - n.getBoundingClientRect().left]; }""")
    assert abs(radius - (btn + inset)) <= 1


def test_phone_body_matches_the_top_bar_so_the_status_bar_has_no_band(phone):
    page, _ = phone
    _boot(page)
    body, bar = page.evaluate("() => [getComputedStyle(document.body).backgroundColor, getComputedStyle(document.querySelector('.app-titlebar')).backgroundColor]")
    assert body == bar


def test_left_swipe_on_a_chat_row_closes_the_drawer_and_never_deletes(phone):
    page, cdp = phone
    body = {"title": "Keep me", "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]}
    req = urllib.request.Request(BASE + "/api/session/import", method="POST", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    sid = json.loads(urllib.request.urlopen(req, timeout=10).read())["session"]["session_id"]
    _boot(page)
    page.wait_for_function("(sid) => !!document.querySelector('.session-item[data-session-id=\"' + sid + '\"]') || !!document.querySelector('.session-item')", arg=sid, timeout=15000)
    page.evaluate("() => _setMobileDrawerState(document.querySelector('.sidebar'), 'open')")
    time.sleep(0.6)
    row = page.evaluate("""(sid) => { const r = document.querySelector('.session-item[data-session-id="' + sid + '"]') || document.querySelector('.session-item');
        if (!r) return null; const b = r.getBoundingClientRect(); return [b.left + b.width * 0.7, b.top + b.height / 2]; }""", sid)
    if row is None:
        pytest.skip("no session row rendered in this state")
    x, y = int(row[0]), int(row[1])
    _swipe(page, cdp, x, x - 140, y=y)
    assert page.evaluate("() => _mobileDrawerState()") == "closed"
    gone = page.evaluate("(sid) => fetch('/api/session?session_id=' + sid).then(r => r.status)", sid)
    assert gone != 404
