"""The Office page on a phone: its controls, Task Status, and the dashboard/integrations pages.

The 3D floor needs WebGL, which a test browser may not have, so the floor's own chrome (header, Task Status
card) is checked by putting the real markup (read from static/office/index.js) into the real panel, with
the real stylesheet, at a phone's width. The dashboard and integrations pages need no WebGL and are opened
for real.
"""
import re
from pathlib import Path

import pytest

from tests._pytest_port import BASE

ROOT = Path(__file__).resolve().parent.parent
OFFICE_JS = (ROOT / "static" / "office" / "index.js").read_text(encoding="utf-8")


def _floor_markup():
    start = OFFICE_JS.index('  container.innerHTML = `\n    <div class="office-header">') + len("  container.innerHTML = `")
    end = OFFICE_JS.index("`;\n  _canvas = container.querySelector('#officeCanvas');")
    markup = OFFICE_JS[start:end]
    assert "${" not in markup
    return markup


@pytest.fixture
def phone():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(viewport={"width": 430, "height": 932}, has_touch=True, is_mobile=True, device_scale_factor=2)
            yield context.new_page()
        finally:
            browser.close()


def _open_office(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_selector("#officeWrap", state="attached", timeout=15000)
    page.wait_for_timeout(800)


def _with_floor_chrome(page):
    _open_office(page)
    # (the panel is mounted without WebGL here: replace its message with the real floor markup)
    page.evaluate("(html) => { const w = document.getElementById('officeWrap'); w.innerHTML = html; w.querySelector('#officeCanvas').remove(); }", _floor_markup())
    page.evaluate("() => { document.querySelector('.office-outlet-btn[data-outlet=projects]').classList.add('is-active'); }")
    page.wait_for_timeout(300)


def test_the_floor_controls_are_compact_and_the_toggle_has_a_flat_middle(phone):
    _with_floor_chrome(phone)
    sizes = phone.evaluate("""() => {
        const box = (el) => { const r = el.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; };
        return {
            labels: [...document.querySelectorAll('.office-header > .office-labels-btn')].map(box),
            outlet: box(document.querySelector('.office-outlet')),
            buttons: [...document.querySelectorAll('.office-outlet-btn')].map((b) => { const c = getComputedStyle(b); return {box: box(b), radius: c.borderRadius, appearance: c.webkitAppearance || c.appearance}; }),
            pause: box(document.getElementById('officePauseBtn')),
            width: innerWidth,
        };
    }""")
    assert all(b[3] == 30 for b in sizes["labels"]) and all(b[2] <= 34 for b in sizes["labels"]), sizes["labels"]     # the two buttons beside the toggle
    assert sizes["outlet"][3] <= 32 and sizes["outlet"][2] <= sizes["width"] * 0.55, sizes["outlet"]                  # a compact toggle, not a full-width bar
    assert sizes["pause"][3] == 30, sizes["pause"]
    # They all share a row and a height.
    ys = {b[1] for b in sizes["labels"]} | {sizes["outlet"][1] - 0} | {sizes["pause"][1]}
    assert max(ys) - min(ys) <= 2, ys
    # The segments are flat where they meet: no rounding of its own on either (iOS gives a <button> one unless reset).
    assert all(b["radius"] == "0px" for b in sizes["buttons"]), sizes["buttons"]
    assert all(b["appearance"] == "none" for b in sizes["buttons"]), sizes["buttons"]


def test_every_plain_button_on_a_touch_screen_has_no_native_rounding(phone):
    _open_office(phone)
    assert phone.evaluate("""() => { const b = document.createElement('button'); document.body.appendChild(b);
        const c = getComputedStyle(b); const out = [c.webkitAppearance || c.appearance, c.borderRadius]; b.remove(); return out; }""") == ["none", "0px"]
    # ...but a button that sets its own radius keeps it.
    assert phone.evaluate("""() => { const b = document.createElement('button'); b.className = 'office-header-btn'; document.body.appendChild(b);
        const r = getComputedStyle(b).borderRadius; b.remove(); return r; }""") == "7px"


def test_task_status_is_a_pill_on_a_phone_that_opens_as_a_sheet_along_the_bottom(phone):
    _with_floor_chrome(phone)
    phone.evaluate("() => { document.getElementById('officeTasksList').innerHTML = '<div class=\"office-tasks-row\"><button class=\"office-tasks-row-select\"><span class=\"office-tasks-row-body\"><span class=\"office-tasks-row-goal\">A long task title that would, left alone, stretch the card beyond the pill it is shut into</span></span></button></div>'; document.getElementById('officeTasks').classList.add('is-collapsed'); }")
    phone.wait_for_timeout(900)    # (the card eases shut)
    state = phone.evaluate("""() => {
        const tasks = document.getElementById('officeTasks');
        const stage = document.querySelector('.office-stage').getBoundingClientRect();
        const r = tasks.getBoundingClientRect();
        return {display: getComputedStyle(tasks).display, pill: [Math.round(r.width), Math.round(r.height)], right: Math.round(stage.right - r.right), top: Math.round(r.top - stage.top), title: getComputedStyle(document.querySelector('.office-tasks-title')).display};
    }""")
    assert state["display"] != "none", state                                    # it exists on a phone now
    assert state["pill"][0] <= 90 and state["pill"][1] <= 46, state              # small: icon and count, whatever its list holds
    assert state["title"] == "none" and state["right"] <= 12 and state["top"] <= 12, state
    phone.evaluate("() => document.getElementById('officeTasks').classList.remove('is-collapsed')")
    phone.wait_for_timeout(900)
    open_state = phone.evaluate("""() => {
        const tasks = document.getElementById('officeTasks');
        const stage = document.querySelector('.office-stage').getBoundingClientRect(); const r = tasks.getBoundingClientRect();
        return {left: Math.round(r.left - stage.left), right: Math.round(stage.right - r.right), bottom: Math.round(stage.bottom - r.bottom), width: Math.round(r.width), stage: Math.round(stage.width), height: Math.round(r.height), stageHeight: Math.round(stage.height)};
    }""")
    assert open_state["left"] == open_state["right"] == 10 and open_state["bottom"] <= 14, open_state         # a sheet, evenly inset, at the bottom
    assert open_state["height"] <= open_state["stageHeight"] * 0.66, open_state                               # it leaves the floor in view


def test_task_status_starts_collapsed_on_a_phone():
    assert "return stored === null ? phone : stored === '1';" in OFFICE_JS
    assert "if (window.matchMedia && window.matchMedia('(max-width: 640px)').matches) return 0;" in OFFICE_JS     # no column to keep a desk clear of


def test_the_back_button_on_the_dashboard_and_integrations_pages_is_compact(phone):
    _open_office(phone)
    phone.wait_for_function("() => typeof window.officeSetSubview === 'function'", timeout=30000)
    for page_name in ("dashboard", "integrations"):
        phone.evaluate("(name) => window.officeSetSubview(name)", page_name)
        phone.wait_for_selector(".office-subview-back", timeout=15000)
        phone.wait_for_timeout(500)
        size = phone.evaluate("() => { const r = document.querySelector('.office-subview-back').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }")
        assert size[0] <= 32 and size[1] <= 32, (page_name, size)
    # ...and an integration card hugs its content instead of keeping the desktop's tall minimum.
    card = phone.evaluate("() => document.querySelector('.office-integration-card').getBoundingClientRect().height")
    assert card < 200, card


def test_the_integrations_note_has_the_same_space_above_its_title_as_below_its_sentence(phone):
    _open_office(phone)
    phone.wait_for_function("() => typeof window.officeSetSubview === 'function'", timeout=30000)
    for width in (430, 1200):
        phone.set_viewport_size({"width": width, "height": 900})
        phone.evaluate("() => window.officeSetSubview('integrations')")
        phone.wait_for_selector(".office-integrations-intro", timeout=15000)
        phone.wait_for_timeout(400)
        gaps = phone.evaluate("""() => {
            const box = document.querySelector('.office-integrations-intro').getBoundingClientRect();
            const title = document.querySelector('.office-integrations-intro span'), sentence = document.querySelector('.office-integrations-intro p');
            // the ink: capital letters sit ~1.4px inside a 10px line box; the sentence's last line ends ~5px (half-leading and descender) above its box
            const range = document.createRange(); range.selectNodeContents(sentence); const lines = range.getClientRects(); const last = lines[lines.length - 1];
            const sentenceFont = parseFloat(getComputedStyle(sentence).fontSize), lineHeight = parseFloat(getComputedStyle(sentence).lineHeight);
            const above = title.getBoundingClientRect().top - box.top + 1.4;
            const below = box.bottom - last.bottom + (lineHeight - sentenceFont) / 2 + sentenceFont * 0.2;
            return {above, below};
        }""")
        assert abs(gaps["above"] - gaps["below"]) <= 3, (width, gaps)
