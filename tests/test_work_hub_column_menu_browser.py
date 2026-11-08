"""Work Hub column menu: the chevron in a column header opens Filter, Select
and Delete. Select picks cards to move or delete together; Delete deletes the
card tapped. Project folders without boards still open, saying so."""

import json
import time
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _post(path, body):
    req = urllib.request.Request(BASE + path, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def _bootstrap():
    return json.loads(urllib.request.urlopen(BASE + "/api/work_hub/bootstrap", timeout=10).read())


@pytest.fixture()
def seeded():
    tag = uuid.uuid4().hex[:6]
    project = _post("/api/projects/create", {"name": f"Menu {tag}", "work_hub_managed": True})["project"]["project_id"]
    board = _post("/api/work_hub/boards/create", {"board": {"name": f"Board {tag}", "project_id": project}, "expected_revision": _bootstrap()["revision"]})["board"]["id"]
    ids = []
    for n in range(3):
        ids.append(_post("/api/work_hub/items/create", {"item": {"title": f"Card {n} {tag}", "status": "triage", "project_id": project, "board_id": board}, "expected_revision": _bootstrap()["revision"]})["item"]["id"])
    empty = _post("/api/projects/create", {"name": f"Empty {tag}", "work_hub_managed": True})["project"]["project_id"]
    yield {"tag": tag, "project": project, "board": board, "ids": ids, "empty": empty}
    for pid in (project, empty):
        try:
            _post("/api/projects/delete", {"project_id": pid})
        except Exception:
            pass


@pytest.fixture()
def page(seeded):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('notes'); }")
            page.wait_for_selector(f".work-hub-project-tile[data-project-toggle='{seeded['project']}']", timeout=15000)
            page.click(f".work-hub-project-tile[data-project-toggle='{seeded['project']}']")
            page.click(f"[data-board-id='{seeded['board']}']")
            page.wait_for_function("(n) => document.querySelectorAll('.work-hub-column[data-status=triage] .work-hub-card').length === n", arg=3, timeout=10000)
            yield page
        finally:
            browser.close()


def _card(item_id):
    return f".work-hub-card[data-item-id='{item_id}']"


def _open_menu(page, status):
    page.click(f"[data-column-menu='{status}']")
    page.wait_for_selector(".work-hub-column-menu:not(.is-leaving)", timeout=5000)


def test_the_column_menu_offers_filter_select_and_delete(page):
    _open_menu(page, "triage")
    labels = page.evaluate("() => [...document.querySelectorAll('.work-hub-column-menu [data-col-action]')].map(b => b.textContent.trim())")
    assert labels == ["Filter", "Select", "Delete"]
    assert page.get_attribute("[data-column-menu='triage']", "aria-expanded") == "true"
    page.click(".work-hub-column-menu [data-col-action=filter]")
    page.wait_for_selector("[data-board-filter-query='triage']", timeout=5000)


def test_picked_cards_move_together_to_another_column(page, seeded):
    _open_menu(page, "triage")
    page.click(".work-hub-column-menu [data-col-action=select]")
    page.wait_for_selector(".work-hub-column[data-status=triage].is-select-mode .dm-wiggle", timeout=5000)
    first, second, third = seeded["ids"]
    # A tap picks a card instead of opening it.
    page.click(_card(first), force=True)
    page.click(_card(second), force=True)
    assert page.evaluate("() => document.querySelector('.work-hub').classList.contains('has-selection')") is False
    assert page.inner_text("[data-col-count]") == "2 selected"
    page.click("[data-col-move]")
    page.click(".work-hub-move-menu [data-move-to=todo]")
    page.wait_for_function("() => !document.querySelector('.is-in-mode')", timeout=10000)
    statuses = {row["id"]: row["status"] for row in _bootstrap()["items"]}
    assert (statuses[first], statuses[second], statuses[third]) == ("todo", "todo", "triage")
    assert page.evaluate(f"() => !!document.querySelector(\".work-hub-column[data-status=todo] {_card(first)}\")")


def test_picked_cards_are_deleted_together(page, seeded):
    _open_menu(page, "triage")
    page.click(".work-hub-column-menu [data-col-action=select]")
    page.wait_for_selector(".is-select-mode .dm-wiggle", timeout=5000)
    first, second, third = seeded["ids"]
    page.click(_card(first), force=True)
    page.click(_card(third), force=True)
    page.click("[data-col-delete-picked]")
    page.click("#appDialogConfirm", timeout=5000)
    page.wait_for_function("() => !document.querySelector('.is-in-mode')", timeout=10000)
    left = {row["id"] for row in _bootstrap()["items"]}
    assert first not in left and third not in left and second in left


def test_delete_mode_deletes_the_tapped_card_and_escape_leaves_it(page, seeded):
    _open_menu(page, "triage")
    page.click(".work-hub-column-menu [data-col-action=delete]")
    page.wait_for_selector(".is-delete-mode .work-hub-card.dm-item", timeout=5000)
    first = seeded["ids"][0]
    page.click(_card(first), force=True)
    page.click("#appDialogConfirm", timeout=5000)
    page.wait_for_function("(id) => !document.querySelector(`.work-hub-card[data-item-id='${id}']`)", arg=first, timeout=10000)
    assert first not in {row["id"] for row in _bootstrap()["items"]}
    assert page.evaluate("() => !!document.querySelector('.is-delete-mode')")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('.is-in-mode')", timeout=5000)
    assert page.evaluate("() => document.querySelectorAll('.work-hub-card.dm-wiggle').length") == 0


def test_a_folder_without_boards_opens_and_says_so(page, seeded):
    tile = f".work-hub-project-tile[data-project-toggle='{seeded['empty']}']"
    page.click(tile)
    assert page.get_attribute(tile, "aria-expanded") == "true"
    note = page.locator(f"#workHubFolderBoards-{seeded['empty']} .work-hub-board-empty")
    note.wait_for(state="visible", timeout=5000)
    assert note.inner_text() == "No board yet"
