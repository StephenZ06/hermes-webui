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
            <button id="workspaceOfficeTab"></button>
            <button id="workspacePlaneTab"></button>
          </div>
          <section id="workspaceArtifacts" hidden></section>
          <section id="workspaceTodosPanel" hidden></section>
          <section id="workspaceOfficePane" hidden></section>
          <section id="workspacePlanePane" hidden><div id="workspacePlaneList"></div></section>
          <button id="workspacePreviewTab"></button>
          <section id="workspaceLivePreviewPane" hidden>
            <input id="workspaceLivePreviewUrl">
            <iframe id="workspaceLivePreviewFrame" hidden></iframe>
            <div id="workspaceLivePreviewEmpty"></div>
            <div id="workspaceLivePreviewBlocked" hidden></div>
          </section>
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
        // page.set_content()'s document has an opaque origin -- the real
        // Storage API throws SecurityError on any access. Shim it with a
        // plain in-memory object so localStorage-persistence behavior is
        // still testable; production code already wraps every real call in
        // try/catch for exactly this kind of denied-storage environment
        // (private browsing, sandboxed iframes), so this shim is a test
        // harness concern, not something the app needs to know about.
        (function(){
          const backing = {};
          Object.defineProperty(window, 'localStorage', {
            configurable: true,
            value: {
              getItem: (k) => Object.prototype.hasOwnProperty.call(backing, k) ? backing[k] : null,
              setItem: (k, v) => { backing[k] = String(v); },
              removeItem: (k) => { delete backing[k]; },
              clear: () => { for (const k in backing) delete backing[k]; },
            },
          });
        })();
        """
    )
    page.add_script_tag(content=WORKSPACE_JS)
    return page


def test_the_built_in_panes_are_registered_on_load(browser):
    page = _page(browser)
    try:
        ids = page.evaluate("() => listChatPanes().map(p => p.id).sort()")
        assert ids == ["artifacts", "files", "graph", "office", "plane", "preview", "todos"]
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


# ── Office pane (Slice 2, swapped from a flat Canvas tree to the real
#    HermesOffice 3D scene per explicit follow-up request) ──────────────────

def _install_fake_hermes_office(page):
    """Stand in for window.HermesOffice -- not loaded in this isolated
    workspace.js harness. mount()/unmount() are recorded, not implemented:
    this pane is a thin pass-through by design, so the CONTRACT (which
    container, when unmount is skipped) is what's worth testing here."""
    page.evaluate(
        """() => {
          window._officeMountCalls = [];
          window._officeUnmountCalls = 0;
          window.HermesOffice = {
            mount: (container) => { window._officeMountCalls.push(container.id); },
            unmount: () => { window._officeUnmountCalls++; },
          };
        }"""
    )


def test_mounting_the_office_pane_mounts_the_real_scene(browser):
    page = _page(browser)
    try:
        _install_fake_hermes_office(page)
        page.evaluate("() => switchRightPanelPane('office')")
        calls = page.evaluate("() => window._officeMountCalls")
        assert calls == ["workspaceOfficePane"]
    finally:
        page.close()


def test_leaving_the_office_pane_unmounts_the_scene(browser):
    page = _page(browser)
    try:
        _install_fake_hermes_office(page)
        page.evaluate("() => switchRightPanelPane('office')")
        page.evaluate("() => switchRightPanelPane('files')")
        calls = page.evaluate("() => window._officeUnmountCalls")
        assert calls == 1
    finally:
        page.close()


def test_leaving_the_office_pane_does_not_unmount_if_the_main_office_panel_owns_it(browser):
    page = _page(browser)
    try:
        _install_fake_hermes_office(page)
        page.evaluate("() => switchRightPanelPane('office')")
        # The main Office panel (a separate top-level view, static/panels.js)
        # is now the active one -- it already handles reclaiming the scene
        # via its own mount() call, so this pane's unmount must not race it.
        page.evaluate("() => { window._currentPanel = 'office'; }")
        page.evaluate("() => switchRightPanelPane('files')")
        calls = page.evaluate("() => window._officeUnmountCalls")
        assert calls == 0
    finally:
        page.close()


# ── Plane pane (Slice 3; now a Work Hub view) ─────────────────────────────────
#
# The pane used to render a Kanban board with its own polling. It now mounts
# the Work Hub (static/work-hub.js, not loaded in this harness), which owns
# editing and durable state; unmounting it has nothing to stop.

def test_mounting_plane_renders_the_work_hub(browser):
    page = _page(browser)
    try:
        page.evaluate(
            "() => { window._workHubRenders = 0;"
            " window.renderWorkspaceWorkHub = () => { window._workHubRenders++; }; }"
        )
        page.evaluate("() => switchRightPanelPane('plane')")
        assert page.evaluate("() => window._workHubRenders") == 1
        page.evaluate("() => switchRightPanelPane('files')")
        assert page.evaluate("() => window._workHubRenders") == 1
    finally:
        page.close()


# ── Live preview pane (Slice 4) ──────────────────────────────────────────────

def test_loading_a_url_shows_the_frame_and_persists_it(browser):
    page = _page(browser)
    try:
        page.evaluate("() => { document.getElementById('workspaceLivePreviewUrl').value = 'http://localhost:3000'; loadWorkspaceLivePreview(); }")
        state = page.evaluate("""() => ({
          frameSrc: document.getElementById('workspaceLivePreviewFrame').src,
          frameHidden: document.getElementById('workspaceLivePreviewFrame').hidden,
          emptyHidden: document.getElementById('workspaceLivePreviewEmpty').hidden,
          saved: localStorage.getItem('hermes-webui-livepreview:'),
        })""")
        assert state["frameSrc"] == "http://localhost:3000/"  # DOM normalizes on read
        assert state["frameHidden"] is False
        assert state["emptyHidden"] is True
        assert state["saved"] == "http://localhost:3000"  # the raw string is stored, unnormalized
    finally:
        page.close()


def test_a_bare_host_is_given_an_http_scheme(browser):
    page = _page(browser)
    try:
        page.evaluate("() => { document.getElementById('workspaceLivePreviewUrl').value = 'localhost:5173'; loadWorkspaceLivePreview(); }")
        src = page.evaluate("() => document.getElementById('workspaceLivePreviewFrame').src")
        assert src == "http://localhost:5173/"
    finally:
        page.close()


def test_a_non_http_url_is_rejected(browser):
    page = _page(browser)
    try:
        page.evaluate("() => { document.getElementById('workspaceLivePreviewUrl').value = 'javascript:alert(1)'; loadWorkspaceLivePreview(); }")
        state = page.evaluate("""() => ({
          frameHidden: document.getElementById('workspaceLivePreviewFrame').hidden,
          frameSrc: document.getElementById('workspaceLivePreviewFrame').src,
        })""")
        assert state["frameHidden"] is True
        assert "javascript" not in state["frameSrc"]
    finally:
        page.close()


def test_an_empty_url_shows_the_empty_state(browser):
    page = _page(browser)
    try:
        page.evaluate("() => { document.getElementById('workspaceLivePreviewUrl').value = '  '; loadWorkspaceLivePreview(); }")
        state = page.evaluate("""() => ({
          frameHidden: document.getElementById('workspaceLivePreviewFrame').hidden,
          emptyHidden: document.getElementById('workspaceLivePreviewEmpty').hidden,
        })""")
        assert state["frameHidden"] is True
        assert state["emptyHidden"] is False
    finally:
        page.close()


def test_mounting_restores_the_saved_url_for_the_workspace(browser):
    page = _page(browser)
    try:
        page.evaluate("""() => {
          localStorage.setItem('hermes-webui-livepreview:', 'http://localhost:4000/');
        }""")
        page.evaluate("() => switchRightPanelPane('preview')")
        value = page.evaluate("() => document.getElementById('workspaceLivePreviewUrl').value")
        src = page.evaluate("() => document.getElementById('workspaceLivePreviewFrame').src")
        assert value == "http://localhost:4000/"
        assert src == "http://localhost:4000/"
    finally:
        page.close()


def test_a_csp_violation_shows_the_blocked_message_not_a_blank_frame(browser):
    page = _page(browser)
    try:
        page.evaluate("() => { document.getElementById('workspaceLivePreviewUrl').value = 'http://example.com'; loadWorkspaceLivePreview(); }")
        # Real CSP enforcement needs a live response header this isolated
        # page.set_content() harness cannot send; dispatch the same event the
        # browser would fire on a genuine block to test the handler itself.
        page.evaluate("""() => {
          document.dispatchEvent(new SecurityPolicyViolationEvent('securitypolicyviolation', {
            violatedDirective: 'frame-src', effectiveDirective: 'frame-src', blockedURI: 'http://example.com',
          }));
        }""")
        state = page.evaluate("""() => ({
          frameHidden: document.getElementById('workspaceLivePreviewFrame').hidden,
          blockedHidden: document.getElementById('workspaceLivePreviewBlocked').hidden,
        })""")
        assert state["frameHidden"] is True
        assert state["blockedHidden"] is False
    finally:
        page.close()


def test_a_violation_for_an_unrelated_directive_is_ignored(browser):
    page = _page(browser)
    try:
        page.evaluate("() => { document.getElementById('workspaceLivePreviewUrl').value = 'http://example.com'; loadWorkspaceLivePreview(); }")
        page.evaluate("""() => {
          document.dispatchEvent(new SecurityPolicyViolationEvent('securitypolicyviolation', {
            violatedDirective: 'script-src', effectiveDirective: 'script-src', blockedURI: 'http://evil.example',
          }));
        }""")
        state = page.evaluate("""() => ({
          frameHidden: document.getElementById('workspaceLivePreviewFrame').hidden,
          blockedHidden: document.getElementById('workspaceLivePreviewBlocked').hidden,
        })""")
        assert state["frameHidden"] is False
        assert state["blockedHidden"] is True
    finally:
        page.close()


def test_reload_forces_a_fresh_navigation(browser):
    page = _page(browser)
    try:
        page.evaluate("() => { document.getElementById('workspaceLivePreviewUrl').value = 'http://localhost:3000'; loadWorkspaceLivePreview(); }")
        page.evaluate("() => reloadWorkspaceLivePreview()")
        src = page.evaluate("() => document.getElementById('workspaceLivePreviewFrame').src")
        assert src == "http://localhost:3000/"
    finally:
        page.close()


def test_unmount_blanks_the_frame_and_stops_it_running(browser):
    page = _page(browser)
    try:
        page.evaluate("() => { document.getElementById('workspaceLivePreviewUrl').value = 'http://localhost:3000'; switchRightPanelPane('preview'); }")
        page.evaluate("() => switchRightPanelPane('files')")
        state = page.evaluate("""() => ({
          src: document.getElementById('workspaceLivePreviewFrame').src,
          hidden: document.getElementById('workspaceLivePreviewFrame').hidden,
        })""")
        assert state["src"] == "about:blank"
        assert state["hidden"] is True
    finally:
        page.close()
