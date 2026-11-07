"""Task Status in the Chat page's Live Office pane: a long goal wraps inside its card.

A goal with an unbroken run (a URL, a path) sized each row's implicit grid
column to that run, so its text ran out past the card's right edge.
"""
import pytest

from tests.test_office_intro_browser import _open

LONG = "Research https://example.com/a/very/long/path/without/any/breaks/whatsoever_and_more and summarise"


def test_a_long_goal_stays_inside_its_task_status_card():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open(pw)
        try:
            page.evaluate("async () => { await switchPanel('chat'); }")
            page.evaluate("() => { if (typeof openWorkspacePanel === 'function') openWorkspacePanel(); switchRightPanelPane('office'); }")
            page.wait_for_function("() => window.HermesOffice && window.HermesOffice.isRunning()", polling=200, timeout=60000)
            page.evaluate("""goal => { window.HermesOffice.onSpawn({subagent_id: 'w1', goal, toolsets: ['web'], run_id: 'r1'});
              window.HermesOffice.onSpawn({subagent_id: 'w2', goal: 'Write code', toolsets: ['terminal'], run_id: 'r1'}); }""", LONG)
            page.wait_for_selector("#workspaceOfficePane .office-tasks-row[data-worker-id='w1']")
            page.click("#workspaceOfficePane .office-tasks-row[data-worker-id='w1'] .office-tasks-row-select")
            page.wait_for_timeout(900)
            out = page.evaluate("""() => [...document.querySelectorAll('#workspaceOfficePane .office-tasks-row')].map(row => {
              const edge = row.getBoundingClientRect().right;
              return [...row.querySelectorAll('*')].filter(e => e.getBoundingClientRect().width > 0)
                .map(e => e.getBoundingClientRect().right - edge).reduce((a, b) => Math.max(a, b), -Infinity); })""")
            assert out and all(over <= 0.5 for over in out), out
        finally:
            browser.close()
