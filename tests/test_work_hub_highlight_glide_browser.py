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


def test_to_a_folder_whose_board_is_tucked_away_only_one_highlight_moves(page):
    ids = _make_two_projects(page)
    try:
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.wait_for_timeout(500)
        page.evaluate(_GLIDES, f"[data-board-id='{ids['a2']}']")
        page.wait_for_timeout(500)
        out = page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['b']}']")
        board_shown = page.evaluate("""(id) => { const b = document.querySelector(`.work-hub-board-row.active > button[data-board-id='${id}']`);
            if (!b) return false; const r = b.getBoundingClientRect(), f = b.closest('.work-hub-project-boards').getBoundingClientRect();
            return f.height > r.height * 0.6; }""", ids["b1"])
        assert out["glides"] == (2 if board_shown else 1), (out, board_shown)
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def test_opening_a_folder_selects_its_top_board_and_only_that_board(page):
    ids = _make_two_projects(page)
    try:
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['b']}']")
        page.wait_for_timeout(500)
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.wait_for_timeout(500)
        out = page.evaluate("""() => [...document.querySelectorAll('.work-hub-board-row.active > button[data-board-id]')].map(b => b.dataset.boardId)""")
        assert out == [ids["a1"]], (out, ids)
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def test_at_rest_the_board_highlight_reaches_the_row_edge(page):
    ids = _make_two_projects(page)
    try:
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.mouse.move(5, 5)
        page.wait_for_timeout(500)
        gap = page.evaluate("""() => { const b = document.querySelector('.work-hub-board-row.active > button[data-board-id]');
            const row = b.closest('.work-hub-board-row').getBoundingClientRect();
            return Math.round(row.right - b.getBoundingClientRect().right); }""")
        assert gap <= 1, gap
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def test_opening_a_folder_leaves_one_folder_highlight_and_no_filter_highlight(page):
    ids = _make_two_projects(page)
    try:
        page.evaluate(_CLICK, ".work-hub-scope[data-scope='all']")
        page.wait_for_timeout(500)
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.mouse.move(5, 5)
        page.wait_for_timeout(500)
        out = page.evaluate("""() => ({scopes: [...document.querySelectorAll('.work-hub-scope.active')].length,
            tiles: [...document.querySelectorAll('.work-hub-project-tile.active')].map(t => [t.dataset.scope, getComputedStyle(t).backgroundColor])})""")
        assert out["scopes"] == 0, out
        # The open folder is filled like the other highlights, not outlined.
        assert [t[0] for t in out["tiles"]] == [ids["a"]] and out["tiles"][0][1] != "rgba(0, 0, 0, 0)", out
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])


def test_a_one_board_folder_opens_and_the_highlight_drops_into_its_board(page):
    """A folder with one board opens like any other, then the board highlight
    drops from the folder into the board once the folder has opened."""
    ids = _make_two_projects(page)
    try:
        page.evaluate(_GLIDES, f".work-hub-project-tile[data-scope='{ids['a']}']")
        page.wait_for_timeout(500)
        out = page.evaluate("""async (b) => {
            // Records handed to the callback are gone from takeRecords(), so keep them.
            const copies = records => records.flatMap(m => [...m.addedNodes]).filter(n => n.classList && n.classList.contains('sidebar-highlight-glide'));
            const later = [];
            const seen = new MutationObserver(records => later.push(...copies(records)));
            seen.observe(document.body, {childList: true});
            document.querySelector(`.work-hub-project-tile[data-scope='${b}']`).click();
            const boards = document.getElementById(`workHubFolderBoards-${b}`);
            const atClick = copies(seen.takeRecords()).length;
            const start = await new Promise(resolve => {
                const t = setInterval(() => { if (later[0]) { clearInterval(t); resolve(later[0].getAnimations()[0]?.effect.getKeyframes()[0].transform); } }, 5);
                setTimeout(() => { clearInterval(t); resolve(null); }, 600); });
            seen.disconnect();
            const tile = document.querySelector(`.work-hub-project-tile[data-scope='${b}']`).getBoundingClientRect();
            const board = document.querySelector('.work-hub-board-row.active > button[data-board-id]');
            return {expanded: boards.classList.contains('expanded'), atClick, later: later.length, start,
                    board: board && board.dataset.boardId, below: board ? board.getBoundingClientRect().top > tile.top : false};
        }""", ids["b"])
        assert out["expanded"] and out["board"] == ids["b1"], out
        assert out["atClick"] == 1 and out["later"] == 1, out
        # The copy starts at the folder, above the board: a negative offset.
        assert out["below"] and out["start"].startswith("translateY(-"), out
    finally:
        _drop_projects(page, [ids["a"], ids["b"]])
