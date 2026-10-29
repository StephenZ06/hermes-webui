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
            if (/^Refinements/.test(project.name)) await api('/api/projects/delete', {method: 'POST', body: JSON.stringify({project_id: project.project_id})});
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
                return {columns: moving('.work-hub-column'), cards: moving('.work-hub-card'), rows: moving('.work-hub-list-row'),
                    leaving: document.querySelectorAll('.list-item-leaving').length}; }"""
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
    assert scope["columns"] == 0 and scope["leaving"] > 0, scope   # scope: the items change, the columns stay
    totals = [total for total, _ in counted]
    steps = [b - a for a, b in zip(totals, totals[1:]) if b != a]
    assert len(set(totals)) > 2 and (all(v < 0 for v in steps) or all(v > 0 for v in steps)), totals  # the count runs, one way
    assert all(fading == 0 for _, fading in counted), counted    # the count badges themselves stay still
    assert to_list["rows"] > 0, to_list
    assert to_board["columns"] > 0, to_board                      # view: the whole board comes in


def test_clicking_into_a_new_items_fields_keeps_the_panel():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = None
        try:
            page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
            _open_work_hub(page)
            page.evaluate("""() => { window.__rebuilds = 0;
                new MutationObserver(records => { for (const r of records) for (const n of r.removedNodes)
                    if (n.nodeType === 1 && (n.matches('.wh-insp') || n.querySelector('.wh-insp'))) window.__rebuilds++; })
                    .observe(document.getElementById('workHub'), {childList: true, subtree: true}); }""")
            page.click("#workHubCreate")
            page.wait_for_selector("#workHubTitle")
            page.wait_for_timeout(400)
            page.evaluate("() => { window.__rebuilds = 0; }")
            page.click("#workHubTitle")
            page.keyboard.type("Clicked")
            for selector in ("#workHubDescription", "#workHubTitle", "#workHubDescription"):
                if page.query_selector(selector):
                    page.click(selector)
                    page.wait_for_timeout(300)
            page.wait_for_timeout(3500)
            after = page.evaluate("() => [window.__rebuilds, document.getElementById('workHubTitle').value]")
        finally:
            try:
                if page is not None:
                    _clean_up(page)
            finally:
                browser.close()
    assert after == [0, "Clicked"], after   # clicking between fields never rebuilds the open panel


def test_scope_change_keeps_shared_items_and_animates_only_the_difference():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = None
        try:
            page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
            _open_work_hub(page)
            # Each card or row is classed by what its animation does: a glide (transform only), an entrance (opacity).
            probe = """() => { const out = {shared: 0, glide: 0, enter: 0, fadeShared: 0, leaving: document.querySelectorAll('.list-item-leaving').length};
                const before = window.__before || new Set();
                document.querySelectorAll('#workHubCanvas [data-item-id]').forEach(n => {
                    const fades = n.getAnimations().some(a => a.effect.getKeyframes().some(k => 'opacity' in k));
                    const moves = n.getAnimations().some(a => a.effect.getKeyframes().some(k => 'transform' in k && !('opacity' in k)));
                    if (before.has(n.dataset.itemId)) { out.shared++; if (fades) out.fadeShared++; if (moves) out.glide++; }
                    else if (fades) out.enter++; });
                return out; }"""
            remember = "() => { window.__before = new Set([...document.querySelectorAll('#workHubCanvas [data-item-id]')].map(n => n.dataset.itemId)); }"
            results = {}
            for view in ("board", "list"):
                page.click(f"[data-view='{view}']")
                page.click(".work-hub-scope[data-scope='all']")
                page.wait_for_timeout(700)
                page.evaluate(remember)
                page.click(".work-hub-scope[data-scope='inbox']")
                narrowing = page.evaluate(probe)
                page.wait_for_timeout(700)
                page.evaluate(remember)
                page.click(".work-hub-scope[data-scope='all']")
                widening = page.evaluate(probe)
                page.wait_for_timeout(700)
                results[view] = (narrowing, widening, page.evaluate("() => document.querySelectorAll('.list-item-leaving').length"))
        finally:
            try:
                if page is not None:
                    _clean_up(page)
            finally:
                browser.close()
    for view, (narrowing, widening, left_over) in results.items():
        # All work -> Inbox: the Inbox items stay (no fade), the project items leave.
        assert narrowing["shared"] > 0 and narrowing["fadeShared"] == 0 and narrowing["leaving"] > 0, (view, narrowing)
        # Inbox -> All work: the Inbox items stay, only the project items come in.
        assert widening["fadeShared"] == 0 and widening["enter"] > 0, (view, widening)
        assert left_over == 0, view   # the leaving copies are gone once they have faded


def test_switching_projects_keeps_each_columns_cards_and_changes_only_their_text():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = None
        try:
            page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
            _open_work_hub(page)
            # Project A: 2 backlog items. Project B: 5 backlog items. Nothing shared.
            page.evaluate("""async () => {
                let rev = (await api('/api/work_hub/bootstrap')).revision || 0;
                for (const [name, n] of [['Refinements A', 2], ['Refinements B', 5]]) {
                    const project = (await api('/api/projects/create', {method: 'POST', body: JSON.stringify({name, work_hub_managed: true})})).project;
                    for (let i = 0; i < n; i++) rev = (await api('/api/work_hub/items/create', {method: 'POST', body: JSON.stringify({item: {title: 'Refinement ' + name.slice(-1) + i, status: 'backlog', project_id: project.project_id}, expected_revision: rev})})).revision;
                }
                await switchPanel('chat'); await switchPanel('notes'); }""")
            page.wait_for_selector(".work-hub-project-tile", timeout=10000)
            # A folder only opens and closes (as on Chat); its Default board,
            # which the items were filed on, switches the project.
            pick = """(name) => { const tile = [...document.querySelectorAll('.work-hub-project-tile')].find(t => t.textContent.includes(name));
                if (tile.getAttribute('aria-expanded') !== 'true') tile.click();
                tile.nextElementSibling.querySelector('[data-board-id]').click(); }"""
            probe = """() => { const cards = [...document.querySelectorAll('#workHubCanvas .work-hub-column[data-status="backlog"] .work-hub-card')];
                const fades = n => n.getAnimations().some(a => a.effect.getKeyframes().some(k => 'opacity' in k));
                return {cards: cards.length, cardFades: cards.filter(fades).length,
                        textFades: cards.filter(c => !fades(c) && [...c.children].some(fades)).length,
                        leaving: document.querySelectorAll('.list-item-leaving').length}; }"""
            page.evaluate(pick, "Refinements A")
            page.wait_for_timeout(700)
            page.evaluate(pick, "Refinements B")
            growing = page.evaluate(probe)
            page.wait_for_timeout(700)
            page.evaluate(pick, "Refinements A")
            shrinking = page.evaluate(probe)
        finally:
            try:
                if page is not None:
                    _clean_up(page)
            finally:
                browser.close()
    # A (2) -> B (5): the 2 cards stay and change their text; 3 come in.
    assert growing == {"cards": 5, "cardFades": 3, "textFades": 2, "leaving": 0}, growing
    # B (5) -> A (2): the 2 stay and change their text; 3 leave.
    assert shrinking == {"cards": 2, "cardFades": 0, "textFades": 2, "leaving": 3}, shrinking


def test_list_rows_match_the_board_columns_status_colour_and_label():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = None
        try:
            page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
            _open_work_hub(page)
            page.click(".work-hub-scope[data-scope='all']")
            board = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#workHubCanvas .work-hub-column')].map(c =>
                [c.dataset.status, [getComputedStyle(c.querySelector('header .work-hub-status')).backgroundColor, c.querySelector('header strong').textContent.trim()]]))""")
            page.click("[data-view='list']")
            page.wait_for_selector(".work-hub-list-row")
            rows = page.evaluate("""() => [...document.querySelectorAll('.work-hub-list-row')].map(r => {
                const dot = r.querySelector('.work-hub-status'); const status = [...dot.classList].find(c => c.startsWith('status-')).slice(7);
                return [status, getComputedStyle(dot).backgroundColor, r.querySelector('small').textContent.trim()]; })""")
        finally:
            try:
                if page is not None:
                    _clean_up(page)
            finally:
                browser.close()
    assert {status for status, _, _ in rows} >= {"triage", "backlog", "todo"}, rows
    for status, colour, label in rows:
        assert [colour, label] == board[status], (status, colour, label, board[status])
