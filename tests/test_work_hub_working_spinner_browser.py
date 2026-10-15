"""A chat working on a Work Hub item shows a spinner: on the item's card (picked
up by the board's refresh, since the chat changes items server-side) and in
the chat's running footer, with readable work_hub tool labels."""

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


def _rev():
    return json.loads(urllib.request.urlopen(BASE + "/api/work_hub/bootstrap", timeout=10).read())["revision"]


@pytest.fixture()
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_context(viewport={"width": 1280, "height": 860}).new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            yield page
        finally:
            browser.close()


def test_a_card_spins_while_a_chat_works_on_it_and_stops_after(page):
    title = f"Spin {uuid.uuid4().hex[:5]}"
    item_id = _post("/api/work_hub/items/create", {"item": {"title": title, "status": "in_progress"}, "expected_revision": _rev()})["item"]["id"]
    page.evaluate("async () => { await switchPanel('notes'); }")
    card = f".work-hub-card[data-item-id='{item_id}']"
    page.wait_for_selector(card, timeout=15000)
    assert page.evaluate(f"() => !document.querySelector(\"{card} .work-hub-spinner\")")

    # The server reports a chat running a turn on this item (the flag is
    # derived from live streams, which a test server cannot start for real).
    working = {"on": True}

    def items(route):
        data = json.loads(urllib.request.urlopen(BASE + "/api/work_hub/items", timeout=10).read())
        for row in data["items"]:
            row["working"] = working["on"] and row["id"] == item_id
        route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

    page.route("**/api/work_hub/items", items)
    page.wait_for_selector(f"{card} .work-hub-spinner", timeout=8000)
    assert page.evaluate(f"() => document.querySelector(\"{card}\").classList.contains('is-working')")

    working["on"] = False
    page.wait_for_function(f"() => !document.querySelector(\"{card} .work-hub-spinner\")", timeout=8000)


def test_the_board_picks_up_an_item_a_chat_moved(page):
    title = f"Moved {uuid.uuid4().hex[:5]}"
    item_id = _post("/api/work_hub/items/create", {"item": {"title": title, "status": "todo"}, "expected_revision": _rev()})["item"]["id"]
    page.evaluate("async () => { await switchPanel('notes'); }")
    card = f".work-hub-card[data-item-id='{item_id}']"
    page.wait_for_selector(card, timeout=15000)

    _post("/api/work_hub/items/update", {"item_id": item_id, "item": {"status": "done"}, "expected_revision": _rev()})

    page.wait_for_function(f"() => document.querySelector(\"{card}\")?.closest('.work-hub-column')?.dataset.status === 'done'", timeout=8000)


def test_the_chat_footer_shows_the_item_being_worked_on_with_a_spinner(page):
    footer = page.evaluate("""() => {
        S.activeStreamId = 'stream-test';
        const sid = (S.session && S.session.session_id) || 'sid-test';
        S.session = S.session || {session_id: sid};
        const host = document.createElement('div'); host.id = 'liveRunStatus'; document.body.appendChild(host);
        _liveRunStatusSessionId = sid;
        noteWorkHubToolResult(sid, {name: 'work_hub', preview: JSON.stringify({updated: {id: 'w1', title: 'Fix login', status: 'in_progress'}})});
        _renderLiveRunStatusContent(host, null);
        const started = [!!host.querySelector('.lf-work-item .work-hub-spinner'), host.textContent.includes('Working on “Fix login”')];
        noteWorkHubToolResult(sid, {name: 'work_hub', preview: JSON.stringify({updated: {id: 'w1', title: 'Fix login', status: 'done'}})});
        _renderLiveRunStatusContent(host, null);
        return started.concat([!!host.querySelector('.lf-work-item')]);
    }""")
    assert footer == [True, True, False]


def test_work_hub_tool_steps_have_readable_labels(page):
    labels = page.evaluate("""() => [
        _toolActionLabelText({name: 'work_hub', done: true, args: {action: 'list'}}),
        _toolActionLabelText({name: 'work_hub', done: false, args: {action: 'update', item_id: 'x', status: 'in_progress'}}),
        _toolActionLabelText({name: 'work_hub', done: true, args: {action: 'update', item_id: 'x', status: 'done'},
                              snippet: JSON.stringify({updated: {id: 'x', title: 'Fix login', status: 'done'}})}),
        _toolActionLabelText({name: 'work_hub', done: true, args: {action: 'create', title: 'New thing'}}),
    ]""")
    assert labels == ["Checked the Work Hub", "Starting a work item", "Completed “Fix login”", "Added “New thing”"]
