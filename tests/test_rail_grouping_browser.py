"""The left rail's page icons sit in four groups, and the slots do not move.

Work (Dashboard, Chat, Work Hub, Notes, Office) | Automations (Tasks, Jobs) |
Agent setup (Personas, Profiles, Skills, Memory, Knowledge) |
Spaces, then Monitoring (Insights, Logs, Activity). The dividers are re-anchored at boot
by _applyTabOrder(), so this checks the rendered rail, not the HTML.
"""
import pytest

from tests._pytest_port import BASE

EXPECTED = ["dashboard", "chat", "notes", "notebook", "office", "|",
            "tasks", "jobs", "|",
            "agents", "profiles", "skills", "memory", "knowledge", "|",
            "workspaces", "insights", "logs", "audit"]


@pytest.mark.parametrize("viewport", [(1440, 900), (390, 844)])
def test_rendered_rail_groups_pages(viewport):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            page.add_init_script("try { localStorage.removeItem('hermes-webui-tab-order'); } catch (e) {}")
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            orders = page.evaluate("""() => ['.rail', '.sidebar-nav'].map(sel => [...document.querySelector(sel).children]
              .filter(el => (el.dataset.panel && !el.hidden && el.dataset.panel !== 'settings') || /divider/.test(el.className))
              .map(el => el.dataset.panel || '|'))""")
        finally:
            browser.close()
    for order in orders:
        # Kanban is feature-gated; when shown it sits after Work Hub and Notes.
        if "kanban" in order:
            assert order.index("kanban") == order.index("notebook") + 1, order
            order = [panel for panel in order if panel != "kanban"]
        assert order == EXPECTED, order
