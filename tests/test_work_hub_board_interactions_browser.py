"""Work Hub board: panning, the picked item's outline, and no flicker.

- Pressing on empty board space and dragging sideways pans the board, and
  sweeping across the board never selects text.
- The picked work item is outlined in its column's colour.
- Switching boards does not replay the empty details panel's entrance, and
  switching items keeps the panel's labels still: only changed values fade.
"""
import pytest

from tests._pytest_port import BASE


@pytest.fixture
def board():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1400, "height": 700})
        ids = None
        try:
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            ids = page.evaluate("""async () => { await switchPanel('notes');
                const a = (await api('/api/projects/create', {method: 'POST', body: JSON.stringify({name: 'Board feel', work_hub_managed: true})})).project.project_id;
                let rev = (await api('/api/work_hub/bootstrap')).revision || 0;
                const bd = async n => { const r = await api('/api/work_hub/boards/create', {method: 'POST', body: JSON.stringify({board: {name: n, project_id: a}, expected_revision: rev})}); rev = r.revision || rev; return r.board.id; };
                const b1 = await bd('Full'), b2 = await bd('Empty');
                for (let i = 0; i < 14; i++) { const r = await api('/api/work_hub/items/create', {method: 'POST', body: JSON.stringify({item: {title: 'Card ' + i, board_id: b1, project_id: a, status: 'triage', description: 'About ' + i}, expected_revision: rev})}); rev = r.revision || rev; }
                await loadWorkHubPanel(); return {a, b1, b2}; }""")
            page.click(f".work-hub-project-tile[data-scope='{ids['a']}']")
            page.wait_for_timeout(300)
            page.click(f"[data-board-id='{ids['b1']}']")
            page.wait_for_function("() => document.querySelectorAll('.work-hub-card').length === 14", timeout=10000)
            page.wait_for_timeout(700)
            yield page, ids
        finally:
            if ids:
                page.evaluate("(id) => api('/api/projects/delete', {method: 'POST', body: JSON.stringify({project_id: id})})", ids["a"])
            browser.close()


def test_dragging_empty_board_space_pans_it_sideways_without_selecting(board):
    page, _ = board
    page.set_viewport_size({"width": 1100, "height": 700})
    page.wait_for_function("() => document.querySelector('.work-hub-board-wrap').classList.contains('can-pan')", timeout=5000)
    # The empty part of the (empty) Backlog column, near the board's right edge.
    spot = page.evaluate("""() => { const wrap = document.querySelector('.work-hub-board-wrap').getBoundingClientRect();
        const col = document.querySelector(".work-hub-column[data-status='backlog']").getBoundingClientRect();
        return [Math.min(col.right, wrap.right) - 30, col.top + 200]; }""")
    assert page.evaluate("([x, y]) => !!document.elementFromPoint(x, y).closest('.work-hub-column[data-status=backlog]')", spot)
    page.mouse.move(*spot)
    page.mouse.down()
    page.mouse.move(spot[0] - 150, spot[1] + 10, steps=6)
    page.mouse.up()
    out = page.evaluate("""() => ({left: document.querySelector('.work-hub-board-wrap').scrollLeft, selected: String(window.getSelection())})""")
    assert out["left"] >= 140 and out["selected"] == "", out


def test_the_picked_item_is_outlined_in_its_columns_colour(board):
    page, _ = board
    page.click(".work-hub-card >> nth=2")
    page.mouse.move(5, 5)
    page.wait_for_timeout(300)
    out = page.evaluate("""() => { const card = document.querySelector('.work-hub-card.is-selected');
        const probe = document.createElement('i'); probe.style.color = 'var(--stage)'; card.closest('.work-hub-column').appendChild(probe);
        const accent = getComputedStyle(probe).color; probe.remove();
        return {count: document.querySelectorAll('.work-hub-card.is-selected').length, border: card && getComputedStyle(card).borderTopColor,
                ring: card && getComputedStyle(card).boxShadow, accent}; }""")
    # A plain 1px outline: no extra ring around it.
    assert out["count"] == 1 and out["border"] == out["accent"] and out["ring"] == "none", out


def test_switching_boards_keeps_the_empty_details_panel_still(board):
    page, ids = board
    page.click(f"[data-board-id='{ids['b2']}']")
    page.wait_for_selector(".work-hub-inspector-empty")
    assert page.evaluate("() => document.querySelector('.work-hub-inspector-empty').getAnimations().length") == 0


def test_switching_items_fades_only_the_values_that_change(board):
    page, _ = board
    page.click(".work-hub-card >> nth=0")
    page.wait_for_timeout(500)
    page.click(".work-hub-card >> nth=1")
    out = page.evaluate("""() => { const panel = document.getElementById('workHubInspector');
        const moving = node => node ? node.getAnimations().length : -1;
        return {panel: moving(panel.querySelector('.wh-insp')), kicker: moving(panel.querySelector('.wh-insp-kicker')),
                labels: [...panel.querySelectorAll('.wh-insp-prop dt')].map(moving).reduce((a, b) => a + b, 0),
                status: moving(panel.querySelector('#workHubStatus').closest('dd')),
                title: moving(panel.querySelector('#workHubTitle')), description: moving(panel.querySelector('#workHubDescription')),
                // The field's box stays still: only its text (colour) animates, never its opacity.
                titleBox: panel.querySelector('#workHubTitle').getAnimations().flatMap(a => a.effect.getKeyframes()).some(k => 'opacity' in k || 'filter' in k)}; }""")
    assert out["panel"] == 0 and out["kicker"] == 0 and out["labels"] == 0 and out["status"] == 0, out
    assert out["title"] >= 1 and out["description"] >= 1 and out["titleBox"] is False, out
