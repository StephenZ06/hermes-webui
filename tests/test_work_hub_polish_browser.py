"""Work Hub polish: Enter saves a new item from its title, primary buttons are
an accent tint, the item panel is wider, the create menus and New Project
dialog use the page background, and a revision bumped elsewhere in the hub
neither fails a save nor costs the typed text."""
import json
import urllib.request

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1899, "height": 990})
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        page.evaluate("() => { localStorage.removeItem('workHubInspectorPanelWidth'); document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove()); }")
        page.evaluate("async () => { await switchPanel('notes'); }")
        page.wait_for_selector("#workHubCreate", timeout=10000)
        yield page
        browser.close()


def _items():
    with urllib.request.urlopen(BASE + "/api/work_hub/bootstrap", timeout=10) as res:
        return json.load(res)["items"]


def _new_item(page):
    page.click("#workHubCreate")
    page.wait_for_selector("#workHubTitle", timeout=10000)
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'workHubTitle'", timeout=5000)


def test_enter_in_a_new_items_title_saves_it(page):
    _new_item(page)
    page.keyboard.type("Enter saved this")
    page.keyboard.press("Enter")
    page.wait_for_function("() => !document.querySelector('#workHubInspector .wh-insp')", timeout=8000)
    assert any(row["title"] == "Enter saved this" for row in _items())


def test_a_change_elsewhere_in_the_hub_does_not_cost_a_save(page):
    _new_item(page)
    page.keyboard.type("Kept through a conflict")
    page.evaluate("""async () => {
      const boot = await api('/api/work_hub/bootstrap');
      await api('/api/work_hub/items/create', {method: 'POST', body: JSON.stringify({item: {title: 'From another tab', status: 'todo'}, expected_revision: boot.revision})});
    }""")
    page.keyboard.press("Enter")
    page.wait_for_function("() => !document.querySelector('#workHubInspector .wh-insp')", timeout=8000)
    assert any(row["title"] == "Kept through a conflict" for row in _items())


def test_a_real_conflict_keeps_the_typed_title(page):
    _new_item(page)
    item_id = page.evaluate("() => document.querySelector('#workHubInspector .wh-insp').dataset.itemId")
    page.keyboard.type("Mine")
    page.evaluate("""async (id) => {
      const boot = await api('/api/work_hub/bootstrap');
      await api('/api/work_hub/items/update', {method: 'POST', body: JSON.stringify({item_id: id, item: {title: 'Theirs'}, expected_revision: boot.revision})});
    }""", item_id)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)
    assert page.input_value("#workHubTitle") == "Mine"
    assert any(row["id"] == item_id and row["title"] == "Theirs" for row in _items())


def test_enter_on_an_untouched_new_item_closes_it(page):
    _new_item(page)
    page.keyboard.press("Enter")
    page.wait_for_function("() => !document.querySelector('#workHubInspector .wh-insp')", timeout=8000)


def test_enter_in_the_description_stays_a_new_line(page):
    _new_item(page)
    page.click("#workHubDescription")
    page.keyboard.type("one")
    page.keyboard.press("Enter")
    page.keyboard.type("two")
    page.wait_for_timeout(300)
    assert page.input_value("#workHubDescription") == "one\ntwo"
    assert page.query_selector("#workHubSave").get_attribute("data-state") is None


def test_item_panel_is_wider_and_primary_buttons_are_a_tint(page):
    _new_item(page)
    page.keyboard.type("x")
    page.mouse.move(700, 500)  # off the + button, whose hover fill fades out
    page.wait_for_timeout(500)
    state = page.evaluate("""() => {
      const probe = document.createElement('div'); document.body.appendChild(probe);
      const fill = v => { probe.style.background = v; return getComputedStyle(probe).backgroundColor; };
      const tint = fill('var(--accent-bg)'); probe.remove();
      const bg = id => getComputedStyle(document.getElementById(id)).backgroundColor;
      return {width: document.getElementById('workHubInspector').getBoundingClientRect().width, tint,
              create: bg('workHubCreate'), save: bg('workHubSave')};
    }""")
    assert state["width"] == 360, state
    assert state["create"] == state["tint"], state
    assert state["save"] == state["tint"], state


def test_new_project_flow_sits_on_the_page_background(page):
    page.click("#workHubProjectCreate")
    page.wait_for_selector(".work-hub-create-menu", timeout=5000)
    fills = page.evaluate("""() => {
      const probe = document.createElement('div'); probe.style.background = 'var(--bg)'; document.body.appendChild(probe);
      const bg = getComputedStyle(probe).backgroundColor; probe.remove();
      return {bg, menu: getComputedStyle(document.querySelector('.work-hub-create-menu')).backgroundColor};
    }""")
    assert fills["menu"] == fills["bg"], fills
    page.click("[data-create-project]")
    page.wait_for_selector(".app-dialog-title", state="visible", timeout=5000)
    assert page.inner_text(".app-dialog-title") == "New Project"
