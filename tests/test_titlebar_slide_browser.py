"""The titlebar's items slide when the chat title changes length.

The titlebar centres its icon, title, message count and search button as one
group, so opening a chat with a longer or shorter title moves all of them.
They slide to their new places instead of jumping there.
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


def test_a_longer_chat_title_slides_the_count_and_search_into_place(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('chat'); }")
    sids = page.evaluate("""async () => {
      const make = async (title) => {
        const r = await fetch('/api/session/import', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({title, messages: [{role: 'user', content: 'q'}, {role: 'assistant', content: 'a'}]})});
        return (await r.json()).session.session_id;
      };
      return [await make('Short'), await make('A much longer chat title than the first one')];
    }""")
    page.evaluate("(sid) => loadSession(sid)", sids[0])
    page.wait_for_function("() => document.getElementById('appTitlebarTitle').textContent === 'Short'", timeout=15000)
    page.wait_for_timeout(500)
    page.evaluate("""() => { window.__xs = []; const tick = () => {
      window.__xs.push(Math.round(document.getElementById('btnCommandPalette').getBoundingClientRect().left * 10) / 10);
      if (window.__xs.length < 60) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }""")
    page.evaluate("(sid) => { loadSession(sid); }", sids[1])
    page.wait_for_function("() => window.__xs.length >= 60", timeout=15000)
    xs = page.evaluate("() => window.__xs")
    start, end = xs[0], xs[-1]
    assert abs(end - start) > 40, xs  # the longer title did move the button
    between = [x for x in xs if min(start, end) + 2 < x < max(start, end) - 2]
    assert len(between) >= 4, ("the button jumped instead of sliding", xs)
    # Every step heads toward the new place: no overshoot back and forth.
    steps = [b - a for a, b in zip(xs, xs[1:]) if abs(b - a) > 0.05]
    assert all((s > 0) == (end > start) for s in steps), xs
