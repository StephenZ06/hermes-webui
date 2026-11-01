"""Laptop-sized windows (a 13" MacBook Air at 1470x956, minus the browser's
own toolbars): the icon rail keeps every page reachable in a short window, the
side panel gives up some width below 1600px, and phone-width Resume Studio
keeps its Skill gaps controls inside the card."""
import json
import urllib.request

import pytest

from tests._pytest_port import BASE

RAIL = """() => { const rail = document.querySelector('.rail');
    const btns = [...rail.querySelectorAll('.rail-btn')].filter(b => b.offsetParent);
    const settings = rail.querySelector('[data-panel="settings"]');
    rail.scrollTop = rail.scrollHeight;
    const s = settings.getBoundingClientRect();
    return {vh: innerHeight, heights: btns.map(b => Math.round(b.getBoundingClientRect().height)),
            lastBottom: Math.max(...btns.map(b => b.getBoundingClientRect().bottom)),
            scrolls: rail.scrollHeight > rail.clientHeight, settingsBottom: s.bottom, settingsHeight: s.height}; }"""


def _open(page, w, h):
    page.set_viewport_size({"width": w, "height": h})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            yield browser.new_page()
        finally:
            browser.close()


@pytest.mark.parametrize("w,h", [(1470, 750), (1366, 768), (1280, 720)])
def test_every_rail_button_fits_a_short_laptop_window(page, w, h):
    _open(page, w, h)
    out = page.evaluate(RAIL)
    assert out["lastBottom"] <= out["vh"], out  # Settings used to sit below the window edge
    assert not out["scrolls"], out
    assert min(out["heights"]) >= 28, out


def test_a_tall_window_keeps_full_size_rail_buttons(page):
    _open(page, 1470, 956)
    out = page.evaluate(RAIL)
    assert set(out["heights"]) == {36}, out


def test_a_window_too_short_for_the_compact_rail_scrolls_it_to_settings(page):
    _open(page, 1280, 600)
    out = page.evaluate(RAIL)
    assert out["scrolls"], out
    assert out["settingsBottom"] <= out["vh"] and out["settingsHeight"] >= 28, out


@pytest.mark.parametrize("w,expected", [(1280, 268), (1470, 283.75), (1600, 300), (1920, 300)])
def test_the_side_panel_narrows_in_laptop_windows(page, w, expected):
    _open(page, w, 900)
    width = page.evaluate("() => document.querySelector('.sidebar').getBoundingClientRect().width")
    assert abs(width - expected) < 0.5, width


def test_office_page_buttons_keep_their_labels_inside_a_narrow_side_panel(page):
    _open(page, 1280, 720)
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_selector(".office-page-nav-btn", timeout=15000)
    out = page.evaluate("() => [...document.querySelectorAll('.office-page-nav-btn')].map(b => [b.textContent.trim(), b.scrollWidth, b.clientWidth])")
    assert out and all(sw <= cw for _, sw, cw in out), out


def test_skill_gaps_controls_stay_inside_their_card_on_a_phone(page):
    req = urllib.request.Request(BASE + "/api/job-os/resume", data=json.dumps(
        {"filename": "cv.md", "text": "Jane Doe\nAnalyst\n" + "SQL and Python reporting. " * 20}).encode(),
        headers={"Content-Type": "application/json", "Origin": BASE})
    urllib.request.urlopen(req, timeout=20).read()
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE + "/#jobs/resume-studio", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_selector(".skill-gaps .gaps-controls .job-os-btn", timeout=15000)
    out = page.evaluate("""() => { const card = document.querySelector('.skill-gaps').getBoundingClientRect();
        return {card: [card.left, card.right], controls: [...document.querySelectorAll('.skill-gaps .gaps-controls > *')].map(e => {
            const r = e.getBoundingClientRect(); return [r.left, r.right]; }), docW: document.documentElement.scrollWidth, vw: innerWidth}; }""")
    assert all(l >= out["card"][0] - 0.5 and r <= out["card"][1] + 0.5 for l, r in out["controls"]), out
    assert out["docW"] <= out["vw"], out


OFFICE_CARDS = """() => { const t = document.querySelector('#officeTasks').getBoundingClientRect();
    const stage = document.querySelector('#officeCanvas').parentElement.getBoundingClientRect();
    return {tasks: [t.left, t.top, t.right, t.bottom], stage: [stage.left, stage.right],
            cards: [...document.querySelectorAll('.office-dept-card')].filter(c => c.offsetParent).map(c => {
                const r = c.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; })}; }"""


def _settled_office(page, w, h, folded=False):
    page.set_viewport_size({"width": w, "height": h})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.evaluate("(f) => localStorage.setItem('hermes-webui-office-tasks-collapsed', f ? '1' : '0')", folded)
    _open(page, w, h)
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_selector("#officeCanvas", state="attached")
    last = None
    for _ in range(90):
        page.wait_for_timeout(1000)
        shot = page.evaluate(OFFICE_CARDS)
        key = [[round(v) for v in c] for c in shot["cards"]]
        if key and key == last:
            return shot
        last = key
    return shot


@pytest.mark.skipif(__import__("os").environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
                    reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1 (WebGL under SwiftShader is slow)")
def test_office_overview_keeps_department_cards_clear_of_task_status():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            page = browser.new_page()
            page.set_default_timeout(240000)
            shots = {size: _settled_office(page, *size) for size in [(1280, 720), (1470, 850), (1920, 1080)]}
            folded = _settled_office(page, 1920, 1080, folded=True)
        finally:
            browser.close()

    def under(shot):
        t = shot["tasks"]
        return [c for c in shot["cards"] if c[2] > t[0] and c[0] < t[2] and c[1] < t[3] and c[3] > t[1]]
    for size, shot in shots.items():
        assert shot["cards"] and not under(shot), (size, shot)
    # Folded to its strip, the card covers no department: the floor stays centred on the stage.
    xs = [c[0] for c in folded["cards"]] + [c[2] for c in folded["cards"]]
    mid = (folded["stage"][0] + folded["stage"][1]) / 2
    assert abs((min(xs) + max(xs)) / 2 - mid) < 24, folded
