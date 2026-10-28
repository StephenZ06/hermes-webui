"""Work Hub: a new item's title is a placeholder, returning to the window keeps an open item's edits,
and changing scope animates only the work items while changing view animates the whole board."""
import pytest

from tests._pytest_port import BASE


def _open_work_hub(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("""async () => {
        const project = (await api('/api/projects/create', {method: 'POST', body: JSON.stringify({name: 'Refinements', work_hub_managed: true})})).project;
        let rev = (await api('/api/work_hub/bootstrap')).revision || 0;
        const statuses = ['triage', 'backlog', 'todo'];
        for (let i = 0; i < 12; i++) {
            const item = {title: 'Refinement ' + i, status: statuses[i % 3], project_id: i < 3 ? null : project.project_id};
            rev = (await api('/api/work_hub/items/create', {method: 'POST', body: JSON.stringify({item, expected_revision: rev})})).revision;
        }
        await switchPanel('notes'); }""")
    page.wait_for_selector(".work-hub-card", timeout=10000)


def _clean_up(page):
    """The test server's state is shared with other tests: take back what these tests added."""
    page.evaluate("""async () => {
        const boot = await api('/api/work_hub/bootstrap'); let rev = boot.revision || 0;
        for (const item of boot.items || []) {
            if (!/^(Refinement |New work item$|Edited title$)/.test(item.title || '')) continue;
            rev = (await api('/api/work_hub/items/delete', {method: 'POST', body: JSON.stringify({item_id: item.id, expected_revision: rev})})).revision;
        }
        for (const project of boot.projects || []) {
            if (project.name === 'Refinements') await api('/api/projects/delete', {method: 'POST', body: JSON.stringify({project_id: project.project_id})});
        } }""")


def test_new_item_title_is_a_placeholder_and_window_focus_keeps_edits():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = None
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
            try:
                if page is not None:
                    _clean_up(page)
            finally:
                browser.close()
    assert fresh == ["", "New work item"], fresh            # the stand-in title clears on click
    assert after == [True, "Edited title", False], after    # coming back to the window does not rebuild the panel


def test_scope_change_animates_items_and_view_change_animates_the_board():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = None
        try:
            page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
            _open_work_hub(page)
            probe = """() => { const c = document.getElementById('workHubCanvas');
                const moving = s => [...c.querySelectorAll(s)].filter(e => e.getAnimations().length).length;
                return {columns: moving('.work-hub-column'), cards: moving('.work-hub-card'), rows: moving('.work-hub-list-row')}; }"""
            page.click(".work-hub-scope[data-scope='all']")
            page.wait_for_timeout(700)
            counted = page.evaluate("""() => new Promise(done => { const seen = []; const t0 = performance.now();
                document.querySelector(".work-hub-scope[data-scope='inbox']").click();
                (function f() { const badges = [...document.querySelectorAll('#workHubCanvas .work-hub-column header small')];
                    seen.push([parseInt(document.querySelector('#workHub .work-hub-live').textContent, 10), badges.filter(b => b.getAnimations().some(a => a instanceof CSSAnimation)).length]);
                    if (performance.now() - t0 < 700) requestAnimationFrame(f); else done(seen); })(); })""")
            page.click(".work-hub-scope[data-scope='all']")
            page.wait_for_timeout(700)
            page.click(".work-hub-scope[data-scope='inbox']")
            scope = page.evaluate(probe)
            page.wait_for_timeout(700)
            page.click("[data-view='list']")
            to_list = page.evaluate(probe)
            page.wait_for_timeout(500)
            page.click("[data-view='board']")
            to_board = page.evaluate(probe)
        finally:
            try:
                if page is not None:
                    _clean_up(page)
            finally:
                browser.close()
    assert scope["columns"] == 0 and scope["cards"] > 0, scope   # scope: the items come in, the columns stay
    totals = [total for total, _ in counted]
    steps = [b - a for a, b in zip(totals, totals[1:]) if b != a]
    assert len(set(totals)) > 2 and (all(v < 0 for v in steps) or all(v > 0 for v in steps)), totals  # the count runs, one way
    assert all(fading == 0 for _, fading in counted), counted    # the count badges themselves stay still
    assert to_list["rows"] > 0, to_list
    assert to_board["columns"] > 0, to_board                      # view: the whole board comes in
