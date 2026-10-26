"""Rows that a text change re-flows slide instead of jumping.

The titlebar centres its icon, title, message count and search button as one
group, so opening a chat with a longer or shorter title moves all of them.
The composer's chips share one row, so a longer model name pushes the others
along. In both, the items slide to their new places instead of jumping there.
"""

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1280, "height": 860})
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def _chats(page, first, second):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('chat'); }")
    sids = page.evaluate("""async (chats) => {
      const make = async ([title, model]) => {
        const r = await fetch('/api/session/import', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({title, model: model || undefined, messages: [{role: 'user', content: 'q'}, {role: 'assistant', content: 'a'}]})});
        return (await r.json()).session.session_id;
      };
      return [await make(chats[0]), await make(chats[1])];
    }""", [first, second])
    page.evaluate("(sid) => loadSession(sid)", sids[0])
    page.wait_for_function("(t) => document.getElementById('appTitlebarTitle').textContent === t", arg=first[0], timeout=15000)
    page.wait_for_timeout(600)
    return sids


def _track(page, selector, sid):
    page.evaluate("""(sel) => { window.__xs = []; const tick = () => {
      window.__xs.push(Math.round(document.querySelector(sel).getBoundingClientRect().left * 10) / 10);
      if (window.__xs.length < 60) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }""", selector)
    page.evaluate("(sid) => { loadSession(sid); }", sid)
    page.wait_for_function("() => window.__xs.length >= 60", timeout=15000)
    return page.evaluate("() => window.__xs")


def _assert_slid(xs):
    start, end = xs[0], xs[-1]
    assert abs(end - start) > 40, xs  # the longer title did move the button
    between = [x for x in xs if min(start, end) + 2 < x < max(start, end) - 2]
    assert len(between) >= 4, ("the button jumped instead of sliding", xs)
    # Every step heads toward the new place: no overshoot back and forth.
    steps = [b - a for a, b in zip(xs, xs[1:]) if abs(b - a) > 0.05]
    assert all((s > 0) == (end > start) for s in steps), xs


def test_a_longer_chat_title_slides_the_count_and_search_into_place(page):
    sids = _chats(page, ("Short", None), ("A much longer chat title than the first one", None))
    _assert_slid(_track(page, "#btnCommandPalette", sids[1]))


def test_a_longer_model_name_slides_the_composer_chips_beside_it(page):
    # Same-length titles, so only the model chip's name changes length.
    sids = _chats(page, ("Model one", "gpt-5"), ("Model two", "provider/a-much-longer-model-name-for-the-chip"))
    _assert_slid(_track(page, "#composerWorkspaceGroup", sids[1]))
