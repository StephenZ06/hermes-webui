"""Work Hub's side panel highlight moves the way Chat's does.

The side panel is rebuilt on every click, so its highlight used to jump.
Now it glides from the row it left to the row picked (ui.js
playActiveHighlightGlide), but only inside a section: Inbox / All Work are
one, the project folders another, and between them the highlight fades in
place instead of travelling across the panel.
"""
import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        project_id = None
        try:
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            project_id = page.evaluate("""async () => (await api('/api/projects/create', {method: 'POST',
                body: JSON.stringify({name: 'Glide project', work_hub_managed: true})})).project.project_id""")
            page.evaluate("async () => { await switchPanel('notes'); }")
            page.wait_for_selector(".work-hub-scope[data-scope='inbox']", timeout=15000)
            page.wait_for_selector(f".work-hub-project-tile[data-scope='{project_id}']", timeout=15000)
            yield page
        finally:
            if project_id:
                page.evaluate("(id) => api('/api/projects/delete', {method: 'POST', body: JSON.stringify({project_id: id})})", project_id)
            browser.close()


_CLICK = """(selector) => {
    const seen = new MutationObserver(() => {});
    seen.observe(document.body, {childList: true});
    document.querySelector(selector).click();
    const glides = seen.takeRecords().flatMap(m => [...m.addedNodes])
        .filter(n => n.classList && n.classList.contains('sidebar-highlight-glide')).length;
    seen.disconnect();
    const active = document.querySelector('.work-hub-scope.active, .work-hub-project-tile.active');
    return {glides, active: active && active.dataset.scope, fades: active ? active.getAnimations().length : 0};
}"""


def test_inbox_and_all_work_glide_between_each_other(page):
    page.evaluate(_CLICK, ".work-hub-scope[data-scope='inbox']")
    page.wait_for_timeout(600)
    out = page.evaluate(_CLICK, ".work-hub-scope[data-scope='all']")
    assert out["active"] == "all" and out["glides"] == 1, out


def test_from_a_filter_to_a_project_folder_it_fades_in_place(page):
    page.evaluate(_CLICK, ".work-hub-scope[data-scope='all']")
    page.wait_for_timeout(600)
    out = page.evaluate(_CLICK, ".work-hub-project-tile")
    assert out["glides"] == 0 and out["fades"] >= 1, out
