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
          </div>
          <section id="workspaceArtifacts" hidden></section>
          <section id="workspaceTodosPanel" hidden></section>
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


def test_the_three_built_in_panes_are_registered_on_load(browser):
    page = _page(browser)
    try:
        ids = page.evaluate("() => listChatPanes().map(p => p.id).sort()")
        assert ids == ["artifacts", "files", "todos"]
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
