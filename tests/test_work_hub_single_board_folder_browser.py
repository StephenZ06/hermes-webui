"""Work Hub project folders open and close the same way, one board or many.

As on Chat, clicking a folder only opens or closes it -- a folder holding a
single board no longer jumps straight to that board -- and the board picked
inside is what the board view shows.
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


def test_every_folder_opens_and_closes_and_its_board_is_picked_inside(two_projects):
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

            for tile in (single_tile, multi_tile):
                page.click(tile)
                assert page.get_attribute(tile, "aria-expanded") == "true"
            # Opening picked nothing.
            assert page.evaluate("() => document.querySelectorAll('.work-hub-board-row.active').length") == 0

            page.click(f"[data-board-id='{board['id']}']")
            page.wait_for_function(
                "(id) => document.querySelector(`[data-board-id='${id}']`)?.closest('.work-hub-board-row')?.classList.contains('active')",
                arg=board["id"], polling=100, timeout=10000,
            )
            page.click(single_tile)
            assert page.get_attribute(single_tile, "aria-expanded") == "false"
        finally:
            browser.close()
