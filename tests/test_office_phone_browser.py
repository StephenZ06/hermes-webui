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
    # (as in the live view: no "View live" button until a past moment is being shown)
    page.evaluate("() => { document.querySelector('.office-outlet-btn[data-outlet=projects]').classList.add('is-active'); document.getElementById('officePauseBtn').hidden = true; }")
    page.wait_for_timeout(300)


def test_the_floor_controls_are_compact_and_the_toggle_has_a_flat_middle(phone):
    _with_floor_chrome(phone)
    sizes = phone.evaluate("""() => {
        const box = (el) => { const r = el.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; };
        return {
            labels: [...document.querySelectorAll('.office-header > .office-labels-btn')].map(box),
            outlet: box(document.querySelector('.office-outlet')),
            buttons: [...document.querySelectorAll('.office-outlet-btn')].map((b) => { const c = getComputedStyle(b); return {box: box(b), radius: c.borderRadius, appearance: c.webkitAppearance || c.appearance}; }),
            width: innerWidth,
        };
    }""")
    assert all(b[3] == 30 for b in sizes["labels"]) and all(b[2] <= 34 for b in sizes["labels"]), sizes["labels"]     # the two buttons beside the toggle
    assert sizes["outlet"][3] <= 32, sizes["outlet"]                                                                  # compact in height...
    assert sizes["outlet"][0] + sizes["outlet"][2] >= sizes["width"] - 20, sizes["outlet"]                            # ...and it runs on to the row's edge again

    # They all share a row and a height.
    ys = {b[1] for b in sizes["labels"]} | {sizes["outlet"][1]}
    assert max(ys) - min(ys) <= 2, ys
    # The segments are flat where they meet: no rounding of its own on either (iOS gives a <button> one unless reset).
    assert all(b["radius"] == "0px" for b in sizes["buttons"]), sizes["buttons"]
    # One corner radius across the row: the switch is no rounder than the buttons beside it.
    radii = phone.evaluate("""() => ({
        labels: [...document.querySelectorAll('.office-header > .office-labels-btn')].map((b) => getComputedStyle(b).borderTopLeftRadius),
        outlet: getComputedStyle(document.querySelector('.office-outlet')).borderTopLeftRadius,
        pause: getComputedStyle(document.getElementById('officePauseBtn')).borderTopLeftRadius })""")
    assert set(radii["labels"]) == {radii["outlet"]} == {radii["pause"]}, radii
    assert all(b["appearance"] == "none" for b in sizes["buttons"]), sizes["buttons"]


def test_every_plain_button_on_a_touch_screen_has_no_native_rounding(phone):
    _open_office(phone)
    assert phone.evaluate("""() => { const b = document.createElement('button'); document.body.appendChild(b);
        const c = getComputedStyle(b); const out = [c.webkitAppearance || c.appearance, c.borderRadius]; b.remove(); return out; }""") == ["none", "0px"]
    # ...but a button that sets its own radius keeps it.
    assert phone.evaluate("""() => { const b = document.createElement('button'); b.className = 'office-header-btn'; document.body.appendChild(b);
        const r = getComputedStyle(b).borderRadius; b.remove(); return r; }""") == "8px"


def test_task_status_is_a_bottom_right_pill_that_opens_in_place_with_an_animation(phone):
    _with_floor_chrome(phone)
    phone.evaluate("() => { document.getElementById('officeTasksList').innerHTML = '<div class=\"office-tasks-row\"><button class=\"office-tasks-row-select\"><span class=\"office-tasks-row-body\"><span class=\"office-tasks-row-goal\">A long task title that would, left alone, stretch the card beyond the pill it is shut into</span></span></button></div>'; document.getElementById('officeTasks').classList.add('is-collapsed'); }")
    phone.wait_for_timeout(1900)    # (the card folds, then narrows)
    measure = """() => {
        const tasks = document.getElementById('officeTasks');
        const stage = document.querySelector('.office-stage').getBoundingClientRect(); const r = tasks.getBoundingClientRect();
        return {display: getComputedStyle(tasks).display, w: Math.round(r.width), h: Math.round(r.height), right: Math.round(stage.right - r.right), bottom: Math.round(stage.bottom - r.bottom), left: Math.round(r.left - stage.left), top: Math.round(r.top - stage.top), stage: Math.round(stage.width), stageH: Math.round(stage.height)};
    }"""
    shut = phone.evaluate(measure)
    assert shut["display"] != "none", shut                                            # it exists on a phone now
    assert shut["w"] <= 90 and shut["h"] <= 46, shut                                 # small: icon and count, whatever its list holds
    assert shut["right"] == shut["bottom"] == 10, shut                               # bottom-right, the same gap below as at the side
    phone.evaluate("() => document.getElementById('officeTasks').classList.remove('is-collapsed')")
    phone.wait_for_timeout(150)
    early = phone.evaluate(measure)
    phone.wait_for_timeout(300)           # ~0.45s: the widening is done and the list is already unfolding
    later = phone.evaluate(measure)
    phone.wait_for_timeout(1500)
    open_ = phone.evaluate(measure)
    # Opening flows in one go: it widens to the left, and the list begins to unfold upward as that finishes,
    # with no standing pause in between...
    assert shut["w"] < early["w"] < open_["w"], (shut, early, open_)
    assert early["h"] <= shut["h"] + 6, (shut, early)                                   # (the height has barely begun)
    assert later["w"] >= open_["w"] - 8 and shut["h"] + 6 < later["h"] < open_["h"], (shut, later, open_)
    assert shut["h"] < open_["h"]
    assert "grid-template-rows" in phone.evaluate("() => getComputedStyle(document.getElementById('officeTasksBody')).transitionProperty")
    assert open_["left"] == open_["right"] == open_["bottom"] == 10, open_              # evenly inset, still anchored to the corner
    assert open_["h"] <= open_["stageH"] * 0.66, open_                                  # it leaves the floor in view
    # Closing: the text FADES (it does not vanish) while the list folds, and the card narrows as that finishes.
    phone.evaluate("() => document.getElementById('officeTasks').classList.add('is-collapsed')")
    phone.wait_for_timeout(110)
    fading = phone.evaluate("""() => ({
        list: parseFloat(getComputedStyle(document.querySelector('.office-tasks-body-inner')).opacity),
        title: parseFloat(getComputedStyle(document.querySelector('.office-tasks-title')).opacity)})""")
    assert 0.05 < fading["list"] < 0.95, fading                                         # mid-fade, not gone
    assert 0.05 < fading["title"] < 0.95, fading
    phone.wait_for_timeout(200)
    folding = phone.evaluate(measure)
    assert folding["w"] >= open_["w"] - 8 and folding["h"] < open_["h"], (open_, folding)
    phone.wait_for_timeout(1800)
    closed = phone.evaluate(measure)
    assert closed["w"] <= shut["w"] + 2 and closed["h"] <= shut["h"] + 2, (shut, closed)


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


def _png_rgba(data):
    """Decode a Chromium screenshot (8-bit RGB/RGBA, no interlace) to rows of (r, g, b, a)."""
    import struct
    import zlib
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks, width, height, depth, kind = 8, [], 0, 0, 0, 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            width, height, depth, kind = struct.unpack(">IIBB", body[:10])
        elif tag == b"IDAT":
            chunks.append(body)
        pos += 12 + length
    assert depth == 8 and kind in (2, 6)
    step = 4 if kind == 6 else 3
    raw = zlib.decompress(b"".join(chunks))
    stride, rows, prev = width * step, [], bytearray(width * step)
    for y in range(height):
        base = y * (stride + 1)
        mode, line = raw[base], bytearray(raw[base + 1:base + 1 + stride])
        for i in range(stride):
            a = line[i - step] if i >= step else 0
            b = prev[i]
            c = prev[i - step] if i >= step else 0
            if mode == 1:
                line[i] = (line[i] + a) & 255
            elif mode == 2:
                line[i] = (line[i] + b) & 255
            elif mode == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif mode == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * step:x * step + 3]) for x in range(width)])
        prev = line
    return rows


def test_the_toggle_is_painted_by_the_switch_so_its_middle_is_a_straight_line(phone):
    """No button shape sits at the join, so there is nothing to round: the active half is a straight-edged
    block, and the divider is one straight 1px line, from the top of the switch to its bottom."""
    for active in ("projects", "business"):
        _with_floor_chrome(phone)
        phone.evaluate("(a) => { document.querySelectorAll('.office-outlet-btn').forEach((b) => b.classList.toggle('is-active', b.dataset.outlet === a)); }", active)
        phone.wait_for_timeout(200)
        info = phone.evaluate("""() => {
            const sw = document.querySelector('.office-outlet').getBoundingClientRect();
            const after = getComputedStyle(document.querySelector('.office-outlet'), '::after');
            const buttons = [...document.querySelectorAll('.office-outlet-btn')].map((b) => getComputedStyle(b).backgroundColor);
            return {x: sw.x, y: sw.y, w: sw.width, h: sw.height, after: [after.width, after.height, after.left], buttons};
        }""")
        assert all(b in ("rgba(0, 0, 0, 0)", "transparent") for b in info["buttons"]), info      # the buttons paint nothing
        assert info["after"][0] == "1px"
        shot = phone.screenshot(clip={"x": info["x"] - 2, "y": info["y"] - 2, "width": info["w"] + 4, "height": info["h"] + 4})
        rows = _png_rgba(shot)
        scale = len(rows[0]) / (info["w"] + 4)
        mid = int((2 + info["w"] / 2) * scale)
        top, bottom = int(3 * scale) + 2, int((info["h"] + 1) * scale) - 2   # just inside the switch's own border (a few device pixels of margin)
        near = lambda a, b: all(abs(x - y) <= 4 for x, y in zip(a, b))
        for side in (-int(3 * scale), int(3 * scale)):                       # the active half and the inactive half, beside the divider
            column = [rows[y][mid + side] for y in range(top, bottom)]
            # a straight edge: the colour beside the divider is the same from top to bottom (a rounded inner
            # corner would show the other half's colour in the first and last few pixels)
            assert all(near(px, column[len(column) // 2]) for px in column), (active, side, column[:6], column[-6:])
        divider = [rows[y][mid] for y in range(top, bottom)]
        assert all(near(px, divider[len(divider) // 2]) for px in divider), (active, divider[:3])   # one unbroken line


def test_picking_a_chat_in_the_office_sidebar_puts_the_phone_drawer_away():
    # Both lists of chats (a workspace folder's and the history) fold the drawer, as the Chat page does; a
    # folder row (which only expands) does not.
    assert "setTimeout(window._closeMobileSidebarAfterPanelSelection, 0)" in OFFICE_JS
    history = OFFICE_JS[OFFICE_JS.index("      if (row.dataset.liveEntry) returnToLive();"):]
    assert history[:200].count("foldPhoneSidebar();") == 1
    folders = OFFICE_JS[OFFICE_JS.index("host.querySelectorAll('.office-session-row').forEach(row => {"):]
    assert "row.onclick = () => { showHistory(row.dataset.parentId); foldPhoneSidebar(); };" in folders[:200]
    toggle = OFFICE_JS[OFFICE_JS.index("host.querySelectorAll('.office-project-folder').forEach(row => {"):OFFICE_JS.index("host.querySelectorAll('.office-session-row').forEach(row => {")]
    assert "foldPhoneSidebar" not in toggle


def test_the_real_drawer_closes_when_a_chat_row_is_chosen(phone):
    _open_office(phone)
    phone.wait_for_function("() => typeof window._closeMobileSidebarAfterPanelSelection === 'function' && typeof closeMobileSidebar === 'function'", timeout=15000)
    phone.evaluate("() => document.querySelector('.sidebar').classList.add('mobile-open')")
    assert phone.evaluate("() => document.querySelector('.sidebar').classList.contains('mobile-open')")
    phone.evaluate("() => setTimeout(window._closeMobileSidebarAfterPanelSelection, 0)")   # what the rows now do
    phone.wait_for_function("() => !document.querySelector('.sidebar').classList.contains('mobile-open')", timeout=5000)


def test_the_conductors_label_goes_behind_the_task_status_card(phone):
    _with_floor_chrome(phone)
    phone.evaluate("() => document.getElementById('officeTasks').classList.add('is-collapsed')")
    phone.wait_for_timeout(1500)
    # (elementsFromPoint ignores the pointer-events:none cards, so the paint order is read from a screenshot)
    box = phone.evaluate("""() => {
        const tasks = document.getElementById('officeTasks'), r = tasks.getBoundingClientRect(), host = document.getElementById('officeDeptCards');
        const h = host.getBoundingClientRect();
        // the conductor's card is given an inline z-index of 100 (static/office/index.js); here, a solid magenta slab over the pill
        host.innerHTML = '<div class="office-dept-card" style="z-index:100;min-width:0;width:60px;height:24px;padding:0;background:#ff00ff;border:0;left:' + (r.left - h.left + 40) + 'px;top:' + (r.top - h.top + 30) + 'px"></div>';
        return {x: r.left, y: r.top, w: r.width, h: r.height};
    }""")
    phone.wait_for_timeout(300)
    rows = _png_rgba(phone.screenshot(clip={"x": box["x"], "y": box["y"], "width": box["w"], "height": box["h"]}))
    scale = len(rows[0]) / box["w"]
    mid = rows[int(box["h"] * scale / 2)][int(box["w"] * scale / 2)]
    assert not (mid[0] > 200 and mid[1] < 60 and mid[2] > 200), f"the conductor's label painted over the Task Status card: {mid}"


def test_an_open_task_status_card_has_the_same_gap_below_its_last_task_as_at_the_sides(phone):
    _with_floor_chrome(phone)
    phone.evaluate("""() => {
        document.getElementById('officeTasksList').innerHTML = ['Research the vendor options', 'Draft the summary'].map((g) =>
            '<div class="office-tasks-row"><button class="office-tasks-row-select"><span class="office-tasks-row-status status-running"></span><span class="office-tasks-row-body"><span class="office-tasks-row-goal">' + g + '</span><span class="office-tasks-row-meta">running · 2m</span></span></button></div>').join('');
        document.getElementById('officeTasks').classList.remove('is-collapsed'); }""")
    phone.wait_for_timeout(1500)
    gaps = phone.evaluate("""() => {
        const card = document.getElementById('officeTasks').getBoundingClientRect();
        const rows = [...document.querySelectorAll('.office-tasks-row')], first = rows[0].getBoundingClientRect(), last = rows[rows.length - 1].getBoundingClientRect();
        return {left: first.left - card.left, right: card.right - first.right, below: card.bottom - last.bottom};
    }""")
    assert abs(gaps["below"] - gaps["left"]) <= 1 and abs(gaps["below"] - gaps["right"]) <= 1, gaps
