"""Chat, Notes, Office and Scheduled jobs, third round: nudges, spacing and motion.

Nudges are ink read on a real 2x display with and without the rule being asked for.
Spacing is read as boxes or ink against the card edge. Motion is read as what the page does
over time, not as a stylesheet declaration.
"""

import uuid

import pytest

from tests._pytest_port import BASE
from tests.test_chat_optical_alignment_browser import (  # noqa: F401
    MACBOOK, _ink, _open, _rect, browser, pytestmark, real_2x,
)
from tests.test_chat_menus_fork_browser import _configured_picker
from tests.test_office_notes_workhub_nudges_browser import _moved, _panel, _post, _row


# ── Chat ────────────────────────────────────────────────────────────────────

def test_files_suggestion_icon_sits_another_half_pixel_lower(real_2x):
    selector = ".suggestion-grid > .suggestion:nth-child(1)"
    assert _moved(real_2x, selector, "icon", f"{selector} > svg{{translate:0 1px!important}}") == .5
    other = ".suggestion-grid > .suggestion:nth-child(2)"
    assert _moved(real_2x, other, "icon", f"{other} > svg{{translate:0 1px!important}}") == 0


def test_configured_model_bubble_has_as_much_room_below_as_above(browser):
    context, page = _open(browser, MACBOOK)
    try:
        _configured_picker(page)
        gaps = page.evaluate("""() => {
          const row = [...document.querySelectorAll('#composerModelDropdown .model-opt')]
            .find(r => r.querySelector('.model-opt-name').textContent === 'gpt-5.6-terra');
          const bubble = row.querySelector('.model-opt-badge').getBoundingClientRect(), box = row.getBoundingClientRect();
          return {above: bubble.top - box.top, below: box.bottom - bubble.bottom, hasId: !!row.querySelector('.model-opt-id')};
        }""")
        assert gaps["hasId"] is False
        # the pill and its name sit half a pixel lower in the row (9.5 above, 8.5 below); the row keeps its height
        assert (gaps["above"], gaps["below"]) == (9.5, 8.5), gaps
    finally:
        context.close()


def test_rows_that_keep_an_id_line_keep_their_spacing(browser):
    context, page = _open(browser, MACBOOK)
    try:
        _configured_picker(page)
        bottoms = page.evaluate("""() => [...document.querySelectorAll('#composerModelDropdown .model-opt')]
          .filter(r => r.querySelector('.model-opt-id')).map(r => getComputedStyle(r).paddingBottom)""")
        assert bottoms and set(bottoms) == {"11px"}
    finally:
        context.close()


# ── Plan goal ───────────────────────────────────────────────────────────────

def _plan_dialog(page):
    _panel(page, "notes")
    page.evaluate("() => window.openGoalPlannerDialog({projectId: null})")
    page.wait_for_selector(".goal-planner-dialog")
    page.wait_for_timeout(500)


def test_plan_goal_scope_card_has_equal_room_above_and_below(real_2x):
    page = real_2x
    _plan_dialog(page)
    card, tag = _rect(page, ".goal-planner-scope"), _rect(page, ".goal-planner-scope .tag")
    small = _ink(page, ".goal-planner-scope small", "text", within=".goal-planner-scope")
    above = tag["y"] - card["y"]
    below = card["y"] + card["height"] - small["bottom"]
    assert abs(above - below) <= .5, (above, below)


def test_plan_button_and_tick_share_one_background_in_every_shared_state(real_2x):
    page = real_2x
    _plan_dialog(page)
    page.evaluate("() => { document.getElementById('goalPlannerSave').disabled = false; }")
    colour = "e => { const s = getComputedStyle(e); return [s.backgroundColor, s.borderTopColor, s.color]; }"
    for state in ("rest", "hover", "focus"):
        page.mouse.move(5, 5)
        seen = []
        for selector in ("#goalPlannerBtn", "#goalPlannerSave"):
            if state == "hover":
                page.hover(selector)
            if state == "focus":
                page.focus(selector)
            page.wait_for_timeout(200)
            seen.append(page.eval_on_selector(selector, colour))
            page.mouse.move(5, 5)
        assert seen[0] == seen[1], (state, seen)


# ── Notes ───────────────────────────────────────────────────────────────────

def test_pinned_and_favorites_text_sit_half_a_pixel_higher_but_general_stays(real_2x):
    page = real_2x
    _panel(page, "notebook")
    label = " > span:not(.nb-scope-count)"
    undo = f".nb-nav:not(.nb-nav-vault) .nb-scope{label}{{top:0!important}}"
    for scope, moved in (("pinned", -.5), ("favorites", -.5), ("general", 0)):
        selector = f"#notebookSidebar [data-nb-scope='{scope}']"
        assert _moved(page, selector + label, "text", undo, within=selector) == moved, scope


def test_note_titles_in_folders_sit_a_pixel_higher_than_before(real_2x):
    page = real_2x
    _panel(page, "notebook")
    _row(page, "#notebookSidebar .nb-nav", '<div class="work-hub-board-row nb-tree-note" id="fxNote"><button type="button"><span>HEHE</span></button></div>')
    assert _moved(page, "#fxNote span", "text", "#fxNote span{position:relative;top:1px!important}", within="#fxNote") == -1


def test_trash_icon_sits_a_pixel_lower(real_2x):
    page = real_2x
    _panel(page, "notebook")
    selector = "#notebookSidebar .nb-trash-scope"
    assert _moved(page, selector, "icon", f"{selector} > svg{{translate:none!important}}") == 1


# ── Office ──────────────────────────────────────────────────────────────────

def test_office_page_icons_sit_a_pixel_below_centre(real_2x):
    page = real_2x
    _panel(page, "office")
    page.wait_for_selector(".office-page-nav-image", state="visible")
    for view in ("dashboard", "integrations"):
        selector = f"[data-office-subview='{view}'] .office-page-nav-image"
        now = page.eval_on_selector(selector, "e => e.getBoundingClientRect().top")
        handle = page.add_style_tag(content=".office-page-nav-image{top:0!important}")
        page.wait_for_timeout(150)
        before = page.eval_on_selector(selector, "e => e.getBoundingClientRect().top")
        handle.evaluate("e => e.remove()")
        assert now - before == 1, (view, now, before)


def _open_integrations(page):
    _panel(page, "office")
    page.evaluate("() => window.officeSetSubview('integrations')")
    page.wait_for_selector(".office-biz-toolbar", timeout=15000)
    page.wait_for_timeout(800)


@pytest.fixture
def second_business():
    name = f"Motion Test Trading Company {uuid.uuid4().hex[:6]}"
    return _post("/api/office/business/businesses/create", {"name": name})["business"]["id"]


def test_business_label_matches_the_name_beside_it(real_2x):
    _open_integrations(real_2x)
    sizes = real_2x.evaluate("""() => [document.querySelector('.office-biz-business > span'),
      document.querySelector('.office-biz-business .themed-select-trigger-label')].map(e => getComputedStyle(e).fontSize)""")
    assert sizes[0] == sizes[1], sizes


def test_business_list_spaces_its_choices_like_its_top_edge(second_business, real_2x):
    page = real_2x
    _open_integrations(page)
    page.click(".office-biz-business .themed-select-trigger")
    page.wait_for_selector(".themed-select-popup .themed-select-option")
    gaps = page.evaluate("""() => {
      const pop = document.querySelector('.themed-select-popup'), rows = [...pop.querySelectorAll('.themed-select-option')];
      const edge = parseFloat(getComputedStyle(pop).paddingTop);
      const between = rows.slice(1).map((r, i) => r.getBoundingClientRect().top - rows[i].getBoundingClientRect().bottom);
      const bottom = parseFloat(getComputedStyle(pop).paddingBottom);
      return {rows: rows.length, edge, between, bottom};
    }""")
    assert gaps["rows"] >= 2, gaps
    assert all(abs(gap - gaps["edge"]) <= .5 for gap in gaps["between"]), gaps
    assert abs(gaps["bottom"] - gaps["edge"]) <= .5, gaps


def test_other_selects_keep_their_plain_list(real_2x):
    page = real_2x
    _open_integrations(page)
    page.click(".office-biz-business .themed-select-trigger")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert page.evaluate("() => [...document.querySelectorAll('.themed-select-popup.is-spaced')].length") <= 1
    page.evaluate("() => { const s = document.createElement('select'); s.id = 'fxPlain'; s.innerHTML = '<option>One</option><option>Two</option>'; document.body.append(s); enhanceThemedSelect(s); }")
    page.click("#fxPlain ~ .themed-select-trigger, .themed-select-wrap:has(#fxPlain) .themed-select-trigger")
    page.wait_for_selector(".themed-select-popup")
    assert page.evaluate("() => document.querySelector('.themed-select-popup').classList.contains('is-spaced')") is False


def _motion_page(browser):
    """A page with its animations running; the shared opener freezes them."""
    context = browser.new_context(viewport={"width": 1470, "height": 956}, device_scale_factor=1)
    page = context.new_page()
    page.add_init_script("try{localStorage.setItem('hermes-skin','zeus-2')}catch(e){}")
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove())")
    return context, page


def test_choosing_a_business_slides_the_plus_and_filter_instead_of_snapping(second_business, browser):
    context, page = _motion_page(browser)
    try:
        _open_integrations(page)
        page.evaluate("""() => { window.__xs = [];
          const filter = () => { const e = document.querySelector('.office-biz-filter'); return e ? Math.round(e.getBoundingClientRect().left * 10) / 10 : null; };
          const plus = () => Math.round(document.querySelector('.office-biz-add').getBoundingClientRect().left * 10) / 10;
          const tick = () => { window.__xs.push([plus(), filter()]); window.__raf = requestAnimationFrame(tick); };
          tick(); }""")
        before = page.evaluate("() => window.__xs[window.__xs.length - 1]")
        page.click(".office-biz-business .themed-select-trigger")
        page.click(".themed-select-popup .themed-select-option:not(.selected)")
        page.wait_for_timeout(900)
        steps = page.evaluate("() => { cancelAnimationFrame(window.__raf); return window.__xs; }")
        plus_positions = {round(x, 1) for x, _ in steps}
        end = steps[-1]
        assert end[0] != before[0], "the business name never changed width"
        between = [x for x in plus_positions if min(before[0], end[0]) + 2 < x < max(before[0], end[0]) - 2]
        assert len(between) >= 3, (before, end, sorted(plus_positions))
        filter_between = {f for _, f in steps if f is not None and min(before[1], end[1]) + 2 < f < max(before[1], end[1]) - 2}
        assert len(filter_between) >= 3, (before, end, sorted(filter_between))
    finally:
        context.close()


def test_changing_business_or_tab_brings_the_new_view_in(second_business, browser):
    context, page = _motion_page(browser)
    try:
        _open_integrations(page)
        page.click("[data-tab=activity]")
        page.wait_for_selector("[data-tab=activity].is-active")
        page.wait_for_timeout(30)
        state = page.evaluate("""() => { const v = document.querySelector('.office-biz-view'); const s = getComputedStyle(v);
          return {entering: v.classList.contains('is-entering'), name: s.animationName, opacity: Number(s.opacity)}; }""")
        assert state["entering"] and state["name"] == "office-biz-view-in" and state["opacity"] < 1, state
        page.wait_for_timeout(600)
        assert page.evaluate("() => Number(getComputedStyle(document.querySelector('.office-biz-view')).opacity)") == 1
        page.click(".office-biz-business .themed-select-trigger")
        page.click(".themed-select-popup .themed-select-option:not(.selected)")
        page.wait_for_function("() => document.querySelector('.office-biz-view.is-entering')", timeout=8000)
    finally:
        context.close()


def test_polling_repaints_do_not_replay_the_entrance(browser):
    context, page = _motion_page(browser)
    try:
        _open_integrations(page)
        page.wait_for_timeout(500)
        assert page.evaluate("() => !!document.querySelector('.office-biz-view') && !document.querySelector('.office-biz-view.is-entering')")
    finally:
        context.close()


# ── Scheduled jobs ──────────────────────────────────────────────────────────

CRON_ITEM = ('<div class="cron-item" id="fxCron"><div class="cron-header"><span class="cron-agent-badge">🤖</span>'
             '<span class="cron-name">HEHE</span><span class="cron-status active">Active</span></div></div>')


def test_active_job_cards_sit_a_pixel_lower_for_icon_and_name(real_2x):
    page = real_2x
    page.evaluate("async () => { await switchPanel('tasks'); }")
    page.wait_for_timeout(800)
    _row(page, "#cronList", CRON_ITEM)
    page.wait_for_timeout(100)
    assert _moved(page, "#fxCron .cron-name", "text", "#fxCron .cron-name{top:-1px!important}", within="#fxCron") == 1
    badge_undo = "#fxCron .cron-agent-badge{top:0!important}"
    handle = page.add_style_tag(content=badge_undo)
    page.wait_for_timeout(100)
    old = page.eval_on_selector("#fxCron .cron-agent-badge", "e => e.getBoundingClientRect().top")
    handle.evaluate("e => e.remove()")
    assert page.eval_on_selector("#fxCron .cron-agent-badge", "e => e.getBoundingClientRect().top") - old == 1
