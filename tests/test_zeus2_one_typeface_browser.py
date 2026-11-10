"""Zeus 2.0 uses one typeface everywhere: code and the Dashboard's pixel fonts
take the skin's own face (scaled stand-ins on the Dashboard)."""

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            tab.add_init_script("try{localStorage.setItem('hermes-theme','dark');localStorage.setItem('hermes-skin','zeus-2');}catch(e){}")
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay,#updateBanner').forEach(e => e.remove())")
            yield tab
        finally:
            browser.close()


def test_code_and_the_dashboard_use_the_skin_typeface(page):
    code = page.evaluate("""() => { const b = document.createElement('div'); b.className = 'msg-body'; b.innerHTML = '<code>x</code>';
      document.body.append(b); const f = getComputedStyle(b.firstChild).fontFamily; b.remove(); return f; }""")
    assert "Zeus2 Courier New" in code and "ui-monospace" not in code, code
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector(".dash.is-rpg h1", timeout=20000)
    families = page.evaluate("""() => [...document.querySelectorAll('.dash.is-rpg :is(h1,.dash-card,.rpg-panel,.dash-level-badge)')]
      .map(e => getComputedStyle(e).fontFamily)""")
    assert families and not [f for f in families if "Press Start" in f or "VT323" in f], families
