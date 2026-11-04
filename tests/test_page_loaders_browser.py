"""Pages with a slow first load show a loader drawn from what the page is:
Notes turns pages, Jobs sweeps a radar, Work Hub moves a card across columns,
Insights grows bars. Each one must leave when the data arrives."""
import pytest

from tests._pytest_port import BASE

READY = "() => typeof S !== 'undefined' && S._bootReady === true"
ZEUS = "localStorage.setItem('hermes-skin','zeus-2');localStorage.setItem('hermes-theme','dark');"
CASES = [
    ("notebook", "**/api/notebook/bootstrap*", ".nb-page-loader .pl-book .pl-leaf", 3),
    ("jobs", "**/api/job*/**", ".pl-radar .pl-blip", 3),
    ("notes", "**/api/work_hub/bootstrap*", ".pl-board i", 3),
    ("insights", "**/api/insights*", ".pl-bars i", 5),
    ("kanban", "**/api/kanban/**", ".pl-board i", 3),
]


def _open(browser, hold=None, **options):
    """Open the app; `hold` keeps that API call waiting from the very first load."""
    context = browser.new_context(viewport={"width": 1899, "height": 990}, **options)
    context.add_init_script(ZEUS)
    page = context.new_page()
    page.held = []
    if hold:
        page.route(hold, lambda route: page.held.append(route))
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function(READY, polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    return page


@pytest.fixture
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        instance = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        yield instance
        instance.close()


@pytest.mark.parametrize("panel,pattern,selector,parts", CASES, ids=[c[0] for c in CASES])
def test_page_shows_its_own_loader_until_the_data_arrives(browser, panel, pattern, selector, parts):
    page = _open(browser, hold=pattern)
    page.evaluate("name => { switchPanel(name); }", panel)
    page.wait_for_selector(selector, state="visible", timeout=8000)
    assert page.locator(selector).count() == parts
    assert page.evaluate("s => getComputedStyle(document.querySelector(s)).animationName !== 'none'", selector)
    for route in page.held:
        route.continue_()
    page.unroute(pattern)
    page.route(pattern, lambda route: route.continue_())
    page.wait_for_selector(selector, state="hidden", timeout=8000)


def test_notes_leaf_turns_around_the_spine(browser):
    page = _open(browser, hold="**/api/notebook/bootstrap*")
    page.evaluate("() => { switchPanel('notebook'); }")
    page.wait_for_selector(".pl-leaf", state="visible", timeout=8000)
    seen = set()
    for _ in range(12):
        seen.add(page.evaluate("() => getComputedStyle(document.querySelector('.pl-leaf')).transform"))
        page.wait_for_timeout(110)
    assert len(seen) > 4, "the leaf must move while the notes load"
    assert page.evaluate("() => getComputedStyle(document.querySelector('.pl-leaf')).transformOrigin").startswith("0px")


def test_reduced_motion_keeps_the_loader_still(browser):
    page = _open(browser, hold="**/api/notebook/bootstrap*", reduced_motion="reduce")
    page.evaluate("() => { switchPanel('notebook'); }")
    page.wait_for_selector(".pl-book", state="visible", timeout=8000)
    assert page.evaluate("() => [...document.querySelectorAll('.pl-leaf')].every(e => getComputedStyle(e).animationName === 'none')")
    assert page.locator(".nb-page-loader-label").inner_text() == "Loading notes"


def test_a_failed_load_does_not_leave_the_loader_up(browser):
    page = _open(browser)
    page.route("**/api/work_hub/bootstrap*", lambda route: route.fulfill(status=500, body="{}"))
    page.evaluate("() => { switchPanel('notes'); }")
    page.wait_for_function("() => !document.querySelector('.pl-board') && document.querySelector('#workHub').children.length", timeout=8000)
