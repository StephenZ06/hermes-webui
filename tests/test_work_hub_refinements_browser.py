"""Work Hub: a new item's title is a placeholder, returning to the window keeps an open item's edits,
and changing scope animates only the work items while changing view animates the whole board."""
import pytest

from tests._pytest_port import BASE


def _open_work_hub(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("""async () => {
        const boot = await api('/api/work_hub/bootstrap'); let rev = boot.revision || 0;
        for (const status of ['triage', 'backlog', 'todo']) {
            const r = await api('/api/work_hub/items/create', {method: 'POST', body: JSON.stringify({item: {title: 'Refinement ' + status, status}, expected_revision: rev})});
            rev = r.revision;
        }
        await switchPanel('notes'); }""")
    page.wait_for_selector(".work-hub-card", timeout=10000)


def test_new_item_title_is_a_placeholder_and_window_focus_keeps_edits():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
            _open_work_hub(page)
            page.click("#workHubCreate")
            page.wait_for_selector("#workHubTitle")
            fresh = page.evaluate("() => { const t = document.getElementById('workHubTitle'); return [t.value, t.placeholder]; }")
            page.fill("#workHubTitle", "Edited title")
            page.evaluate("() => { window.__panel = document.querySelector('.wh-insp'); window.dispatchEvent(new Event('focus')); }")
            page.wait_for_timeout(800)
            after = page.evaluate("""() => [window.__panel === document.querySelector('.wh-insp'),
                document.getElementById('workHubTitle').value, document.getElementById('workHubSave').disabled]""")
        finally:
            browser.close()
    assert fresh == ["", "New work item"], fresh            # the stand-in title clears on click
    assert after == [True, "Edited title", False], after    # coming back to the window does not rebuild the panel


def test_scope_change_animates_items_and_view_change_animates_the_board():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
            _open_work_hub(page)
            probe = """() => { const c = document.getElementById('workHubCanvas');
                const moving = s => [...c.querySelectorAll(s)].filter(e => e.getAnimations().length).length;
                return {columns: moving('.work-hub-column'), cards: moving('.work-hub-card'), rows: moving('.work-hub-list-row')}; }"""
            page.click(".work-hub-scope[data-scope='inbox']")
            scope = page.evaluate(probe)
            page.wait_for_timeout(500)
            page.click("[data-view='list']")
            to_list = page.evaluate(probe)
            page.wait_for_timeout(500)
            page.click("[data-view='board']")
            to_board = page.evaluate(probe)
        finally:
            browser.close()
    assert scope["columns"] == 0 and scope["cards"] > 0, scope   # scope: the items come in, the columns stay
    assert to_list["rows"] > 0, to_list
    assert to_board["columns"] > 0, to_board                      # view: the whole board comes in
