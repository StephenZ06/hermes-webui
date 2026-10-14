"""Work Hub on a phone: adding into the open board, one-tap boards, single-board
folders opening straight away, and hold-to-drag cards between columns."""

import json
import time
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE

PHONE = {"viewport": {"width": 430, "height": 873}, "is_mobile": True, "has_touch": True}


def _post(path, body):
    req = urllib.request.Request(BASE + path, method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def _rev():
    return json.loads(urllib.request.urlopen(BASE + "/api/work_hub/bootstrap", timeout=10).read())["revision"]


@pytest.fixture()
def seeded():
    tag = uuid.uuid4().hex[:5]
    multi = _post("/api/projects/create", {"name": f"Multi {tag}"})["project"]["project_id"]
    single = _post("/api/projects/create", {"name": f"Single {tag}"})["project"]["project_id"]
    boards = {}
    for name, project in ((f"Alpha {tag}", multi), (f"Beta {tag}", multi), (f"Only {tag}", single)):
        boards[name.split()[0]] = _post("/api/work_hub/boards/create", {"board": {"name": name, "project_id": project}, "expected_revision": _rev()})["board"]["id"]
    item = _post("/api/work_hub/items/create", {"item": {"title": f"Drag me {tag}", "status": "triage"}, "expected_revision": _rev()})["item"]["id"]
    return {"tag": tag, "multi": multi, "single": single, "boards": boards, "item": item}


@pytest.fixture()
def phone(seeded):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            ctx = browser.new_context(**PHONE)
            page = ctx.new_page()
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            page.evaluate("async () => { await switchPanel('notes'); }")
            page.wait_for_selector(".work-hub-board, .work-hub-list", timeout=15000)
            yield page, ctx.new_cdp_session(page)
        finally:
            browser.close()


def _open_drawer(page):
    page.evaluate("() => _setMobileDrawerState(document.querySelector('.sidebar'), 'open')")
    time.sleep(0.6)


def test_a_board_opens_on_one_tap_and_new_items_land_in_it(phone, seeded):
    page, _ = phone
    _open_drawer(page)
    page.tap(f".work-hub-project-tile[data-project-toggle='{seeded['multi']}']")
    time.sleep(0.5)
    page.tap(f"[data-board-id='{seeded['boards']['Beta']}']")
    time.sleep(0.8)
    assert page.evaluate("() => _mobileDrawerState()") == "closed"
    before = page.evaluate("() => document.querySelectorAll('.work-hub-card').length")
    page.tap("#workHubCreate")
    page.wait_for_function("(n) => document.querySelectorAll('.work-hub-card').length === n + 1", arg=before, timeout=10000)


def test_a_single_board_folder_opens_its_board_and_closes_the_drawer(phone, seeded):
    page, _ = phone
    _open_drawer(page)
    page.tap(f".work-hub-project-tile[data-project-toggle='{seeded['single']}']")
    time.sleep(0.8)
    state = page.evaluate("() => [_mobileDrawerState(), (document.querySelector('.work-hub-board-row.active') || {}).textContent || '']")
    assert state[0] == "closed" and "Only" in state[1]


def test_board_row_actions_do_not_depend_on_hover_on_touch(phone, seeded):
    page, _ = phone
    _open_drawer(page)
    page.tap(f".work-hub-project-tile[data-project-toggle='{seeded['multi']}']")
    time.sleep(0.5)
    opacity = page.evaluate("() => getComputedStyle(document.querySelector('.work-hub-project-boards.expanded .work-hub-board-rename')).opacity")
    assert float(opacity) > 0


def _touch(cdp, kind, x, y):
    cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [] if kind == "touchEnd" else [{"x": x, "y": y}]})


def test_hold_and_drag_moves_a_card_to_another_column(phone, seeded):
    page, cdp = phone
    page.evaluate("() => { document.querySelector('[data-scope=all]') && document.querySelector('[data-scope=all]').click(); }")
    time.sleep(0.8)
    sel = f".work-hub-card[data-item-id='{seeded['item']}']"
    page.evaluate(f"() => document.querySelector(\"{sel}\").scrollIntoView({{block: 'center'}})")
    x, y = page.evaluate(f"() => {{ const r = document.querySelector(\"{sel}\").getBoundingClientRect(); return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)]; }}")
    # A quick swipe scrolls; it does not pick the card up.
    _touch(cdp, "touchStart", x, y)
    for xx in range(x, x - 100, -10):
        _touch(cdp, "touchMove", xx, y)
    _touch(cdp, "touchEnd", x - 100, y)
    time.sleep(0.4)
    assert page.evaluate("() => !document.querySelector('.work-hub-card-ghost')")
    page.evaluate("() => { document.querySelector('.work-hub-board-wrap').scrollLeft = 0; }")
    time.sleep(0.3)
    x, y = page.evaluate(f"() => {{ const r = document.querySelector(\"{sel}\").getBoundingClientRect(); return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)]; }}")
    target_x = page.evaluate("() => { const r = document.querySelector('.work-hub-column[data-status=backlog]').getBoundingClientRect(); return Math.round(r.x + Math.min(60, r.width / 3)); }")
    _touch(cdp, "touchStart", x, y)
    time.sleep(0.6)
    assert page.evaluate("() => !!document.querySelector('.work-hub-card-ghost')")
    for xx in range(x, target_x, 8):
        _touch(cdp, "touchMove", xx, y)
    time.sleep(0.3)
    assert page.evaluate("() => (document.querySelector('.work-hub-column.drop-target') || {dataset: {}}).dataset.status") == "backlog"
    _touch(cdp, "touchEnd", target_x, y)
    page.wait_for_function(f"() => (document.querySelector(\"{sel}\") || {{closest: () => null}}).closest('.work-hub-column')?.dataset.status === 'backlog'", timeout=10000)
    assert page.evaluate("() => !document.querySelector('.work-hub-card-ghost')")
