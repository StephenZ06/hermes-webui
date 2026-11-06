"""Chat page, second round: fork transition, model picker, menu nudges, folder counts.

Nudges are read as ink on a real 2x display with and without the rule being asked for,
so each number is how far the eye sees the thing move. The fork and the model picker are
checked on what the page does, not on source text.
"""

import pytest
from PIL import ImageChops

from tests.test_chat_optical_alignment_browser import (  # noqa: F401
    MACBOOK, _ink, _open, _rect, _shot, browser, pytestmark, real_2x,
)
from tests.test_office_notes_workhub_nudges_browser import _moved, _panel, _post, _row


def _undo(page, css):
    handle = page.add_style_tag(content=css)
    page.wait_for_timeout(150)
    return handle


def _rect_top(page, selector):
    return page.eval_on_selector(selector, "e => e.getBoundingClientRect().top")


# ── fork ────────────────────────────────────────────────────────────────────

@pytest.fixture
def forkable_session():
    messages = []
    for i in range(60):
        messages.append({"role": "user", "content": f"Question {i}"})
        messages.append({"role": "assistant", "content": f"Answer {i}\n\n```python\nvalue = {i}\n```"})
    sid = _post("/api/session/import", {"title": "Fork probe", "messages": messages})["session"]["session_id"]
    created = [sid]
    yield sid, created
    for session_id in created:
        _post("/api/session/delete", {"session_id": session_id})


def test_forking_keeps_the_transcript_up_instead_of_blanking_to_a_skeleton(browser, forkable_session):
    sid, created = forkable_session
    context, page = _open(browser, MACBOOK)
    try:
        page.evaluate("async sid => { await loadSession(sid); }", sid)
        page.wait_for_selector("#messages .msg-actions button[onclick*=forkFromMessage]")
        page.wait_for_timeout(2000)  # the transcript pins itself to the bottom while it settles
        page.evaluate("""() => {
          window.__skeletons = [];
          new MutationObserver(list => list.forEach(r => r.addedNodes.forEach(n => {
            if (n.classList && n.classList.contains('skel')) window.__skeletons.push(n.className);
          }))).observe(document.getElementById('messages'), {childList: true});
        }""")
        button = page.locator("#messages .msg-actions button[onclick*=forkFromMessage]").nth(10)
        button.evaluate("e => e.scrollIntoView({block: 'center'})")
        centre = "e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }"
        page.wait_for_timeout(400)
        box = button.evaluate(centre)
        page.mouse.move(box[0] - 40, box[1] - 60)
        page.mouse.move(box[0], box[1])
        page.wait_for_timeout(400)  # the row's actions fade in on hover, and code blocks settle
        box = button.evaluate(centre)
        assert page.evaluate("([x, y, el]) => !!document.elementFromPoint(x, y)?.closest('button[onclick*=forkFromMessage]')", box), "the fork button is not under the pointer"
        page.mouse.move(box[0], box[1])
        page.mouse.down()
        page.mouse.up()
        page.wait_for_function("(sid) => S.session && S.session.session_id !== sid", arg=sid, timeout=15000)
        created.append(page.evaluate("() => S.session.session_id"))
        page.wait_for_selector("#messages .msg-row")
        assert page.evaluate("() => window.__skeletons") == []
        assert page.evaluate("() => document.querySelectorAll('#messages .msg-row').length") > 0
    finally:
        context.close()


# ── model picker ────────────────────────────────────────────────────────────

def _configured_picker(page):
    page.evaluate("""() => {
      window._configuredModelBadges = {
        'gpt-5.6-terra': {role: 'primary', label: 'Primary', provider: 'custom:acme'},
        'gpt-5.6-luna': {role: 'fallback', label: 'Fallback 1'},
      };
      const select = document.getElementById('modelSelect');
      for (const value of ['gpt-5.6-terra', 'gpt-5.6-luna']) {
        const option = document.createElement('option');
        option.value = value; option.textContent = value; select.appendChild(option);
      }
    }""")
    page.click("#composerModelChip")
    page.wait_for_selector("#composerModelDropdown .model-opt")


def test_configured_models_do_not_repeat_their_id_under_the_name(browser):
    context, page = _open(browser, MACBOOK)
    try:
        _configured_picker(page)
        rows = page.evaluate("""() => {
          const out = [];
          let on = false;
          for (const e of document.querySelectorAll('#composerModelDropdown .model-group, #composerModelDropdown .model-opt')) {
            if (e.classList.contains('model-group')) { on = e.textContent.trim().toLowerCase() === 'configured'; continue; }
            if (on) out.push({name: e.querySelector('.model-opt-name').textContent,
                              ids: [...e.querySelectorAll('.model-opt-id')].map(i => i.textContent)});
          }
          return out;
        }""")
        assert [r["name"] for r in rows] == ["gpt-5.6-terra", "gpt-5.6-luna"]
        assert [r["ids"] for r in rows] == [[], []]
    finally:
        context.close()


def test_other_provider_rows_still_show_their_id(browser):
    context, page = _open(browser, MACBOOK)
    try:
        _configured_picker(page)
        ids = page.eval_on_selector_all("#composerModelDropdown .model-opt-id", "els => els.map(e => e.textContent)")
        assert any("/" in value for value in ids), ids
    finally:
        context.close()


def test_scope_note_hides_what_scrolls_under_it(browser):
    context, page = _open(browser, MACBOOK)
    try:
        page.set_viewport_size({"width": 1470, "height": 420})  # short enough that the list scrolls
        page.wait_for_timeout(300)
        _configured_picker(page)
        page.evaluate("""() => {
          const note = document.querySelector('#composerModelDropdown .model-scope-note');
          let box = note.parentElement;
          while (box && box.scrollHeight <= box.clientHeight) box = box.parentElement;
          if (box) box.scrollTop = 60;
          window.__scrolled = box ? box.scrollTop : 0;
        }""")
        assert page.evaluate("() => window.__scrolled") > 0, "the picker never scrolled, so nothing slid under the note"
        page.wait_for_timeout(200)
        box = _rect(page, "#composerModelDropdown .model-scope-note")
        clip = {"x": box["x"] + 2, "y": box["y"] + 2, "width": box["width"] - 4, "height": box["height"] - 4}
        before = _shot(page, clip)
        handle = page.add_style_tag(content="#composerModelDropdown :is(.model-opt,.model-group,.model-search-row,"
                                            ".model-custom-row){visibility:hidden!important}")
        after = _shot(page, clip)
        handle.evaluate("e => e.remove()")
        # A level or two of rounding at the edge is not a row showing through; text would be tens of levels.
        assert ImageChops.difference(before, after).convert("L").getextrema()[1] <= 2, "rows show through the note"
    finally:
        context.close()


def test_a_highlighted_model_row_runs_up_to_the_next_divider(browser):
    context, page = _open(browser, MACBOOK)
    try:
        _configured_picker(page)
        page.wait_for_timeout(300)
        gap = page.evaluate("""() => {
          const rows = [...document.querySelectorAll('#composerModelDropdown .model-opt')];
          const last = rows.find(r => r.nextElementSibling && r.nextElementSibling.classList.contains('model-group'));
          return last.nextElementSibling.getBoundingClientRect().top - last.getBoundingClientRect().bottom;
        }""")
        assert gap == 0, f"{gap}px of bare menu between a row's highlight and the divider under it"
    finally:
        context.close()


def test_picker_headings_have_equal_room_above_and_below_their_text(real_2x):
    page = real_2x
    _configured_picker(page)
    page.mouse.move(5, 5)
    page.wait_for_timeout(800)
    page.evaluate("""() => { const groups = [...document.querySelectorAll('#composerModelDropdown .model-group')];
      groups.find(e => /configured/i.test(e.textContent)).id = 'fxCfg';
      document.querySelector('#composerModelDropdown .model-custom-sep').id = 'fxSep'; }""")
    for heading, below_to in (("#fxCfg", "#fxCfg + .model-opt"), ("#fxSep", "#fxSep + .model-custom-row .model-custom-input")):
        box = page.eval_on_selector(heading, "e => { const r = e.getBoundingClientRect(); return r.top + parseFloat(getComputedStyle(e).borderTopWidth); }")
        edge = page.eval_on_selector(below_to, "e => e.getBoundingClientRect().top")
        ink = _ink(page, heading, "text")
        assert abs((ink["top"] - box) - (edge - ink["bottom"])) <= 1, (heading, ink, box, edge)


def test_provider_groups_start_collapsed_even_the_one_holding_the_current_model(browser):
    context, page = _open(browser, MACBOOK)
    try:
        _configured_picker(page)
        out = page.evaluate("""() => [...document.querySelectorAll('#composerModelDropdown .model-group.collapsible')].map(g => ({
          open: g.classList.contains('open'),
          body: getComputedStyle(g.nextElementSibling).display,
        }))""")
        assert out, "no provider groups rendered"
        assert all(not row["open"] and row["body"] == "none" for row in out), out
    finally:
        context.close()


def test_a_search_opens_the_groups_and_clearing_it_collapses_them_again(browser):
    context, page = _open(browser, MACBOOK)
    try:
        _configured_picker(page)
        page.fill("#composerModelDropdown .model-search-input", "gpt")
        page.wait_for_timeout(300)
        assert page.evaluate("() => [...document.querySelectorAll('#composerModelDropdown .model-group.collapsible')].some(g => g.classList.contains('open'))")
        page.fill("#composerModelDropdown .model-search-input", "")
        page.wait_for_timeout(300)
        assert page.evaluate("() => [...document.querySelectorAll('#composerModelDropdown .model-group.collapsible')].every(g => !g.classList.contains('open'))")
    finally:
        context.close()


def test_search_box_sits_a_pixel_lower_and_the_custom_id_box_a_pixel_higher(real_2x):
    page = real_2x
    _configured_picker(page)
    page.mouse.move(5, 5)
    page.wait_for_timeout(800)
    page.evaluate("""() => { const d = document.querySelector('#composerModelDropdown');
      d.querySelector('.model-search-input').id = 'fxSearch'; d.querySelector('.model-search-clear').id = 'fxClear';
      d.querySelector('.model-custom-input').id = 'fxCustom'; }""")
    # The menu is anchored at its bottom, so everything is measured from its own top edge.
    inside = lambda sel: page.eval_on_selector(sel, "e => e.getBoundingClientRect().top - document.querySelector('#composerModelDropdown').getBoundingClientRect().top")
    now = {k: inside(k) for k in ("#fxSearch", "#fxClear", "#fxCustom")}
    handle = _undo(page, "#composerModelDropdown .model-search-row{padding-top:8px!important;padding-bottom:10px!important}"
                         "#composerModelDropdown .model-custom-row{padding-top:6px!important}.model-custom-sep{padding-top:6px!important}")
    old = {k: inside(k) for k in now}
    handle.evaluate("e => e.remove()")
    assert now["#fxSearch"] - old["#fxSearch"] == 1
    assert now["#fxClear"] - old["#fxClear"] == 1
    assert now["#fxCustom"] - old["#fxCustom"] == -1


# ── nudges ──────────────────────────────────────────────────────────────────

def test_workspace_menu_name_and_path_sit_half_a_pixel_higher(real_2x):
    page = real_2x
    page.click("#composerWorkspaceChip")
    page.wait_for_selector("#composerWsDropdown .ws-opt:not(.ws-opt-action) .ws-opt-path")
    page.mouse.move(5, 5)
    page.wait_for_timeout(800)
    row = "#composerWsDropdown .ws-opt:not(.ws-opt-action)"
    undo = f"{row} > :is(.ws-opt-name,.ws-opt-path){{top:0!important}}"
    assert _moved(page, f"{row} .ws-opt-name", "text", undo, within=row) == -.5
    assert _moved(page, f"{row} .ws-opt-path", "text", undo, within=row) == -.5


def test_profile_menu_text_sits_half_a_pixel_higher_but_dots_icons_and_model_stay(real_2x):
    page = real_2x
    page.click("#profileChip")
    page.wait_for_selector("#profileDropdown .profile-opt-name")
    page.evaluate("""() => {
      const first = document.querySelector('#profileDropdown .profile-opt:not(.ws-manage)');
      first.insertAdjacentHTML('beforeend', '<div class="profile-opt-meta">local-model</div>');
    }""")
    page.wait_for_timeout(100)
    first = "#profileDropdown .profile-opt:not(.ws-manage)"
    undo = ("#profileDropdown .profile-opt-name{top:0!important}"
            "#profileDropdown .profile-opt-name :is(.profile-opt-badge,svg){translate:none!important}"
            "#profileDropdown .profile-opt.ws-manage{padding-top:6px!important;padding-bottom:6px!important}"
            "#profileDropdown .profile-opt.ws-manage svg{translate:none!important}")
    assert _moved(page, f"{first} .profile-opt-name", "text", undo, within=first) == -.5
    assert _moved(page, f"{first} .profile-opt-meta", "text", undo, within=first) == 0
    manage = "#profileDropdown .profile-opt.ws-manage"
    assert _moved(page, manage, "text", undo) == -.5
    assert _moved(page, manage, "icon", undo) == 0
    dot = f"{first} .profile-opt-badge"
    now = _rect_top(page, dot)
    handle = _undo(page, undo)
    assert _rect_top(page, dot) == now
    handle.evaluate("e => e.remove()")


def test_persona_dots_sit_half_a_pixel_lower(real_2x):
    page = real_2x
    page.click("#btnPersonaPicker")
    page.wait_for_selector("#personaPickerPopup .persona-picker-dot")
    dot = "#personaPickerPopup .persona-picker-row:first-child .persona-picker-dot"
    now = _rect_top(page, dot)
    handle = _undo(page, "#personaPickerPopup .persona-picker-dot{translate:none!important}")
    assert now - _rect_top(page, dot) == .5
    handle.evaluate("e => e.remove()")


def test_folder_titles_inside_chat_folders_sit_a_pixel_higher(real_2x):
    page = real_2x
    page.evaluate("""() => {
      const wrap = document.createElement('div');
      wrap.className = 'project-folder-sessions expanded'; wrap.id = 'fxFolderChats';
      wrap.innerHTML = '<div class="project-folder-sessions-inner"><div class="session-item" id="fxFolderChat">'
        + '<div class="session-text"><div class="session-title-row"><span class="session-title">HEHE</span></div></div></div></div>';
      document.getElementById('sessionList').prepend(wrap);
    }""")
    page.wait_for_timeout(200)
    assert _moved(page, "#fxFolderChat .session-title", "text",
                  "#fxFolderChat .session-title{top:1.5px!important}", within="#fxFolderChat") == -1


FOLDER_ROW = ('<button type="button" class="project-chip project-folder-row {extra}" id="fxFolder">'
              '<span class="project-folder-chevron">▸</span>'
              '<span class="project-folder-dot-slot"><span class="color-dot" style="background:#f5c542"></span></span>'
              '<span class="project-folder-name">HEHE</span><span class="project-folder-count">2</span></button>')
COUNT_UNDO = "#fxFolder .project-folder-count{top:0!important}"


def _count_moved(page, host, extra, undo=COUNT_UNDO):
    _row(page, host, FOLDER_ROW.format(extra=extra))
    page.wait_for_timeout(150)
    try:
        return _moved(page, "#fxFolder .project-folder-count", "text", undo, within="#fxFolder")
    finally:
        page.evaluate("() => document.getElementById('fxFolder').remove()")


def test_folder_counts_sit_half_a_pixel_lower_in_chat(real_2x):
    assert _count_moved(real_2x, "#sessionList", "") == .5


def test_folder_counts_sit_half_a_pixel_lower_in_work_hub(real_2x):
    _panel(real_2x, "notes")
    assert _count_moved(real_2x, "#workHubSidebar .work-hub-nav", "work-hub-project-tile") == .5


def test_folder_counts_sit_half_a_pixel_lower_in_notes(real_2x):
    _panel(real_2x, "notebook")
    assert _count_moved(real_2x, "#notebookSidebar .nb-nav", "work-hub-project-tile") == .5


def test_folder_counts_sit_half_a_pixel_lower_in_office(real_2x):
    _panel(real_2x, "office")
    assert _count_moved(real_2x, "#officeProjectFolders .project-folder-list", "office-project-folder") == .5
