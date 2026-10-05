"""Office dashboard cards: fixed height, scrolling, and per-floor completions.

Every card body is one height -- four rows -- and scrolls past it, so a
seven-floor Business office or a long list no longer stretches its card.
A Work distribution floor opens, inside the same card, the tasks completed
on that floor only, with a way back.
"""
import pytest

from tests._pytest_port import BASE


def _open_dashboard(pw):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_function("() => window.HermesOffice && typeof window.officeSetSubview === 'function'", polling=100, timeout=30000)
    page.evaluate("""() => {
      const O = window.HermesOffice;
      // Two completed on Research, one on Coding, one still running on Research.
      [['r1', 'research competitor pricing'], ['r2', 'research the market size'],
       ['c1', 'fix the failing build in the code'], ['r3', 'research hiring trends']]
        .forEach(([id, goal]) => O.onSpawn({subagent_id: id, goal, depth: 1, run_id: 'dash'}));
      ['r1', 'r2', 'c1'].forEach(id => O.onComplete({subagent_id: id, status: 'completed', summary: 'done'}));
      window.officeSetSubview('dashboard');
    }""")
    page.wait_for_selector("[data-dashboard-panel='distribution'] [data-dashboard-floor]", timeout=15000)
    return browser, page


def test_every_card_body_has_one_fixed_height_and_scrolls_past_it():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open_dashboard(pw)
        try:
            projects = page.evaluate("""() => [...document.querySelectorAll('.office-dashboard-panel-body')]
              .map(b => ({h: Math.round(b.getBoundingClientRect().height), overflow: getComputedStyle(b).overflowY}))""")
            page.click("[data-dashboard-outlet='business']")
            page.wait_for_function(
                "() => document.querySelectorAll('[data-dashboard-panel=\"distribution\"] [data-dashboard-floor]').length > 4",
                polling=100, timeout=15000)
            business = page.evaluate("""() => {
              const body = document.querySelector('[data-dashboard-panel="distribution"] .office-dashboard-panel-body');
              const rows = [...body.querySelectorAll('[data-dashboard-floor]')];
              const top = body.getBoundingClientRect().top, bottom = body.getBoundingClientRect().bottom;
              return {h: Math.round(body.getBoundingClientRect().height), scrolls: body.scrollHeight > body.clientHeight + 1,
                      rows: rows.length, fullyVisible: rows.filter(r => { const b = r.getBoundingClientRect(); return b.top >= top - 1 && b.bottom <= bottom + 1; }).length};
            }""")
        finally:
            browser.close()

    assert len(projects) == 4
    assert len({p["h"] for p in projects}) == 1, f"all four cards share one body height: {projects}"
    assert all(p["overflow"] == "auto" for p in projects)
    assert business["h"] == projects[0]["h"], "seven Business floors must not stretch the card"
    assert business["scrolls"] and business["rows"] == 7, business
    assert business["fullyVisible"] == 4, f"the body shows exactly four floors before scrolling: {business}"


def test_a_floor_opens_its_completed_tasks_inside_the_card_and_goes_back():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open_dashboard(pw)
        try:
            research_key = page.evaluate("""() => [...document.querySelectorAll('[data-dashboard-floor]')]
              .find(b => /research/i.test(b.textContent)).dataset.dashboardFloor""")
            page.click(f"[data-dashboard-floor='{research_key}']")
            page.wait_for_selector("[data-dashboard-floor-back]", timeout=10000)
            detail = page.evaluate("""() => {
              const card = document.querySelector('[data-dashboard-panel="distribution"]');
              return {title: card.querySelector('h2').textContent.trim(),
                      ids: [...card.querySelectorAll('[data-dashboard-worker-id]')].map(b => b.dataset.dashboardWorkerId).sort(),
                      cards: document.querySelectorAll('.office-dashboard-panel').length,
                      focused: document.activeElement && document.activeElement.hasAttribute('data-dashboard-floor-back')};
            }""")
            # A live re-render (every sync) keeps the detail open.
            page.evaluate("() => window.HermesOffice.onSpawn({subagent_id: 'r4', goal: 'research a vendor', depth: 1, run_id: 'dash'})")
            page.wait_for_timeout(300)
            still_open = page.is_visible("[data-dashboard-floor-back]")
            page.keyboard.press("Escape")
            page.wait_for_selector(f"[data-dashboard-floor='{research_key}']", timeout=10000)
            back_focus = page.evaluate("() => document.activeElement && document.activeElement.dataset.dashboardFloor")
        finally:
            browser.close()

    assert "Research" in detail["title"]
    assert detail["ids"] == ["r1", "r2"], "only Research's completed tasks: not Coding's, not the running one"
    assert detail["cards"] == 4, "the detail replaces the card's content, it does not add a card"
    assert detail["focused"], "keyboard focus moves to the back button"
    assert still_open, "a live update must not close the open floor"
    assert back_focus == research_key, "going back returns focus to the floor that was opened"
