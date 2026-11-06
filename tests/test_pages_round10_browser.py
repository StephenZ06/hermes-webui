"""Profiles, Personas, Personal memory and Knowledge: header highlight, side panel highlight, entrance and spacing.

As in the earlier rounds, nudges are ink on a real 2x display with and without the rule being asked for.
"""

import pytest

from tests.test_chat_optical_alignment_browser import _ink, _rect, browser, pytestmark, real_2x  # noqa: F401
from tests.test_office_notes_workhub_nudges_browser import _moved, _panel


def _open(page, name, selector):
    _panel(page, name)
    page.wait_for_selector(selector, timeout=15000)
    page.wait_for_timeout(300)


# ── Header buttons share one highlight ──────────────────────────────────────

def test_the_personas_header_buttons_share_a_highlight_that_slides(real_2x):
    page = real_2x
    _open(page, "agents", "#panelAgents .panel-head-actions button")
    buttons = page.evaluate("() => [...document.querySelectorAll('#panelAgents .panel-head-actions > button')].map(b => b.id || b.getAttribute('aria-label'))")
    assert len(buttons) == 2
    rects = []
    for i in range(2):
        page.hover(f"#panelAgents .panel-head-actions > button:nth-of-type({i + 1})")
        page.wait_for_timeout(500)
        pill = page.evaluate("""() => { const p = document.querySelector('#panelAgents .mi-hover-pill'); const r = p.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height, o: getComputedStyle(p).opacity}; }""")
        button = _rect(page, f"#panelAgents .panel-head-actions > button:nth-of-type({i + 1})")
        assert pill["o"] == "1" and abs(pill["x"] - button["x"]) <= .5 and abs(pill["w"] - button["width"]) <= .5 and abs(pill["h"] - button["height"]) <= .5, (pill, button)
        rects.append(pill["x"])
    assert rects[0] != rects[1]
    page.mouse.move(900, 600)
    page.wait_for_timeout(400)
    assert page.evaluate("() => getComputedStyle(document.querySelector('#panelAgents .mi-hover-pill')).opacity") == "0"
    # While it shows, the button does not light up on its own as well.
    page.hover("#panelAgents .panel-head-actions > button:nth-of-type(1)")
    page.wait_for_timeout(400)
    assert page.evaluate("() => getComputedStyle(document.querySelector('#panelAgents .panel-head-actions > button')).backgroundColor") in ("rgba(0, 0, 0, 0)", "transparent")


# ── Personal memory ─────────────────────────────────────────────────────────

def test_the_memory_sections_share_a_highlight_and_their_titles_read_half_a_pixel_lower(real_2x):
    page = real_2x
    _open(page, "memory", "#memoryPanel .side-menu-item")
    first = "#memoryPanel button:first-of-type"
    assert _moved(page, first, "text", "#memoryPanel .side-menu-item > span{translate:none!important}", within=first) == .5
    page.click("#memoryPanel .side-menu-item:nth-of-type(2)")
    page.wait_for_timeout(700)
    out = page.evaluate("""() => { const p = document.querySelector('#memoryPanel > .mi-pill'); const a = document.querySelector('#memoryPanel .side-menu-item.active');
      return {pill: p.getBoundingClientRect().y, active: a.getBoundingClientRect().y, h: [p.getBoundingClientRect().height, a.getBoundingClientRect().height], bg: getComputedStyle(a).backgroundColor,
        index: [...a.parentElement.querySelectorAll('.side-menu-item')].indexOf(a), o: getComputedStyle(p).opacity}; }""")
    assert out["index"] == 1 and out["o"] == "1" and abs(out["pill"] - out["active"]) <= .5 and abs(out["h"][0] - out["h"][1]) <= .5, out
    assert out["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), out  # the highlight is the pill


def test_the_patterns_and_corrections_underline_slides_while_the_cards_change_in_place(real_2x):
    page = real_2x
    _open(page, "memory", "#memoryPanel .side-menu-item")
    page.click("#memoryPanel .side-menu-item:nth-of-type(1)")
    page.wait_for_selector(".memory-entry-tabs .memory-entry-tab", timeout=10000)
    page.wait_for_timeout(800)
    page.evaluate("() => { document.querySelector('.memory-entry-tabs').dataset.same = '1'; }")
    before = page.evaluate("() => document.querySelector('.memory-entry-tabs > .mi-pill').getBoundingClientRect().x")
    page.click(".memory-entry-tab[data-memory-tab='corrections']")
    page.wait_for_timeout(700)
    out = page.evaluate("""() => { const strip = document.querySelector('.memory-entry-tabs'); const pill = strip.querySelector(':scope > .mi-pill'); const tab = strip.querySelector('.memory-entry-tab.active');
      return {same: strip.dataset.same, pill: pill.getBoundingClientRect().x, tab: tab.getBoundingClientRect().x, which: tab.dataset.memoryTab, selected: tab.getAttribute('aria-selected'),
        empty: document.querySelector('.memory-entry-cards').textContent.trim(), border: getComputedStyle(tab).borderBottomColor}; }""")
    assert out["same"] == "1" and out["which"] == "corrections" and out["selected"] == "true", out
    assert out["pill"] > before and abs(out["pill"] - out["tab"]) <= .5, (before, out)
    assert "correction" in out["empty"].lower(), out
    assert out["border"] in ("rgba(0, 0, 0, 0)", "transparent"), out


# ── Personas side panel ─────────────────────────────────────────────────────

def test_the_persona_dot_and_emoji_read_half_a_pixel_lower(real_2x):
    page = real_2x
    _open(page, "agents", "#agentsList .skill-item .agent-def-emoji")
    assert _moved(page, "#agentsList .skill-item:first-child .agent-def-emoji", "text", "#agentsList .agent-def-emoji{translate:none!important}") == .5
    assert page.evaluate("() => getComputedStyle(document.querySelector('#agentsList .skill-item > span[aria-hidden=\"true\"]')).translate") == "0px 0.5px"


def test_the_persona_highlight_glides_to_the_row_picked(real_2x):
    page = real_2x
    _open(page, "agents", "#agentsList .skill-item")
    page.click("#agentsList .skill-item:nth-child(1)")
    page.wait_for_timeout(1200)
    gliding = page.evaluate("""() => { document.querySelector('#agentsList .skill-item:nth-child(3)').click(); return !!document.querySelector('.sidebar-highlight-glide'); }""")
    assert gliding


# ── Knowledge ───────────────────────────────────────────────────────────────

def test_the_knowledge_icon_reads_a_pixel_lower_and_the_highlight_glides(real_2x):
    page = real_2x
    _open(page, "knowledge", "#knowledgeList .skill-item")
    assert _moved(page, "#knowledgeList .knowledge-item", "icon", "#knowledgeList .knowledge-type-badge{translate:none!important}") == 1
    page.evaluate("""() => { _knowledgeItems = [{id: 'fx-a', title: 'A', type: 'note', snippet: ''}, {id: 'fx-b', title: 'B', type: 'note', snippet: ''}]; _knowledgeSearchResults = null; _currentKnowledgeItemId = null; renderKnowledgeItems(); }""")
    page.click("#knowledgeList [data-knowledge-id='fx-a']")
    page.wait_for_timeout(1200)
    assert page.evaluate("""() => { document.querySelector("#knowledgeList [data-knowledge-id='fx-b']").click(); return !!document.querySelector('.sidebar-highlight-glide'); }""")


# ── Profiles ────────────────────────────────────────────────────────────────

def _profile_page(page):
    _open(page, "profiles", ".profile-card[data-name='default']")
    page.wait_for_selector(".profile-health-banner", timeout=15000)
    page.click(".profile-card[data-name='default']")
    page.wait_for_selector("#mainProfiles .pp-setup", timeout=15000)
    page.wait_for_timeout(1200)


def test_the_needs_setup_banner_is_as_wide_as_the_profile_buttons(real_2x):
    page = real_2x
    _profile_page(page)
    banner, card = _rect(page, ".profile-health-banner"), _rect(page, ".profile-card[data-name='default']")
    assert abs(banner["x"] - card["x"]) <= .5 and abs(banner["width"] - card["width"]) <= .5, (banner, card)
    rule = _rect(page, ".profile-concept-divider")  # the rule above it is as wide as well
    assert abs(rule["x"] - card["x"]) <= .5 and abs(rule["width"] - card["width"]) <= .5, (rule, card)


def test_the_profile_buttons_have_the_same_room_on_every_side_of_the_list(real_2x):
    page = real_2x
    _profile_page(page)
    out = page.evaluate("""() => { const panel = document.getElementById('profilesPanel'); const cs = getComputedStyle(panel); const cards = [...panel.querySelectorAll('.profile-card')]; const last = cards[cards.length - 1];
      const p = panel.getBoundingClientRect(), f = cards[0].getBoundingClientRect(), l = last.getBoundingClientRect();
      return {top: f.top - p.top, left: l.left - p.left, right: p.right - l.right - (panel.offsetWidth - panel.clientWidth), bottom: parseFloat(cs.paddingBottom) + parseFloat(getComputedStyle(last).marginBottom)}; }""")
    for side in ("left", "right", "bottom"):
        assert abs(out[side] - out["top"]) <= .5, out


@pytest.mark.parametrize("name,ready,body", [("profiles", None, "#profileDetailBody"), ("agents", "#agentsList .skill-item", "#agentDefDetailBody")])
def test_the_cards_on_a_page_have_the_same_room_above_below_and_on_both_sides(real_2x, name, ready, body):
    page = real_2x
    if name == "profiles":
        _profile_page(page)
    else:
        _open(page, name, ready)
        page.click("#agentsList .skill-item:nth-child(1)")
        page.wait_for_selector(f"{body} .detail-card", timeout=10000)
        page.wait_for_timeout(1200)
    out = page.evaluate("""body => { const b = document.querySelector(body); const cs = getComputedStyle(b); const content = b.querySelector('.main-view-content'); const cards = [...content.querySelectorAll(':scope > .detail-card')].filter(c => !c.hidden);
      const last = cards[cards.length - 1]; const br = b.getBoundingClientRect(), f = cards[0].getBoundingClientRect(), l = last.getBoundingClientRect(); const head = b.parentElement.querySelector('.main-view-header').getBoundingClientRect();
      return {top: f.top - head.bottom, left: f.left - br.left, right: br.right - l.right - (b.offsetWidth - b.clientWidth), bottom: parseFloat(cs.paddingBottom) + parseFloat(getComputedStyle(content.lastElementChild.hidden ? last : content.lastElementChild).marginBottom)}; }""", body)
    for side in ("left", "right", "bottom"):
        assert abs(out[side] - out["top"]) <= .5, out
    assert out["top"] == 24, out


def test_set_up_a_provider_reads_half_a_pixel_higher_and_sign_in_again_half_a_pixel_lower(real_2x):
    page = real_2x
    _profile_page(page)
    assert _moved(page, "#mainProfiles .pp-setup", "text", "#mainProfiles .pp-card-head .pp-setup{padding:0 12px!important}") == -.5
    sign = "#mainProfiles .pp-signin .pp-row .profile-signin-btn"
    page.eval_on_selector("#mainProfiles .pp-more", "e => { e.open = true; }")
    page.eval_on_selector(sign, "e => e.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(300)
    assert _moved(page, sign, "text", f"#mainProfiles .pp-row .profile-signin-btn{{padding-top:6px!important;padding-bottom:6px!important}}") == .5


# ── Pages arrive the way a knowledge item does ──────────────────────────────

@pytest.mark.parametrize("name,ready,pick,host", [
    ("agents", "#agentsList .skill-item", "#agentsList .skill-item:nth-child(2)", "#mainAgents"),
    ("memory", "#memoryPanel .side-menu-item", "#memoryPanel .side-menu-item:nth-of-type(2)", "#mainMemory"),
    ("profiles", ".profile-card[data-name='default']", ".profile-card[data-name='default']", "#mainProfiles")])
def test_a_page_stands_as_placeholders_then_fades_into_its_text(real_2x, name, ready, pick, host):
    page = real_2x
    _open(page, name, ready)
    state = page.evaluate("""([pick, host]) => { document.querySelector(pick).click(); const h = document.querySelector(host + ' .main-view-body').parentElement; return {skel: h.dataset.skel || '', hidden: document.querySelector(host + ' .main-view-body').getAttribute('data-skel-hide') || ''}; }""", [pick, host])
    assert state == {"skel": "loading", "hidden": "loading"}, state
    page.wait_for_timeout(1500)
    done = page.evaluate("host => ({skel: document.querySelector(host + ' .main-view-body').parentElement.dataset.skel || '', hidden: document.querySelector(host + ' .main-view-body').getAttribute('data-skel-hide') || '', text: document.querySelector(host + ' .main-view-body').textContent.trim().length})", host)
    assert done["skel"] == "" and done["hidden"] == "" and done["text"] > 10, done
