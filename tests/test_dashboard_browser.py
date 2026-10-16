"""The Dashboard page: opens from the nav, switches tabs (remembered), shows
Work Hub quests that open the item, and fits a phone without sideways scroll."""

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
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            yield b
        finally:
            b.close()


def _open(browser, **ctx):
    page = browser.new_context(**ctx).new_page()
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return page


def test_dashboard_tabs_switch_and_are_remembered(browser):
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("() => { try { localStorage.removeItem('hermes-dashboard-tab'); } catch (_) {} }")
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector("#dashboardRoot .dash-stats", timeout=15000)
    assert page.evaluate("() => document.querySelector('.dash-tabs .on').textContent") == "Personal"

    page.evaluate("() => document.querySelector('.dash-tabs [data-dash-tab=career]').click()")
    page.wait_for_function("() => document.querySelector('.dash-body')?.dataset.tab === 'career' && document.querySelector('.dash-stats')", polling=100, timeout=15000)
    assert "Funnel" in page.evaluate("() => document.querySelector('.dash-body').textContent")
    assert page.evaluate("() => document.querySelector('#dashboardSidebar .side-menu-item.active').textContent.trim()") == "Career"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_function("() => document.querySelector('.dash-body')?.dataset.tab === 'career'", polling=100, timeout=15000)


def test_a_quest_is_picked_from_the_work_hub_finishes_there_and_earns_xp(browser):
    title = f"Phase 10 {uuid.uuid4().hex[:5]}"
    item_id = _post("/api/work_hub/items/create", {"item": {"title": title, "status": "todo", "priority": "high"}, "expected_revision": _rev()})["item"]["id"]
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    page.wait_for_selector(".dash-card.is-quests", timeout=15000)

    page.evaluate("() => window.HermesDashboard.openQuestPicker()")
    box = f".dash-picker input[value='{item_id}']"
    page.wait_for_selector(box, timeout=15000)
    page.evaluate(f"() => {{ const b = document.querySelector(\"{box}\"); b.checked = true; b.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
    page.evaluate("() => document.querySelector('[data-picker-add]').click()")
    row = f".dash-quest-row[data-quest='{item_id}']"
    page.wait_for_selector(row, timeout=15000)
    assert not page.evaluate(f"() => document.querySelector(\"{row}\").classList.contains('is-done')")

    # Finished in the Work Hub (or by a chat through the work_hub tool).
    _post("/api/work_hub/items/update", {"item_id": item_id, "item": {"status": "done"}, "expected_revision": _rev()})
    page.evaluate("() => window.HermesDashboard.select('career')")
    page.evaluate("() => window.HermesDashboard.select('personal')")
    page.wait_for_function(f"() => document.querySelector(\"{row}\")?.classList.contains('is-done')", polling=100, timeout=15000)
    assert page.evaluate(f"() => document.querySelector(\"{row} .dash-xp-gain\").textContent") == "+75 XP"  # high 50 x 1.5

    page.evaluate("() => window.HermesDashboard.select('character')")
    page.wait_for_selector(".char-stage .px-hero", timeout=15000)
    log = page.evaluate("() => document.querySelector('.dash-body').textContent")
    assert title in log and "+75 XP" in log
    assert page.evaluate("() => document.querySelectorAll('.char-tier').length") == 5
    assert page.evaluate("() => /Level \\d+/.test(document.querySelector('.char-title h2').textContent)")


def test_quest_rows_open_their_work_hub_item(browser):
    title = f"Dash quest {uuid.uuid4().hex[:5]}"
    item_id = _post("/api/work_hub/items/create", {"item": {"title": title, "status": "in_progress"}, "expected_revision": _rev()})["item"]["id"]
    _post("/api/dashboard/quests/add", {"item_ids": [item_id]})
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    quest = f".dash-quest-open[data-dash-item='{item_id}']"
    page.wait_for_selector(quest, timeout=15000)
    page.evaluate(f"() => document.querySelector(\"{quest}\").click()")
    page.wait_for_function(f"() => document.querySelector('main.main').classList.contains('showing-notes') && [...document.querySelectorAll('#workHubInspector input, #workHubInspector textarea')].some(e => e.value === {json.dumps(title)})", polling=100, timeout=15000)
    page.wait_for_selector("#workHubQuestToggle", timeout=10000)
    assert "On your quests" in page.evaluate("() => document.getElementById('workHubQuest').textContent")
    page.evaluate("() => document.getElementById('workHubQuestToggle').click()")
    page.wait_for_function("() => document.getElementById('workHubQuest')?.textContent.includes('Not a quest')", polling=100, timeout=10000)
    assert item_id not in json.loads(urllib.request.urlopen(BASE + "/api/dashboard/quests", timeout=10).read())["item_ids"]


def test_dashboard_fits_a_phone(browser):
    page = _open(browser, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector("#dashboardRoot .dash-stats", timeout=15000)
    time.sleep(0.4)
    widths = page.evaluate("() => { const r = document.getElementById('mainDashboard'); return [r.scrollWidth, r.clientWidth, document.querySelector('.dash-stats').getBoundingClientRect().right, innerWidth]; }")
    assert widths[0] <= widths[1] + 1 and widths[2] <= widths[3]
    assert page.evaluate("() => getComputedStyle(document.querySelector('.dash-stats')).gridTemplateColumns.split(' ').length") == 2


def test_character_page_fits_a_phone(browser):
    page = _open(browser, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('character'); }")
    page.wait_for_selector(".char-stage .px-hero", timeout=15000)
    time.sleep(0.4)
    assert page.evaluate("() => { const m = document.getElementById('mainDashboard'); return m.scrollWidth <= m.clientWidth + 1; }")
    assert page.evaluate("() => document.querySelector('.char-panel').getBoundingClientRect().right <= innerWidth")
