"""Notes and Office alignment: the Obsidian icon, the note's place picker with
its sectioned list, and the Office side panel, header, task rows and floor cards."""
import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE

READY = "() => typeof S !== 'undefined' && S._bootReady === true"
TOP = "(s) => getComputedStyle(document.querySelector(s)).top"
# Text snaps to whole pixels unless it has its own layer, so a half pixel needs both.
HALF_PIXEL = """(s) => { const c = getComputedStyle(document.querySelector(s));
  return {top: c.top, translate: c.translate, layer: c.willChange}; }"""


def _api(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_context(viewport={"width": 1899, "height": 990}).new_page()
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function(READY, polling=100, timeout=30000)
        page.evaluate("""() => { document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove());
          document.documentElement.dataset.skin = 'zeus-2'; document.documentElement.classList.add('dark'); }""")
        yield page
        browser.close()


def _notes_with_a_note(page):
    _api("/api/projects/create", {"name": f"Align {uuid.uuid4().hex[:4]}", "color": "#5fbf9f"})
    _api("/api/notebook/folders/create", {"name": f"Align {uuid.uuid4().hex[:4]}"})
    note = _api("/api/notebook/notes/create", {"title": "Align"})["note"]
    page.evaluate("async () => { await switchPanel('notebook'); }")
    page.wait_for_selector("#notebookSidebar .nb-nav", timeout=15000)
    return note


def _open_note(page):
    page.click(".nb-item")
    page.wait_for_selector(".nb-place-select .themed-select-trigger", state="visible", timeout=15000)


def _office(page):
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_selector("#officePauseBtn", state="attached", timeout=15000)


SECTION_GAPS = """(label) => [...document.querySelectorAll(label)].map(el => {
  const box = el.getBoundingClientRect(), before = el.previousElementSibling.getBoundingClientRect(), after = el.nextElementSibling.getBoundingClientRect();
  const c = getComputedStyle(el), line = getComputedStyle(el, '::before'), tail = getComputedStyle(el, '::after');
  return {above: box.top - before.bottom, below: after.top - box.bottom, display: c.display, lines: [line.content, tail.content], widths: [line.width, tail.width]};
})"""


def _assert_sections(sections):
    assert len(sections) == 2
    for section in sections:
        assert section["display"] == "flex"
        assert section["lines"] == ['""', '""'], "the label sits between two divider lines"
        assert section["widths"][0] == section["widths"][1], "the label is centred"
        assert abs(section["above"] - section["below"]) < 0.1 and section["above"] > 0


def test_obsidian_notes_icon_drops_to_its_resting_line(page):
    _notes_with_a_note(page)
    assert page.evaluate(TOP, ".nb-obsidian-scope svg") == "0px"


def test_place_picker_label_lifts_and_its_list_has_centred_divided_sections(page):
    _notes_with_a_note(page)
    _open_note(page)
    label = page.evaluate(HALF_PIXEL, ".nb-place-select .themed-select-trigger-label")
    assert label == {"top": "auto", "translate": "0px -0.5px", "layer": "transform"}
    page.click(".nb-place-select .themed-select-trigger")
    page.wait_for_selector(".themed-select-popup .themed-select-group-label")
    _assert_sections(page.evaluate(SECTION_GAPS, ".themed-select-popup .themed-select-group-label"))


def test_place_picker_rows_show_each_place_colour(page):
    _notes_with_a_note(page)
    _open_note(page)
    project = _api("/api/notebook/bootstrap")["projects"][-1]
    page.click(".nb-place-select .themed-select-trigger")
    page.wait_for_selector(".themed-select-popup .themed-select-option .color-dot")
    rows = page.evaluate("""() => [...document.querySelectorAll('.themed-select-popup .themed-select-option')].map(row => {
      const dot = row.querySelector('.color-dot'), box = row.getBoundingClientRect(), mark = dot.getBoundingClientRect();
      return {name: row.textContent, colour: dot.style.background, gaps: [mark.top - box.top, box.bottom - mark.bottom], round: getComputedStyle(dot).borderRadius, size: mark.width}; })""")
    assert rows[0]["name"] == "General"
    match = next(row for row in rows if row["name"] == project["name"])
    assert page.evaluate("""(c) => { const a = document.createElement('i'), b = document.createElement('i'); a.style.color = c[0]; b.style.color = c[1];
      document.body.append(a, b); const same = getComputedStyle(a).color === getComputedStyle(b).color; a.remove(); b.remove(); return same; }""", [match["colour"], project["color"]])
    for row in rows:
        assert row["size"] == 7 and row["round"] == "50%" and abs(row["gaps"][0] - row["gaps"][1]) <= 0.5


def test_new_note_place_list_matches_the_picker(page):
    _notes_with_a_note(page)
    page.click("#notebookSidebar .nb-create-row .work-hub-project-create")
    page.click(".nb-create-menu [data-nb-create=note]")
    page.wait_for_selector(".nb-create-menu.is-picking .nb-pick-label")
    _assert_sections(page.evaluate(SECTION_GAPS, ".nb-create-menu .nb-pick-label"))


def test_other_selects_keep_their_plain_group_labels(page):
    state = page.evaluate("""() => { const p = document.createElement('div'); p.className = 'themed-select-popup';
      p.innerHTML = '<div class="themed-select-group-label">Group</div>'; document.body.appendChild(p);
      return getComputedStyle(p.firstChild).display; }""")
    assert state == "block"


def test_office_nav_icons_sit_one_pixel_low(page):
    _office(page)
    page.wait_for_selector(".office-page-nav-image", state="visible", timeout=8000)
    assert page.evaluate("""() => [...document.querySelectorAll('.office-page-nav-image')].map(i => getComputedStyle(i).top)""") == ["0.5px", "0.5px"]


def test_history_text_sits_half_a_pixel_low_and_folder_titles_a_pixel_low(page):
    _office(page)
    state = page.evaluate("""() => { const row = '<button class="office-session-row"><span class="office-session-text"><span class="office-session-title">T</span><span class="office-session-meta">M</span></span></button>';
      const history = document.getElementById('officeSessionList'), folders = document.getElementById('officeProjectFolders');
      history.insertAdjacentHTML('beforeend', row); folders.insertAdjacentHTML('beforeend', row);
      const top = (host, s) => getComputedStyle(host.querySelector('.office-session-row:last-child ' + s)).top;
      return [top(history, '.office-session-title'), top(history, '.office-session-meta'), top(folders, '.office-session-title')]; }""")
    assert state == ["0.5px", "-0.5px", "0px"]


def test_view_live_text_matches_the_idle_pill_in_bold(page):
    _office(page)
    state = page.evaluate("""() => ['#officePauseBtn', '#officePill'].map(s => { const c = getComputedStyle(document.querySelector(s));
      return [c.fontSize, c.fontWeight, c.letterSpacing]; })""")
    assert state[0] == state[1] == ["10px", "700", "0.8px"]


def test_view_live_text_lifts_half_a_pixel_without_its_button(page):
    _office(page)
    state = page.evaluate("""() => { const b = document.getElementById('officePauseBtn'), label = b.querySelector('span'), c = label && getComputedStyle(label);
      return [b.textContent, getComputedStyle(b).translate, c && c.translate, c && c.willChange]; }""")
    assert state == ["View live", "none", "0px -0.5px", "transform"]


def test_task_status_icon_drops_half_a_pixel(page):
    _office(page)
    assert page.evaluate("() => getComputedStyle(document.querySelector('.office-tasks-title-icon')).translate") == "0px 0.5px"


def test_floor_plan_toggle_text_drops_one_pixel(page):
    _office(page)
    assert page.evaluate("() => getComputedStyle(document.querySelector('.office-header .office-outlet-btn')).paddingBottom") == "0px"


def test_task_row_status_dot_has_equal_space_above_and_below(page):
    _office(page)
    gaps = page.evaluate("""() => { const host = document.createElement('div'); host.className = 'office-tasks-row';
      host.innerHTML = '<button class="office-tasks-row-select"><span class="office-tasks-row-status status-done"></span><span class="office-tasks-row-body"><span class="office-tasks-row-goal">Goal</span><span class="office-tasks-row-meta">done</span></span></button>';
      document.getElementById('mainOffice').appendChild(host);
      const row = host.querySelector('.office-tasks-row-select').getBoundingClientRect(), dot = host.querySelector('.office-tasks-row-status').getBoundingClientRect();
      return [dot.top - row.top, row.bottom - dot.bottom]; }""")
    assert abs(gaps[0] - gaps[1]) <= 0.5


def test_floor_card_stat_text_lifts_without_its_dot(page):
    _office(page)
    page.wait_for_selector(".office-dept-card-stat", state="attached", timeout=15000)
    state = page.evaluate("""() => { const stat = document.querySelector('.office-dept-card-stat');
      return [getComputedStyle(stat).top, getComputedStyle(stat, '::before').top]; }""")
    assert state == ["-1px", "1px"]
