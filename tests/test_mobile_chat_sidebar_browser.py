"""Phone chat sidebar and composer polish: the conversation filter keeps the
keyboard, select mode ends on delete, even spacing, aligned option buttons,
unclipped highlight rings, folder rows matching Work Hub / Notes."""

import json
import time
import urllib.request

import pytest

from tests._pytest_port import BASE

PHONE = {"viewport": {"width": 430, "height": 873}, "is_mobile": True, "has_touch": True}


def _import(title):
    body = {"title": title, "messages": [{"role": "user", "content": "hi " + title}, {"role": "assistant", "content": "hello"}]}
    req = urllib.request.Request(BASE + "/api/session/import", method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["session"]["session_id"]


def _boot(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")


@pytest.fixture()
def phone():
    sync_api = pytest.importorskip("playwright.sync_api")
    for title in ("Filter alpha", "Filter beta", "Filter gamma"):
        _import(title)
    req = urllib.request.Request(BASE + "/api/projects/create", method="POST", data=json.dumps({"name": "Folder size"}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(**PHONE).new_page()
            _boot(page)
            page.evaluate("() => _setMobileDrawerState(document.querySelector('.sidebar'), 'open')")
            time.sleep(0.6)
            yield page
        finally:
            browser.close()


def test_conversation_filter_keeps_focus_while_typing_and_deleting(phone):
    page = phone
    page.tap("#sessionSearch")
    page.evaluate("() => { window.__blurs = 0; document.getElementById('sessionSearch').addEventListener('blur', () => window.__blurs++); }")
    for key in ("f", "i", "Backspace", "l"):
        page.keyboard.press(key)
        time.sleep(0.8)
    state = page.evaluate("() => [document.activeElement && document.activeElement.id, document.getElementById('sessionSearch').value, window.__blurs]")
    assert state == ["sessionSearch", "fl", 0]


def test_deleting_a_chat_ends_select_mode(phone):
    page = phone
    page.evaluate("() => toggleSessionSelectMode()")
    sid = page.evaluate("() => [...document.querySelectorAll('.session-item[data-sid]')].find(e => e.offsetParent).dataset.sid")
    page.evaluate("(sid) => { window.__del = deleteSession(sid); }", sid)
    page.wait_for_function("() => [...document.querySelectorAll('button')].some(b => /delete/i.test(b.textContent) && b.offsetParent)", timeout=5000)
    page.evaluate("() => [...document.querySelectorAll('button')].find(b => /delete/i.test(b.textContent) && b.offsetParent && b.closest('[class*=dialog]')).click()")
    page.wait_for_function("(sid) => !document.querySelector('.session-item[data-sid=\"' + sid + '\"]')", arg=sid, timeout=10000)
    assert page.evaluate("() => [_sessionSelectMode, !!document.querySelector('.session-search.is-selecting'), document.querySelectorAll('.session-item input[type=checkbox]').length]") == [False, False, 0]


def test_select_mode_controls_sit_over_the_filter_box(phone):
    page = phone
    measure = """() => { const f = document.querySelector('#sessionSearch').getBoundingClientRect();
        const h = document.querySelector('.chat-sidebar-section--workspaces .chat-sidebar-section-heading').getBoundingClientRect();
        const x = document.querySelector('.session-select-overlay .batch-exit-btn');
        const a = document.querySelector('.session-select-overlay .batch-delete-btn');
        return { field: [f.top, f.bottom], heading: h.top,
                 exit: x ? [x.getBoundingClientRect().top, x.getBoundingClientRect().bottom] : null,
                 all: a ? a.getBoundingClientRect().right : null, right: f.right }; }"""
    before = page.evaluate(measure)
    page.evaluate("() => toggleSessionSelectMode()")
    time.sleep(0.4)
    after = page.evaluate(measure)
    # Nothing moves: the controls cover the filter instead of adding a row.
    assert abs(after["heading"] - before["heading"]) <= 0.5
    assert after["field"][0] <= after["exit"][0] and after["exit"][1] <= after["field"][1]
    assert after["all"] <= after["right"]
    assert page.evaluate("() => document.querySelector('.session-search').classList.contains('is-selecting')")
    # Delete is the only action: inert until a chat is picked, no separate card.
    assert page.evaluate("() => document.querySelector('.session-select-overlay .batch-delete-btn').disabled")
    page.evaluate("() => setSessionSelected([...document.querySelectorAll('.session-item[data-sid]')].find(e => e.offsetParent).dataset.sid, true)")
    assert page.evaluate("() => [document.querySelector('.session-select-overlay .batch-delete-btn').disabled, document.querySelectorAll('.batch-action-bar').length]") == [False, 0]
    page.evaluate("() => exitSessionSelectMode()")
    assert not page.evaluate("() => document.querySelector('.session-search').classList.contains('is-selecting')")


def test_highlight_ring_is_drawn_inside_the_row(phone):
    page = phone
    shadow = page.evaluate("""() => new Promise(r => { const a = [...document.querySelectorAll('.session-item')].find(e => e.offsetParent);
        a.classList.add('long-pressing'); setTimeout(() => r(getComputedStyle(a).boxShadow), 500); })""")
    assert "inset" in shadow


def test_chat_folder_rows_match_work_hub_rows(phone):
    page = phone
    chat = page.evaluate("() => { const e = [...document.querySelectorAll('#sessionList .project-chip')].find(x => x.offsetParent); return e ? e.getBoundingClientRect().height : null; }")
    if chat is None:
        pytest.skip("no project folders in this state")
    page.evaluate("async () => { await switchPanel('notes'); }")
    time.sleep(1.2)
    page.evaluate("() => _setMobileDrawerState(document.querySelector('.sidebar'), 'open')")
    time.sleep(0.6)
    hub = page.evaluate("() => { const e = [...document.querySelectorAll('#workHubSidebar .project-chip')].find(x => x.offsetParent); return e ? e.getBoundingClientRect().height : null; }")
    if hub is None:
        pytest.skip("no Work Hub folders in this state")
    assert abs(chat - hub) <= 1


def test_composer_option_text_is_centred_on_its_icon(phone):
    page = phone
    page.evaluate("() => { closeMobileSidebar(); openMobileComposerConfig(); }")
    time.sleep(0.6)
    offsets = page.evaluate("""() => ['composerMobileWorkspaceAction', 'composerMobileModelAction', 'composerMobileReasoningAction'].map(id => {
        const b = document.getElementById(id); const v = b.querySelector('.composer-mobile-config-value').getBoundingClientRect();
        const i = b.querySelector('svg').getBoundingClientRect(); return Math.abs((v.top + v.height / 2) - (i.top + i.height / 2)); })""")
    assert all(o <= 1 for o in offsets)


def test_composer_option_text_descenders_are_not_clipped(phone):
    page = phone
    page.evaluate("""() => { closeMobileSidebar(); openMobileComposerConfig();
        document.querySelector('#composerMobileReasoningAction .composer-mobile-config-value').textContent = 'High'; }""")
    time.sleep(0.6)
    clip, glyphs = page.evaluate("""() => { const v = document.querySelector('#composerMobileReasoningAction .composer-mobile-config-value');
        const r = document.createRange(); r.selectNodeContents(v); return [v.getBoundingClientRect().bottom, r.getBoundingClientRect().bottom]; }""")
    assert clip >= glyphs


def test_zeus_chat_controls_shift_down_by_a_tenth_of_a_pixel(phone):
    phone.evaluate("() => { document.documentElement.dataset.skin = 'zeus-2'; }")
    tops = phone.evaluate("""() => [
        document.getElementById('sessionSearch'),
        document.querySelector('#mainChat .suggestion'),
        document.getElementById('msg')
    ].map(element => getComputedStyle(element).top)""")
    assert tops == ['0.1px', '0.1px', '0.1px']
