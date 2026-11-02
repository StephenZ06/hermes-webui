"""A profile-switch skeleton never waits on the pointer.

Opening a chat from another profile (for example inside a project folder,
with "show all profiles" on) switches profile first, which replaces the
sidebar with a loading skeleton. A refresh queued behind the switch's own
render, such as the one loadSession() asks for, supersedes it; that refresh
defers its payload while the pointer is over the list, so the skeleton stayed
up for as long as the pointer rested on the sidebar and the project folders
looked empty.
"""
import pytest

from tests._pytest_port import BASE


def test_skeleton_is_replaced_while_the_pointer_rests_on_the_list():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.wait_for_function("() => document.querySelector('#sessionList #sessionSearch')", timeout=10000)
            box = page.evaluate("() => { const r = document.getElementById('sessionList').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
            page.mouse.move(*box)
            state = page.evaluate("""async () => {
              showSessionListSkeleton();
              const hovered = document.getElementById('sessionList').matches(':hover');
              const own = renderSessionList();
              const queued = renderSessionList({deferWhileInteracting: true});
              await Promise.all([own, queued]);
              await new Promise(r => setTimeout(r, 1500));
              return {hovered, skeleton: _sessionListSkeletonActive,
                      skeletonRows: document.querySelectorAll('#sessionList .session-skeleton-row, #sessionList [class*=skeleton]').length};
            }""")
        finally:
            browser.close()
    assert state["hovered"], state
    assert state["skeleton"] is False, state
    assert state["skeletonRows"] == 0, state
