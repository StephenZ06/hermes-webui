"""Chat rows keep room for their ⋯ trigger, and the ⋯ menu insets its labels evenly."""
import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1300, "height": 1000}).new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('chat'); }")
            # A fresh test server has no chats: render two from the sidebar's own cache.
            page.evaluate("""() => { const now = Date.now() / 1000;
                _allSessions = [1, 2].map(i => ({session_id: 'spacing' + i, title: 'Spacing chat ' + i, message_count: 4,
                    created_at: now - i * 60, updated_at: now - i * 60, last_message_at: now - i * 60, workspace: '', model: ''}));
                renderSessionListFromCache(); }""")
            page.wait_for_selector(".session-item .session-actions-trigger", state="attached", timeout=15000)
            yield page
        finally:
            browser.close()


def test_rows_inside_a_project_folder_keep_room_for_the_trigger(page):
    gap = page.evaluate("""() => {
        const row = document.querySelector('.session-item:has(.session-actions-trigger)').cloneNode(true);
        row.querySelector('.session-title').textContent = 'Subagent Workspace Listing Workflow '.repeat(3);
        const folder = document.createElement('div'); folder.className = 'project-folder-sessions';
        folder.style.width = '260px'; folder.appendChild(row);
        document.querySelector('#sessionList').prepend(folder);
        row.classList.add('menu-open');
        const title = row.querySelector('.session-title').getBoundingClientRect();
        const trigger = row.querySelector('.session-actions-trigger').getBoundingClientRect();
        return trigger.left - title.right; }""")
    assert gap >= 4, gap


def test_menu_labels_sit_the_same_distance_from_every_edge(page):
    item = page.locator(".session-item:has(.session-actions-trigger)").first
    item.hover()
    item.locator(".session-actions-trigger").click()
    page.wait_for_selector(".session-action-menu:not(.popup-closing)")
    page.wait_for_timeout(500)
    insets = page.evaluate("""() => { const m = document.querySelector('.session-action-menu:not(.popup-closing)');
        const box = m.getBoundingClientRect();
        const opts = [...m.querySelectorAll('.session-action-opt')].filter(o => o.offsetParent);
        const text = (o) => { const r = document.createRange(); r.selectNodeContents(o.querySelector('.ws-opt-name') || o); return r.getBoundingClientRect(); };
        const pad = (o) => parseFloat(getComputedStyle(o.querySelector('.ws-opt-action')).paddingTop);
        return [opts[0].querySelector('.ws-opt-icon').getBoundingClientRect().left - box.left,
                opts[0].getBoundingClientRect().top + pad(opts[0]) - box.top,
                box.bottom - (opts.at(-1).getBoundingClientRect().bottom - pad(opts.at(-1))),
                box.right - Math.max(...opts.map(o => text(o).right))]; }""")
    assert max(insets) - min(insets) <= 1, insets
