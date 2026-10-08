"""Final UI check: rail icons appear together, Spaces sits above Insights, the
chat Workspace panel has a Notes tab whose labels give way to icons when narrow,
Scout cards close the gap left by a deleted search, and the Jobs Settings menu
lines up with its pane."""

import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read() or b"{}")


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            yield tab
            assert not errors, errors
        finally:
            browser.close()


def test_rail_icons_show_together_and_spaces_sits_above_insights(page):
    page.wait_for_function("() => !document.documentElement.classList.contains('nav-marks-pending')", timeout=5000)
    order = page.eval_on_selector_all(".rail .nav-tab[data-panel]", "els => els.map(e => e.dataset.panel)")
    assert order.index("workspaces") == order.index("insights") - 1
    side = page.eval_on_selector_all(".sidebar-nav .nav-tab[data-panel]", "els => els.map(e => e.dataset.panel)")
    assert side.index("workspaces") == side.index("insights") - 1


def test_workspace_panel_notes_tab_lists_notes_and_opens_one(page):
    title = f"Workspace note {uuid.uuid4().hex[:6]}"
    _post("/api/notebook/notes/create", {"title": title})
    page.evaluate("async () => { toggleWorkspacePanel(true); }")
    page.wait_for_selector("#workspaceNotesTab", state="visible", timeout=10000)
    page.evaluate("() => switchWorkspacePanelTab('notes')")
    row = page.wait_for_selector(f".workspace-nb-note:has-text('{title}')", timeout=10000)
    # Narrow panel: icons only; wide panel: icons and labels.
    page.evaluate("() => { document.querySelector('.rightpanel').style.width = '300px'; }")
    page.wait_for_function("() => document.querySelector('.workspace-panel-tabs').classList.contains('is-compact')", timeout=5000)
    page.evaluate("() => { document.querySelector('.rightpanel').style.width = '640px'; }")
    page.wait_for_function("() => !document.querySelector('.workspace-panel-tabs').classList.contains('is-compact')", timeout=5000)
    row.click()
    page.wait_for_function("(t) => document.getElementById('nbTitle') && document.getElementById('nbTitle').value === t",
                           arg=title, timeout=30000)


def test_deleting_a_scout_search_keeps_the_other_cards(page):
    marker = uuid.uuid4().hex[:6]
    ids = [_post("/api/job-os/searches", {"search": {"name": f"{marker} {n}", "keywords": f"Analyst {n}", "country": "MY",
                                                      "sites": ["indeed"], "locations": []}})["search"]["id"] for n in range(3)]
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.evaluate("() => { location.hash = '#jobs/scout'; }")
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_selector(f".scout-search[data-search-id='{ids[2]}']", timeout=15000)
    page.evaluate("(ids) => ids.forEach((id) => { document.querySelector(`.scout-search[data-search-id='${id}']`)._kept = id; })", ids[1:])
    button = f".scout-search[data-search-id='{ids[0]}'] [data-job-os-action='scout-delete']"
    page.click(button)
    page.click(button)  # the in-place confirm
    page.wait_for_function("(id) => !document.querySelector(`.scout-search[data-search-id='${id}']`)", arg=ids[0], timeout=10000)
    page.wait_for_timeout(1200)  # the refresh that follows the delete
    kept = page.evaluate("(ids) => ids.map((id) => { const el = document.querySelector(`.scout-search[data-search-id='${id}']`); return !!el && el._kept === id; })", ids[1:])
    assert kept == [True, True], "the other searches stay on the page as the same cards"


def test_jobs_settings_menu_lines_up_with_its_pane(page):
    page.evaluate("() => { location.hash = '#jobs/settings'; }")
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_selector("#jobOsRoot .settings-nav", timeout=15000)
    page.wait_for_timeout(600)  # the pane's slide-in
    tops = page.evaluate("() => ['.settings-nav', '.settings-page'].map((s) => Math.round(document.querySelector('#jobOsRoot ' + s).getBoundingClientRect().top))")
    assert tops[0] == tops[1]
