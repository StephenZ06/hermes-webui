"""Work Hub's side panel highlight moves the way Chat's does.

The side panel is rebuilt on every click, so its highlight used to jump.
Now it glides from the row it left to the row picked (ui.js
playActiveHighlightGlide), exactly as Chat's does: a project folder only opens
or closes and is never highlighted itself; the highlight is on Inbox / All
Work or on a board inside a folder, and between those two sections it fades
in place instead of travelling across the panel.
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


def test_from_a_filter_to_a_board_it_fades_in_place(page):
    ids = _make_two_projects(page)
    try:
        page.evaluate(_CLICK, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.wait_for_timeout(500)
        page.evaluate(_CLICK, ".work-hub-scope[data-scope='all']")
        page.wait_for_timeout(600)
        out = page.evaluate(_GLIDES, f"[data-board-id='{ids['a1']}']")
        fades = page.evaluate("() => document.querySelector('.work-hub-board-row.active > button').getAnimations().length")
        assert out["glides"] == 0 and fades >= 1, (out, fades)
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def _make_two_projects(page):
    """Project A with two boards and project B with one."""
    return page.evaluate("""async () => {
        const make = async name => (await api('/api/projects/create', {method: 'POST',
            body: JSON.stringify({name, work_hub_managed: true})})).project.project_id;
        const a = await make('Glide A'), b = await make('Glide B');
        let rev = (await api('/api/work_hub/bootstrap')).revision || 0;
        const board = async (name, project_id) => {
            const r = await api('/api/work_hub/boards/create', {method: 'POST',
                body: JSON.stringify({board: {name, project_id}, expected_revision: rev})});
            rev = r.revision || rev; return r.board.id; };
        const a1 = await board('A one', a), a2 = await board('A two', a), b1 = await board('B one', b);
        await loadWorkHubPanel();
        return {a, b, a1, a2, b1};
    }""")


def _drop_projects(page, ids):
    page.evaluate("""async (ids) => { for (const id of ids)
        await api('/api/projects/delete', {method: 'POST', body: JSON.stringify({project_id: id})}); }""", ids)


_GLIDES = """(selector) => {
    const seen = new MutationObserver(() => {});
    seen.observe(document.body, {childList: true});
    document.querySelector(selector).click();
    const glides = seen.takeRecords().flatMap(m => [...m.addedNodes])
        .filter(n => n.classList && n.classList.contains('sidebar-highlight-glide')).length;
    seen.disconnect();
    const button = document.querySelector('.work-hub-board-row.active > button[data-board-id]');
    const nudged = button ? button.getAnimations({subtree: true})
        .filter(a => (a.effect.getKeyframes()[0] || {}).transform?.startsWith('translateX')).length : 0;
    return {glides, nudged};
}"""


def test_board_to_board_moves_only_the_highlight(page):
    ids = _make_two_projects(page)
    try:
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.wait_for_timeout(500)
        page.evaluate(_GLIDES, f"[data-board-id='{ids['a1']}']")
        page.wait_for_timeout(500)
        out = page.evaluate(_GLIDES, f"[data-board-id='{ids['a2']}']")
        assert out == {"glides": 1, "nudged": 0}, out
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def test_a_folder_click_only_opens_and_closes_it(page):
    """As on Chat: the folder opens or closes, nothing is picked and nothing
    glides; the board picked before keeps the highlight."""
    ids = _make_two_projects(page)
    try:
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.wait_for_timeout(500)
        page.evaluate(_GLIDES, f"[data-board-id='{ids['a2']}']")
        page.wait_for_timeout(500)
        tile = f".work-hub-project-tile[data-scope='{ids['b']}']"
        opened = page.evaluate(_GLIDES, tile)
        state = page.evaluate("""(b) => ({open: document.getElementById(`workHubFolderBoards-${b}`).classList.contains('expanded'),
            boards: [...document.querySelectorAll('.work-hub-board-row.active > button[data-board-id]')].map(x => x.dataset.boardId),
            tiles: document.querySelectorAll('.work-hub-project-tile.active').length})""", ids["b"])
        assert opened["glides"] == 0 and state == {"open": True, "boards": [ids["a2"]], "tiles": 0}, (opened, state)
        page.wait_for_timeout(300)
        page.evaluate(_GLIDES, tile)
        shut = page.evaluate("(b) => document.getElementById(`workHubFolderBoards-${b}`).classList.contains('expanded')", ids["b"])
        assert not shut
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def test_between_boards_of_two_folders_the_highlight_glides(page):
    ids = _make_two_projects(page)
    try:
        for target in (f".work-hub-project-tile[data-scope='{ids['a']}']", f".work-hub-project-tile[data-scope='{ids['b']}']", f"[data-board-id='{ids['a2']}']"):
            page.evaluate(_GLIDES, target)
            page.wait_for_timeout(400)
        out = page.evaluate(_GLIDES, f"[data-board-id='{ids['b1']}']")
        assert out["glides"] == 1, out
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def test_at_rest_the_board_highlight_reaches_the_row_edge(page):
    ids = _make_two_projects(page)
    try:
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.wait_for_timeout(400)
        page.evaluate(_GLIDES, f"[data-board-id='{ids['a1']}']")
        page.mouse.move(5, 5)
        page.wait_for_timeout(500)
        gap = page.evaluate("""() => { const b = document.querySelector('.work-hub-board-row.active > button[data-board-id]');
            const row = b.closest('.work-hub-board-row').getBoundingClientRect();
            return Math.round(row.right - b.getBoundingClientRect().right); }""")
        assert gap <= 1, gap
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def test_one_highlight_between_filters_and_boards(page):
    """Picking All Work drops the board highlight (and its board filter);
    picking a board drops the filter highlight. Folders are never filled."""
    ids = _make_two_projects(page)
    try:
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.wait_for_timeout(400)
        page.evaluate(_GLIDES, f"[data-board-id='{ids['a1']}']")
        page.wait_for_timeout(400)
        on_board = page.evaluate("""() => ({scopes: document.querySelectorAll('.work-hub-scope.active').length,
            boards: document.querySelectorAll('.work-hub-board-row.active').length, tiles: document.querySelectorAll('.work-hub-project-tile.active').length})""")
        page.evaluate(_CLICK, ".work-hub-scope[data-scope='all']")
        page.wait_for_timeout(400)
        on_all = page.evaluate("""() => ({scopes: document.querySelectorAll('.work-hub-scope.active').length,
            boards: document.querySelectorAll('.work-hub-board-row.active').length, tiles: document.querySelectorAll('.work-hub-project-tile.active').length})""")
        assert on_board == {"scopes": 0, "boards": 1, "tiles": 0}, on_board
        assert on_all == {"scopes": 1, "boards": 0, "tiles": 0}, on_all
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])
