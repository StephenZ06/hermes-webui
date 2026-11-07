"""Jobs Settings, cards on the pages, side panel rows, Files in its side panel, Skills and Insights, eleventh round.

Room inside a card is ink against the card's edge on a real 2x display. A line of text is measured to its letters,
so a descender may reach a little below the room it is given.
"""

import io

import pytest
from PIL import Image

from tests.test_chat_optical_alignment_browser import _ink, _rect, browser, pytestmark, real_2x  # noqa: F401
from tests.test_job_os_page_polish_browser import seeded  # noqa: F401
from tests.test_jobs_round4_browser import jobs  # noqa: F401
from tests.test_jobs_round7_browser import settings  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved, _panel

SOUL = "# Hermes Agent Persona\n\nYou are a warm mentor and workspace lead.\n\nSecond line."
SKILL = '---\nname: demo\n---\n# Demo skill\n\nBody.\n\n```json\n{"a": 1}\n```\n\nLast line.\n'


def _open(page, name, selector):
    _panel(page, name)
    page.wait_for_selector(selector, timeout=15000)
    page.wait_for_timeout(300)


def _room(page, selector):
    """Room from a card's edge to the ink inside it, border left out."""
    box = _rect(page, selector)
    clip = {"x": box["x"] + 2, "y": box["y"] + 2, "width": box["width"] - 4, "height": box["height"] - 4}
    shot = Image.open(io.BytesIO(page.screenshot(clip=clip))).convert("L")
    ground = shot.getpixel((6, shot.height // 2))
    ink = shot.point(lambda v: 255 if abs(v - ground) >= 28 else 0).crop((4, 4, shot.width - 4, shot.height - 4)).getbbox()
    return {"top": (ink[1] + 4) / 2 + 2, "bottom": (shot.height - ink[3] - 4) / 2 + 2, "left": (ink[0] + 4) / 2 + 2}


def _write_memory(page, section, content):
    page.evaluate("""([section, content]) => fetch('/api/memory/write', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({section, content})})""", [section, content])


def _memory(page, section):
    _open(page, "memory", "#memoryPanel .side-menu-item")
    page.evaluate("() => loadMemory(true)")
    page.wait_for_timeout(500)
    page.click(f"#memoryPanel .side-menu-item:nth-of-type({section})")
    page.wait_for_selector("#memoryDetailBody .detail-card", timeout=10000)
    page.wait_for_timeout(600)


# ── Jobs Settings ───────────────────────────────────────────────────────────

def test_section_icons_are_twenty_pixels(settings):
    out = settings.evaluate("""() => [...document.querySelectorAll('.settings-nav-icon svg')].map(s => s.getBoundingClientRect().width)""")
    assert out and set(out) == {20}, out


def _resume_page(page):
    page.evaluate("() => document.querySelector('[data-job-os-view=settings]').click()")
    page.wait_for_timeout(500)
    page.click(".settings-rail .settings-nav-item:last-of-type")
    page.wait_for_selector("#job-os-settings-resume .set-row-text")
    page.wait_for_timeout(500)


def test_the_master_resume_row_has_the_same_room_above_and_below(settings):
    page = settings
    _resume_page(page)
    card = _rect(page, "#job-os-settings-resume .set-group")
    ink = _ink(page, "#job-os-settings-resume .set-row-text", "text")
    assert abs((ink["top"] - card["y"]) - (card["y"] + card["height"] - ink["bottom"])) <= 1, (ink, card)


def test_the_dot_beside_working_sits_half_a_pixel_higher(settings):
    page = settings
    page.evaluate("() => document.querySelector('[data-job-os-view=settings]').click()")
    page.wait_for_selector(".site-health-row .job-os-pill", timeout=10000)
    page.wait_for_timeout(400)
    top = page.evaluate("() => getComputedStyle(document.querySelector('.site-health-row .job-os-pill'), '::before').top")
    other = page.evaluate("() => getComputedStyle(document.querySelector('#job-os-settings-connections .set-row:not(.site-health-row) .job-os-pill'), '::before').top")
    assert (top, other) == ("0px", "0.5px")


# ── Side panel rows ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,rows", [("agents", "#agentsList .skill-item"), ("skills", "#skillsList .skills-category:first-child .skill-item")])
def test_side_panel_rows_stand_two_pixels_apart(real_2x, name, rows):
    page = real_2x
    _open(page, name, rows)
    gap = page.evaluate("""s => { const [a, b] = [...document.querySelectorAll(s)].map(e => e.getBoundingClientRect()); return b.top - a.bottom; }""", rows)
    assert gap == 2


def test_knowledge_rows_stand_two_pixels_apart(real_2x):
    page = real_2x
    _open(page, "knowledge", "#knowledgeList .skill-item")
    page.evaluate("""() => { _knowledgeItems = [{id: 'fx-a', title: 'A', type: 'note', snippet: ''}, {id: 'fx-b', title: 'B', type: 'note', snippet: ''}]; _knowledgeSearchResults = null; renderKnowledgeItems(); }""")
    page.wait_for_selector("[data-knowledge-id='fx-b']")
    assert page.evaluate("""() => { const [a, b] = [...document.querySelectorAll('#knowledgeList .skill-item')].map(e => e.getBoundingClientRect()); return b.top - a.bottom; }""") == 2


# ── Cards on the pages ──────────────────────────────────────────────────────

def _equal_room(room, *sides):
    values = [room[s] for s in sides]
    assert max(values) - min(values) <= 1.5, room


def test_a_persona_card_has_the_same_room_on_every_side(real_2x):
    page = real_2x
    _open(page, "agents", "#agentsList .skill-item")
    page.click("#agentsList .skill-item:nth-child(1)")
    page.wait_for_selector("#agentDefDetailBody .detail-card")
    page.wait_for_timeout(800)
    room = _room(page, "#agentDefDetailBody .detail-card")
    _equal_room(room, "top", "left")
    assert 16.5 <= room["bottom"] <= 22, room


def test_the_profiles_introduction_stands_evenly_on_the_page(real_2x):
    page = real_2x
    _open(page, "profiles", "#profilesPanel .profile-card")
    page.click("#profilesPanel .profile-card")
    page.wait_for_selector("#profileDetailBody .detail-card")
    page.wait_for_timeout(800)
    edges = page.evaluate("""() => { const c = document.querySelector('#profileDetailBody .detail-card').getBoundingClientRect(), b = document.querySelector('#profileDetailBody').getBoundingClientRect();
      return [c.left - b.left, b.right - c.right, c.top - b.top]; }""")
    assert edges == [24, 24, 24]
    _equal_room(_room(page, "#profileDetailBody .detail-card"), "top", "left")


# ── Personal memory ─────────────────────────────────────────────────────────

def test_my_notes_stand_in_cards_with_even_gaps_and_room_around_add_entry(real_2x):
    page = real_2x
    _write_memory(page, "memory", "First thing\n§\nSecond thing")
    _memory(page, 1)
    out = page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect(), all = s => [...document.querySelectorAll(s)].map(e => e.getBoundingClientRect());
      const [c1, c2] = all('#memoryDetailBody .detail-card'), [e1, e2] = all('.memory-entry-card'), body = r('#memoryDetailBody'), add = r('.memory-entry-add-form button[type=submit]'), field = r('#memEntryAddText');
      return {outer: [c1.top - body.top, c1.left - body.left, body.right - c1.right], cards: c2.top - c1.bottom, entries: e2.top - e1.bottom, above: add.top - field.bottom, below: c2.bottom - add.bottom}; }""")
    assert out["outer"] == [24, 24, 24] and out["cards"] == 16 and out["entries"] == 16, out
    assert abs(out["above"] - out["below"]) <= 1, out


def test_no_corrections_yet_stands_halfway(real_2x):
    page = real_2x
    _memory(page, 1)
    page.click(".memory-entry-tab[data-memory-tab='corrections']")
    page.wait_for_timeout(500)
    out = page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect(); const text = r('.memory-empty');
      return [text.top - r('.memory-entry-tabs').bottom, r('#memoryDetailBody .detail-card').bottom - text.bottom]; }""")
    assert abs(out[0] - out[1]) <= 1, out


def test_the_soul_heading_has_the_same_room_above_it_around_its_rule(real_2x):
    page = real_2x
    _write_memory(page, "soul", SOUL)
    _memory(page, 3)
    out = page.evaluate("""() => { const h = document.querySelector('.memory-content h1'), box = h.getBoundingClientRect(), meta = [...document.querySelectorAll('.memory-detail-mtime')].pop().getBoundingClientRect();
      return {above: box.top - meta.bottom, text_to_rule: parseFloat(getComputedStyle(h).paddingBottom), rule_to_text: h.nextElementSibling.getBoundingClientRect().top - box.bottom}; }""")
    assert out == {"above": 14, "text_to_rule": 14, "rule_to_text": 14}
    _equal_room(_room(page, "#memoryDetailBody .detail-card"), "top", "bottom", "left")


# ── Spaces ──────────────────────────────────────────────────────────────────

def _two_spaces(page):
    _open(page, "workspaces", "#workspacesPanel .ws-row")
    page.evaluate("""() => renderWorkspacesPanel([..._workspaceList.slice(0, 1), {name: 'Second', path: '/fixture/second', availability: 'online'}])""")
    page.wait_for_selector("#workspacesPanel .ws-row:nth-of-type(2)")


def test_a_highlight_slides_between_the_spaces_under_the_pointer(real_2x):
    page = real_2x
    _two_spaces(page)
    tops = []
    for row in page.query_selector_all("#workspacesPanel .ws-row"):
        row.hover()
        page.wait_for_timeout(450)
        pill = page.evaluate("""() => { const p = document.querySelector('#workspacesPanel .mi-hover-pill'); return {top: p.getBoundingClientRect().top, o: getComputedStyle(p).opacity}; }""")
        assert pill["o"] == "1" and abs(pill["top"] - row.bounding_box()["y"]) <= .5
        tops.append(pill["top"])
    assert tops[0] != tops[1]


def test_the_header_buttons_of_spaces_and_skills_share_a_highlight(real_2x):
    page = real_2x
    _open(page, "workspaces", "#panelWorkspaces .panel-head-actions.mi-hover")
    _open(page, "skills", "#panelSkills .panel-head-actions.mi-hover")


def test_the_space_highlight_glides_to_the_row_picked(real_2x):
    page = real_2x
    _open(page, "workspaces", "#workspacesPanel .ws-row")
    page.evaluate("""() => { _workspaceList = [..._workspaceList.slice(0, 1), {name: 'Second', path: '/fixture/second', availability: 'online'}]; renderWorkspacesPanel(_workspaceList); }""")
    page.wait_for_selector("#workspacesPanel .ws-row:nth-of-type(2)")
    page.click("#workspacesPanel .ws-row:nth-of-type(1) .ws-row-info")
    page.wait_for_timeout(1200)
    assert page.evaluate("""() => { document.querySelector('#workspacesPanel .ws-row:nth-of-type(2) .ws-row-info').click(); return !!document.querySelector('.sidebar-highlight-glide'); }""")


def test_a_space_row_and_its_page_card_have_the_same_room_on_every_side(real_2x):
    page = real_2x
    _open(page, "workspaces", "#workspacesPanel .ws-row")
    page.click("#workspacesPanel .ws-row-info")
    page.wait_for_selector("#workspaceDetailBody .detail-card")
    page.mouse.move(900, 900)
    page.wait_for_timeout(500)
    _equal_room(_room(page, "#workspacesPanel .ws-row"), "top", "bottom", "left")
    room = _room(page, "#workspaceDetailBody .detail-card")
    _equal_room(room, "top", "bottom", "left")


# ── Files ───────────────────────────────────────────────────────────────────

def test_the_spaces_stand_in_the_files_side_panel(real_2x):
    page = real_2x
    _open(page, "files", "#filesSidebarHost .files-workspace")
    out = page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
      return {note: !!document.querySelector('.files-sidebar-note'), onPage: document.querySelectorAll('#fileManagerRoot .files-workspaces').length,
        rule: r('.files-toolbar').bottom - r('#panelFiles .panel-head').bottom, left: r('.files-browser').left - r('#fileManagerRoot').left}; }""")
    assert out == {"note": False, "onPage": 0, "rule": 0, "left": 0}, out


def test_picking_a_space_in_the_side_panel_opens_it(real_2x):
    page = real_2x
    page.route("**/api/file-manager/workspaces*", lambda route: route.fulfill(json={"workspaces": [
        {"id": "a", "name": "A", "available": True}, {"id": "b", "name": "B", "available": True}]}))
    page.route("**/api/file-manager/list*", lambda route: route.fulfill(json={"path": ".", "entries": []}))
    _open(page, "files", "#filesSidebarHost [data-workspace-id='b']")
    with page.expect_request(lambda r: "workspace_id=b" in r.url, timeout=8000):
        page.click("#filesSidebarHost [data-workspace-id='b']")
    page.wait_for_selector("#filesSidebarHost [data-workspace-id='b'].is-active")


def test_typing_in_the_filter_keeps_the_field(real_2x):
    page = real_2x
    _open(page, "files", ".files-search input")
    page.click(".files-search input")
    page.keyboard.type("abc")
    assert page.evaluate("() => [document.activeElement.className === '' && document.activeElement.type, document.querySelector('.files-search input').value]") == ["search", "abc"]


def test_the_filter_icon_is_a_magnifier_centred_on_its_field(real_2x):
    page = real_2x
    _open(page, "files", ".files-search svg circle")
    icon, field = _rect(page, ".files-search svg"), _rect(page, ".files-search input")
    assert abs((icon["y"] + icon["height"] / 2) - (field["y"] + field["height"] / 2)) <= 1


def test_files_sits_under_office_in_the_rail_and_the_menu(real_2x):
    order = real_2x.evaluate("""() => ['.rail', '.sidebar-nav'].map(s => [...document.querySelectorAll(s + ' .nav-tab[data-panel]')].map(b => b.dataset.panel))""")
    for tabs in order:
        assert tabs.index("files") == tabs.index("office") + 1, tabs
    assert real_2x.evaluate("""() => document.querySelector('.rail .nav-tab[data-panel=files]').nextElementSibling.dataset.afterPanel""") == "files"


# ── Skills ──────────────────────────────────────────────────────────────────

def _skill(page):
    _open(page, "skills", "#skillsList .skill-item")
    page.click("#skillsList .skill-item")
    page.wait_for_timeout(900)
    page.evaluate("s => _renderSkillDetail('demo', s, {references: ['a.md']})", SKILL)
    page.evaluate("""() => { document.getElementById('skillSecuritySection').outerHTML = '<div id="skillSecuritySection" class="skill-security-section skill-security-safe"><div class="skill-security-header"><span class="skill-security-badge skill-security-badge-safe">Safe</span><span class="skill-security-trust">Builtin</span></div></div>'; }""")
    page.mouse.move(900, 900)
    page.wait_for_timeout(500)


def test_a_skill_page_stands_in_cards(real_2x):
    page = real_2x
    _skill(page)
    gaps = page.evaluate("""() => { const c = [...document.querySelectorAll('#skillDetailBody .main-view-content > *')].map(e => e.getBoundingClientRect()); return c.slice(1).map((b, i) => b.top - c[i].bottom); }""")
    assert len(gaps) == 3 and set(gaps) == {16}, gaps
    for card in (".skill-doc-card", ".skill-linked-files", ".skill-frontmatter"):
        _equal_room(_room(page, f"#skillDetailBody {card}"), "top", "bottom", "left")


def test_the_code_language_bar_joins_its_code(real_2x):
    page = real_2x
    _skill(page)
    out = page.evaluate("""() => { const h = document.querySelector('#skillDetailBody .pre-header'), p = h.nextElementSibling, a = h.getBoundingClientRect(), b = p.getBoundingClientRect();
      return {gap: b.top - a.bottom, same: getComputedStyle(h).backgroundColor === getComputedStyle(p).backgroundColor, edges: a.left === b.left && a.right === b.right, radius: getComputedStyle(p).borderTopLeftRadius}; }""")
    assert out == {"gap": 0, "same": True, "edges": True, "radius": "0px"}, out


def test_safe_and_builtin_read_half_a_pixel_lower(real_2x):
    page = real_2x
    _skill(page)
    undo = "#skillDetailBody .skill-security-badge,#skillDetailBody .skill-security-trust{translate:none!important}"
    assert _moved(page, ".skill-security-trust", "text", undo) == .5
    assert _moved(page, ".skill-security-badge", "text", undo) == .5


def test_the_search_text_and_the_switches_read_half_a_pixel_higher_and_the_names_level_with_them(real_2x):
    page = real_2x
    _open(page, "skills", "#skillsList .skill-item")
    undo = "#panelSkills .skills-search input{padding-top:7px!important;padding-bottom:7px!important}"
    assert _moved(page, "#panelSkills .skills-search input", "text", undo) == -.5
    assert page.evaluate("() => getComputedStyle(document.querySelector('#skillsList .skill-toggle')).translate") == "0px -0.5px"
    toggle = _rect(page, "#skillsList .skill-item .skill-toggle")
    ink = _ink(page, "#skillsList .skill-item .skill-name", "text")
    assert abs((ink["top"] + ink["bottom"]) / 2 - (toggle["y"] + toggle["height"] / 2)) <= .5


def test_the_skill_highlight_glides_to_the_row_picked(real_2x):
    page = real_2x
    _open(page, "skills", "#skillsList .skill-item")
    page.click("#skillsList .skill-item")
    page.wait_for_timeout(1500)
    assert page.evaluate("""() => { document.querySelectorAll('#skillsList .skill-item')[1].click(); return !!document.querySelector('.sidebar-highlight-glide'); }""")


# ── Insights ────────────────────────────────────────────────────────────────

def test_every_insights_card_stands_the_same_distance_apart(real_2x):
    page = real_2x
    _open(page, "insights", "#insightsContent .insights-usage-grid")
    out = page.evaluate("""() => { const box = document.getElementById('insightsContent'), c = [...box.children].map(e => e.getBoundingClientRect());
      const rowGap = s => getComputedStyle(document.querySelector(s)).columnGap;
      return {between: [...new Set(c.slice(1).map((b, i) => b.top - c[i].bottom))], top: c[0].top - box.getBoundingClientRect().top,
        inside: ['.insights-row', '.insights-grid', '.system-health-metrics', '.wiki-status-grid', '.skill-usage-grid'].map(rowGap)}; }""")
    assert out["between"] == [16] and out["top"] == 24 and set(out["inside"]) == {"16px"}, out
