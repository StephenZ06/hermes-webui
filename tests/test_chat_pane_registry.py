"""Chat right-panel pane registry (docs/rfcs/chat-split-view-panes.md, Step 1).

Files/Artifacts/Todos moved from one hardcoded switch function into
registerChatPane() entries with no behavior change; switchWorkspacePanelTab()
is now a delegate to switchRightPanelPane(). Kept in static/workspace.js
itself (not a separate file) because a large number of existing tests build
an isolated page by injecting only workspace.js's source
(page.add_script_tag(content=WORKSPACE_JS)) -- a second file would need its
own script tag added to every one of them.
"""
from pathlib import Path
import shutil

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_JS = (ROOT / "static/workspace.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def browser():
    if sync_playwright is None:
        pytest.skip("Playwright is unavailable")
    with sync_playwright() as playwright:
        if not shutil.which("node") or not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Playwright Chromium is unavailable")
        instance = playwright.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        yield instance
        instance.close()


def _page(browser):
    page = browser.new_page(viewport={"width": 1024, "height": 600})
    page.set_content(
        """
        <aside class="rightpanel">
          <div class="workspace-panel-tabs">
            <button id="workspaceFilesTab"></button>
            <button id="workspaceArtifactsTab"></button>
            <button id="workspaceTodosTab"></button>
            <button id="workspaceCanvasTab"></button>
          </div>
          <section id="workspaceArtifacts" hidden></section>
          <section id="workspaceTodosPanel" hidden></section>
          <section id="workspaceCanvasPane" hidden><div id="workspaceCanvasTree"></div></section>
        </aside>
        """
    )
    page.add_script_tag(
        content="""
        window.S = {session: null, messages: [], toolCalls: []};
        window.$ = id => document.getElementById(id);
        window.esc = value => String(value);
        window.t = key => key;
        window.setStatus = () => {};
        window.openFile = () => {};
        """
    )
    page.add_script_tag(content=WORKSPACE_JS)
    return page


def test_the_built_in_panes_are_registered_on_load(browser):
    page = _page(browser)
    try:
        ids = page.evaluate("() => listChatPanes().map(p => p.id).sort()")
        assert ids == ["artifacts", "canvas", "files", "todos"]
    finally:
        page.close()


def test_switching_calls_mount_and_shows_the_right_content(browser):
    page = _page(browser)
    try:
        # Spy on the registered pane's own mount reference rather than the
        # global renderSessionArtifacts() it normally calls: workspace.js
        # declares that name itself, and a function declaration in a later
        # script tag overwrites an earlier script's assignment of the same
        # global -- so a window.renderSessionArtifacts stub set up before
        # WORKSPACE_JS loads gets silently clobbered back to the real one.
        page.evaluate("""() => {
          window._artifactsMountCount = 0;
          getChatPane('artifacts').mount = () => { window._artifactsMountCount++; };
        }""")
        page.evaluate("() => switchRightPanelPane('artifacts')")
        state = page.evaluate("""() => ({
          artifactsHidden: document.getElementById('workspaceArtifacts').hidden,
          todosHidden: document.getElementById('workspaceTodosPanel').hidden,
          artifactsTabActive: document.getElementById('workspaceArtifactsTab').classList.contains('active'),
          filesTabActive: document.getElementById('workspaceFilesTab').classList.contains('active'),
          artifactsTabSelected: document.getElementById('workspaceArtifactsTab').getAttribute('aria-selected'),
          mountCount: window._artifactsMountCount,
          activeDataset: document.querySelector('.rightpanel').dataset.activeTab,
        })""")
        assert state["artifactsHidden"] is False
        assert state["todosHidden"] is True
        assert state["artifactsTabActive"] is True
        assert state["filesTabActive"] is False
        assert state["artifactsTabSelected"] == "true"
        assert state["mountCount"] == 1
        assert state["activeDataset"] == "artifacts"
    finally:
        page.close()


def test_switching_away_and_back_does_not_remount_stale_panes(browser):
    page = _page(browser)
    try:
        page.evaluate("""() => {
          window._todosMountCount = 0;
          getChatPane('todos').mount = () => { window._todosMountCount++; };
        }""")
        page.evaluate("() => switchRightPanelPane('todos')")
        page.evaluate("() => switchRightPanelPane('files')")
        page.evaluate("() => switchRightPanelPane('todos')")
        count = page.evaluate("() => window._todosMountCount")
        assert count == 2, "todos mounts once per time it becomes active, not on every unrelated switch"
    finally:
        page.close()


def test_an_unknown_pane_id_falls_back_to_files(browser):
    page = _page(browser)
    try:
        page.evaluate("() => switchRightPanelPane('nonexistent-pane')")
        active = page.evaluate("() => document.getElementById('workspaceFilesTab').classList.contains('active')")
        assert active is True
    finally:
        page.close()


def test_leaving_a_pane_calls_its_unmount(browser):
    page = _page(browser)
    try:
        page.evaluate("""() => {
          window._unmountCalls = 0;
          registerChatPane({id: 'test-pane', unmount: () => { window._unmountCalls++; }});
          switchRightPanelPane('test-pane');
          switchRightPanelPane('files');
        }""")
        calls = page.evaluate("() => window._unmountCalls")
        assert calls == 1
    finally:
        page.close()


def test_switchworkspacepaneltab_delegates_to_the_registry(browser):
    page = _page(browser)
    try:
        page.evaluate("() => switchWorkspacePanelTab('artifacts')")
        active = page.evaluate("() => document.getElementById('workspaceArtifactsTab').classList.contains('active')")
        assert active is True
    finally:
        page.close()


# ── Canvas pane (Slice 2) ────────────────────────────────────────────────────

def _install_fake_office_and_canvas(page, workers=None):
    """Stand in for window.HermesOffice (the live adapter) and window.AgentCanvas
    (the renderer) -- neither is loaded in this isolated workspace.js harness."""
    page.evaluate(
        """(workers) => {
          window._renderCalls = [];
          window._unsubscribed = 0;
          window.AgentCanvas = {
            renderStaticTree: (container, opts) => { window._renderCalls.push(opts); },
          };
          window.HermesOffice = {
            getState: () => ({ conductor: { status: 'orchestrating' }, workers }),
            adapter: {
              subscribe: (fn) => { window._officeListener = fn; return () => { window._unsubscribed++; }; },
            },
          };
        }""",
        workers or [],
    )


def test_switching_to_canvas_renders_the_tree_from_the_office_adapter(browser):
    page = _page(browser)
    try:
        _install_fake_office_and_canvas(page, [
            {"id": "s1", "parentId": None, "goal": "Read README", "status": "running",
             "spawnedAt": 1000, "endedAt": None, "toolCount": 2,
             "inputTokens": 10, "outputTokens": 20, "reasoningTokens": 0,
             "apiCalls": 1, "costUsd": 0.01},
        ])
        page.evaluate("() => switchRightPanelPane('canvas')")
        calls = page.evaluate("() => window._renderCalls")
        assert len(calls) == 1
        opts = calls[0]
        assert opts["live"] is True, "a genuinely-running worker must not be shown as interrupted"
        assert opts["parentSessionId"] is None
        assert opts["rootStatus"] == "running"
        assert len(opts["children"]) == 1
        child = opts["children"][0]
        assert child["session_id"] == "s1"
        assert child["parent_session_id"] is None
        assert child["status"] == "running"
        assert child["title"] == "Read README"
    finally:
        page.close()


def test_nested_delegation_keeps_its_real_parent(browser):
    page = _page(browser)
    try:
        _install_fake_office_and_canvas(page, [
            {"id": "s1", "parentId": None, "goal": "top", "status": "running", "spawnedAt": 1000},
            {"id": "s2", "parentId": "s1", "goal": "nested", "status": "running", "spawnedAt": 1001},
        ])
        page.evaluate("() => switchRightPanelPane('canvas')")
        children = page.evaluate("() => window._renderCalls[0].children")
        by_id = {c["session_id"]: c for c in children}
        assert by_id["s1"]["parent_session_id"] is None
        assert by_id["s2"]["parent_session_id"] == "s1"
    finally:
        page.close()


def test_canvas_pane_subscribes_on_mount_and_unsubscribes_on_leave(browser):
    page = _page(browser)
    try:
        _install_fake_office_and_canvas(page, [])
        page.evaluate("() => switchRightPanelPane('canvas')")
        has_listener = page.evaluate("() => typeof window._officeListener === 'function'")
        assert has_listener is True
        page.evaluate("() => switchRightPanelPane('files')")
        unsub_count = page.evaluate("() => window._unsubscribed")
        assert unsub_count == 1
    finally:
        page.close()


def test_a_live_update_re_renders_the_pane_while_mounted(browser):
    page = _page(browser)
    try:
        _install_fake_office_and_canvas(page, [])
        page.evaluate("() => switchRightPanelPane('canvas')")
        before = page.evaluate("() => window._renderCalls.length")
        page.evaluate("() => window._officeListener()")
        after = page.evaluate("() => window._renderCalls.length")
        assert after == before + 1
    finally:
        page.close()
