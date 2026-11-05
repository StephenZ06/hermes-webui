"""Controls that lost their labels keep a name, stay centred, and leave no gap behind."""

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1470, "height": 956})
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
        yield page
        browser.close()


def test_board_and_list_are_named_icons_and_search_starts_beside_them(page):
    page.evaluate("async () => { await switchPanel('notes'); }")
    page.wait_for_selector(".work-hub-view-switch button")
    out = page.evaluate("""() => {
      const buttons = [...document.querySelectorAll('.work-hub-view-switch > button')];
      const sw = document.querySelector('.work-hub-view-switch').getBoundingClientRect();
      const search = document.querySelector('.work-hub-search').getBoundingClientRect();
      return { text: buttons.map(b => b.textContent.trim()), names: buttons.map(b => b.getAttribute('aria-label')),
        widths: buttons.map(b => b.getBoundingClientRect().width),
        centred: buttons.every(b => { const r = b.getBoundingClientRect(), i = b.querySelector('svg').getBoundingClientRect();
          return Math.abs((r.left + r.right) / 2 - (i.left + i.right) / 2) <= .5; }),
        switchWidth: sw.width, gap: search.left - sw.right };
    }""")
    assert out["text"] == ["", ""]
    assert out["names"] == ["Board view", "List view"]
    assert out["widths"] == [30, 30]
    assert out["centred"]
    assert out["switchWidth"] <= 66
    assert out["gap"] == 8


def test_board_list_switch_still_changes_view(page):
    page.evaluate("async () => { await switchPanel('notes'); }")
    page.wait_for_selector("[data-view='list']")
    page.click("[data-view='list']")
    page.wait_for_selector("[data-view='list'].active")
    page.click("[data-view='board']")
    page.wait_for_selector("[data-view='board'].active")


def test_empty_notes_list_centres_its_message_with_no_button(page):
    page.evaluate("async () => { await switchPanel('notebook'); }")
    page.wait_for_selector(".nb-list-empty p")
    out = page.evaluate("""() => {
      const text = document.querySelector('.nb-list-empty p').getBoundingClientRect();
      const panel = document.querySelector('.nb-list').getBoundingClientRect();
      return { above: text.top - panel.top, below: panel.bottom - text.bottom,
        buttons: document.querySelectorAll('.nb-list-items button').length,
        plus: document.querySelectorAll('.nb-list-head [data-nb-action="new"]').length };
    }""")
    assert abs(out["above"] - out["below"]) <= 1, out
    assert out["buttons"] == 0
    assert out["plus"] == 1


def test_office_page_buttons_are_named_centred_icons(page):
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_selector(".office-page-nav-image", state="visible", timeout=15000)
    out = page.evaluate("""() => [...document.querySelectorAll('.office-page-nav-btn')].map(button => {
      const box = button.getBoundingClientRect(), icon = button.querySelector('img').getBoundingClientRect();
      return { text: button.textContent.trim(), name: button.getAttribute('aria-label'),
               offset: Math.abs((box.left + box.right) / 2 - (icon.left + icon.right) / 2) };
    })""")
    assert [row["text"] for row in out] == ["", ""]
    assert [row["name"] for row in out] == ["Dashboard: Office overview", "Integrations: Connected accounts"]
    assert all(row["offset"] <= .5 for row in out), out
