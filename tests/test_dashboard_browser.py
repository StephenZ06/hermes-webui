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


def test_a_quest_opens_its_work_hub_item(browser):
    title = f"Dash quest {uuid.uuid4().hex[:5]}"
    item_id = _post("/api/work_hub/items/create", {"item": {"title": title, "status": "in_progress"}, "expected_revision": _rev()})["item"]["id"]
    page = _open(browser, viewport={"width": 1280, "height": 860})
    page.evaluate("() => { try { localStorage.setItem('hermes-dashboard-tab', 'personal'); } catch (_) {} }")
    page.evaluate("async () => { await switchPanel('dashboard'); window.HermesDashboard.select('personal'); }")
    quest = f"[data-dash-item='{item_id}']"
    page.wait_for_selector(quest, timeout=15000)
    page.evaluate(f"() => document.querySelector(\"{quest}\").click()")
    page.wait_for_function(f"() => document.querySelector('main.main').classList.contains('showing-notes') && [...document.querySelectorAll('#workHubInspector input, #workHubInspector textarea')].some(e => e.value === {json.dumps(title)})", polling=100, timeout=15000)


def test_dashboard_fits_a_phone(browser):
    page = _open(browser, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page.evaluate("async () => { await switchPanel('dashboard'); }")
    page.wait_for_selector("#dashboardRoot .dash-stats", timeout=15000)
    time.sleep(0.4)
    widths = page.evaluate("() => { const r = document.getElementById('mainDashboard'); return [r.scrollWidth, r.clientWidth, document.querySelector('.dash-stats').getBoundingClientRect().right, innerWidth]; }")
    assert widths[0] <= widths[1] + 1 and widths[2] <= widths[3]
    assert page.evaluate("() => getComputedStyle(document.querySelector('.dash-stats')).gridTemplateColumns.split(' ').length") == 2
