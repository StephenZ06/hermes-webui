"""The conversation filter survives the profile-switch loading skeleton.

The filter box is rendered inside #sessionList (in the workspaces section).
switchToProfile() paints a skeleton by clearing #sessionList, which destroyed
the box: every later sidebar render then read `$('sessionSearch').value` on
null and the switch failed with "Cannot read properties of null".
"""
import pytest

from tests._pytest_port import BASE


def test_filter_box_survives_the_skeleton_and_keeps_its_text():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.wait_for_function("() => document.querySelector('#sessionList #sessionSearch')", timeout=10000)
            state = page.evaluate("""async () => {
              const input = document.getElementById('sessionSearch');
              input.value = 'keep me';
              showSessionListSkeleton();
              const duringSkeleton = !!document.getElementById('sessionSearch');
              let renderError = null;
              try { await renderSessionList(); } catch (e) { renderError = e.message; }
              await new Promise(r => setTimeout(r, 300));
              const after = document.getElementById('sessionSearch');
              const result = {duringSkeleton, renderError, after: !!after, same: after === input,
                              value: after && after.value};
              if (after) { after.value = ''; filterSessions(); }
              return result;
            }""")
        finally:
            browser.close()
    assert state["duringSkeleton"], "the skeleton must not destroy the filter box"
    assert state["renderError"] is None, state["renderError"]
    assert state["after"] and state["same"], "the same filter input is back in the sidebar"
    assert state["value"] == "keep me", "the typed filter survives"
    assert not [e for e in errors if "reading 'value'" in e], errors
