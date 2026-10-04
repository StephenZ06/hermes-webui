"""Work Hub project folders: one board opens directly, several boards expand.

Clicking a project that holds a single board has nothing to disclose, so it
opens that board instead of expanding; the chevron still reveals the board
row (rename/delete live there). A project with several boards expands.
"""

import json
import urllib.request

import pytest

from tests._pytest_port import BASE


def _call(path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Origin": BASE},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read() or b"{}")


def _revision():
    return _call("/api/work_hub/bootstrap").get("revision")


@pytest.fixture
def two_projects():
    single = _call("/api/projects/create", {"name": "Single board", "work_hub_managed": True})["project"]
    multi = _call("/api/projects/create", {"name": "Many boards", "work_hub_managed": True})["project"]
    board = _call("/api/work_hub/boards/create", {
        "board": {"name": "Only board", "project_id": single["project_id"]}, "expected_revision": _revision(),
    })["board"]
    for name in ("First", "Second"):
        _call("/api/work_hub/boards/create", {
            "board": {"name": name, "project_id": multi["project_id"]}, "expected_revision": _revision(),
        })
    yield single, multi, board
    for project in (single, multi):
        try:
            _call("/api/projects/delete", {"project_id": project["project_id"]})
        except Exception:
            pass


def test_single_board_project_opens_its_board_and_multi_board_project_expands(two_projects):
    sync_api = pytest.importorskip("playwright.sync_api")
    single, multi, board = two_projects
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('notes'); }")
            single_tile = f".work-hub-project-tile[data-project-toggle='{single['project_id']}']"
            multi_tile = f".work-hub-project-tile[data-project-toggle='{multi['project_id']}']"
            page.wait_for_selector(single_tile, timeout=15000)

            page.click(single_tile)
            page.wait_for_function(
                "(id) => document.querySelector(`[data-board-id='${id}']`)?.closest('.work-hub-board-row')?.classList.contains('active')",
                arg=board["id"], polling=100, timeout=10000,
            )
            assert page.get_attribute(single_tile, "aria-expanded") == "false"

            page.click(multi_tile)
            page.wait_for_function(
                "(sel) => document.querySelector(sel)?.getAttribute('aria-expanded') === 'true'",
                arg=multi_tile, polling=100, timeout=10000,
            )

            page.click(f"{single_tile} .work-hub-project-chevron")
            page.wait_for_function(
                "(sel) => document.querySelector(sel)?.getAttribute('aria-expanded') === 'true'",
                arg=single_tile, polling=100, timeout=10000,
            )
        finally:
            browser.close()
