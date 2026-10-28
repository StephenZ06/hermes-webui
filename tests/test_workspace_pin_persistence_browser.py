"""A pinned workspace panel stays beside the chat: pages that need the whole
surface (Work Hub, Notes, Files) put it away, and the chat brings it back."""
import pytest

from tests._pytest_port import BASE

STATE = """() => [_workspacePanelMode !== 'closed', document.documentElement.dataset.workspacePinned === '1',
    Math.round(document.querySelector('.rightpanel').getBoundingClientRect().width) > 200]"""


def _boot(page):
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")


def test_pinned_split_view_comes_back_with_the_chat():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1400, "height": 860}).new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            _boot(page)
            page.evaluate("() => { toggleWorkspacePanel(true); toggleWorkspacePin(true); }")
            page.wait_for_timeout(800)
            seen = {}
            for name in ("notes", "chat", "files", "dashboard", "notebook", "chat"):
                page.evaluate(f"() => switchPanel('{name}')")
                page.wait_for_timeout(600)
                seen.setdefault(name, []).append(page.evaluate(STATE))
            page.evaluate("() => switchPanel('notes')")
            page.wait_for_timeout(300)
            page.reload(wait_until="domcontentloaded")
            _boot(page)
            page.evaluate("() => switchPanel('chat')")
            page.wait_for_timeout(600)
            after_reload = page.evaluate(STATE)
        finally:
            browser.close()
    assert [s[:2] for s in seen["notes"] + seen["files"]] == [[False, True]] * 2, seen  # these take the whole surface
    assert seen["chat"] == [[True, True, True]] * 2, seen       # the chat gets its split view back, side by side
    assert seen["dashboard"][0][:2] == [True, True], seen
    assert after_reload == [True, True, True], after_reload     # even after a reload on Work Hub
