"""Notes and Office side panels treat project folders as Chat does.

A folder click only opens or closes the folder; the folder itself is never
highlighted. The highlight is on the note or run picked inside, and moves to
the next one picked with the shared glide (ui.js playActiveHighlightGlide).
"""
import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _api(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            yield page
        finally:
            browser.close()


_GLIDES = """async (selector) => {
    // Opening a note renders the side panel after a fetch, so collect for a while.
    const glides = [];
    const seen = new MutationObserver(records => records.forEach(m => m.addedNodes.forEach(n => {
        if (n.matches && (n.matches('.sidebar-highlight-glide') || n.querySelector('.sidebar-highlight-glide'))) glides.push(n); })));
    seen.observe(document.body, {childList: true});
    document.querySelector(selector).click();
    await new Promise(r => setTimeout(r, 400));
    seen.disconnect();
    return glides.length;
}"""


def test_notes_folder_click_only_opens_it_and_notes_glide(page):
    project = _api("/api/projects/create", {"name": f"Glide {uuid.uuid4().hex[:4]}"})["project"]
    pid = project["project_id"]
    try:
        one = _api("/api/notebook/notes/create", {"title": "Glide one", "project_id": pid})["note"]
        two = _api("/api/notebook/notes/create", {"title": "Glide two", "project_id": pid})["note"]
        page.evaluate("() => { try { localStorage.removeItem('hermes-notebook-last'); } catch (e) {} }")
        page.evaluate("async () => { await switchPanel('notebook'); }")
        tile = f"#notebookSidebar .nb-place-btn[data-nb-id='{pid}']"
        page.wait_for_selector(tile, timeout=15000)
        page.click("[data-nb-scope=general]")
        page.wait_for_timeout(300)
        page.click(tile)
        page.wait_for_timeout(400)
        state = page.evaluate("""(tile) => ({open: document.querySelector(tile).getAttribute('aria-expanded'),
            tiles: document.querySelectorAll('#notebookSidebar .nb-place-btn.active').length,
            general: !!document.querySelector('[data-nb-scope=general].active')})""", tile)
        # Nothing was picked: General keeps the highlight, the folder only opened.
        assert state == {"open": "true", "tiles": 0, "general": True}, state
        page.click(f"#notebookSidebar [data-nb-open='{one['id']}']")
        page.wait_for_function("(id) => document.querySelector(`.nb-tree-note.active [data-nb-open='${id}']`)", arg=one["id"], timeout=10000)
        page.wait_for_timeout(500)
        glides = page.evaluate(_GLIDES, f"#notebookSidebar [data-nb-open='{two['id']}']")
        page.wait_for_function("(id) => document.querySelector(`.nb-tree-note.active [data-nb-open='${id}']`)", arg=two["id"], timeout=10000)
        active = page.evaluate("() => [...document.querySelectorAll('#notebookSidebar .nb-tree-note.active, #notebookSidebar .nb-scope.active, #notebookSidebar .nb-place-btn.active')].length")
        assert glides == 1 and active == 1, (glides, active)
    finally:
        _api("/api/projects/delete", {"project_id": pid})


def test_office_runs_in_a_folder_glide_and_the_folder_is_never_highlighted(page):
    pid = f"glide{uuid.uuid4().hex[:6]}"
    parents = [{"parent_session_id": f"run{i}", "title": f"Run {i}", "project_id": pid, "children": []} for i in (1, 2)]
    page.route("**/api/agent-canvas/sessions*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"parents": parents})))
    page.route("**/api/projects?all_profiles=1", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"projects": [{"project_id": pid, "name": "Glide office"}]})))
    try:
        page.evaluate("async () => { await switchPanel('office'); }")
        folder = f".office-project-folder[data-project-id='{pid}']"
        page.wait_for_selector(folder, timeout=20000)
        page.click(folder)
        page.wait_for_timeout(400)
        page.click(".office-session-row[data-parent-id='run1']")
        page.wait_for_timeout(500)
        glides = page.evaluate(_GLIDES, ".office-session-row[data-parent-id='run2']")
        out = page.evaluate("""() => ({active: [...document.querySelectorAll('.office-session-row.is-active')].map(r => r.dataset.parentId),
            folders: document.querySelectorAll('.office-project-folder.active').length,
            fill: getComputedStyle(document.querySelector('.office-session-row.is-active')).backgroundColor})""")
        assert glides == 1 and out["active"] == ["run2"] and out["folders"] == 0, (glides, out)
    finally:
        page.evaluate("async () => { await switchPanel('chat'); }")


@pytest.mark.parametrize("panel", ["notes", "notebook"])
def test_picking_far_down_the_side_panel_keeps_its_scroll(page, panel):
    """The side panel's nav is rebuilt on every pick; it used to start back at
    the top, so a board or note picked far down jumped out of sight."""
    ids = page.evaluate("""async () => { const ids = [];
        for (let i = 0; i < 14; i++) ids.push((await api('/api/projects/create', {method: 'POST', body: JSON.stringify({name: 'Deep ' + i, work_hub_managed: true})})).project.project_id);
        const rev = (await api('/api/work_hub/bootstrap')).revision || 0;
        const board = (await api('/api/work_hub/boards/create', {method: 'POST', body: JSON.stringify({board: {name: 'Deep board', project_id: ids[13]}, expected_revision: rev})})).board.id;
        const note = (await api('/api/notebook/notes/create', {method: 'POST', body: JSON.stringify({title: 'Deep note', project_id: ids[13]})})).note.id;
        return {ids, board, note}; }""")
    try:
        page.set_viewport_size({"width": 1400, "height": 600})
        page.evaluate(f"async () => {{ await switchPanel('{panel}'); }}")
        last = ids["ids"][13]
        tile = (f".work-hub-project-tile[data-scope='{last}']" if panel == "notes"
                else f"#notebookSidebar .nb-place-btn[data-nb-id='{last}']")
        pick = f"[data-board-id='{ids['board']}']" if panel == "notes" else f"#notebookSidebar [data-nb-open='{ids['note']}']"
        nav = "#workHubSidebar .work-hub-nav" if panel == "notes" else "#notebookSidebar .nb-nav"
        page.wait_for_selector(tile, state="attached", timeout=15000)
        page.evaluate(f"""() => {{ const nav = document.querySelector("{nav}"); nav.scrollTop = nav.scrollHeight;
            document.querySelector("{tile}").click(); }}""")
        page.wait_for_timeout(400)
        before = page.evaluate(f"() => document.querySelector(\"{nav}\").scrollTop")
        page.evaluate(f"() => document.querySelector(\"{pick}\").click()")
        page.wait_for_timeout(800)
        after = page.evaluate(f"() => document.querySelector(\"{nav}\").scrollTop")
        assert before > 100 and abs(after - before) <= 2, (before, after)
    finally:
        page.evaluate("async (ids) => { for (const id of ids) await api('/api/projects/delete', {method: 'POST', body: JSON.stringify({project_id: id})}); }", ids["ids"])
