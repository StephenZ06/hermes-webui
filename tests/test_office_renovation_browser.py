"""Office renovation: department scenery is chosen from the department's name,
and leaving the Office suspends its scene so coming back reuses the same
canvas and WebGL context instead of rebuilding everything."""

import pytest

from tests._pytest_port import BASE


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--use-gl=angle",
                                           "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            tab = browser.new_page(viewport={"width": 1280, "height": 800})
            tab.add_init_script("""window.__contexts = 0;
              const get = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
                if (String(kind).startsWith('webgl')) window.__contexts += 1;
                return get.call(this, kind, ...rest);
              };""")
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
            yield tab
        finally:
            browser.close()


def test_department_names_pick_their_scenery(page):
    kinds = page.evaluate("""async () => {
      const { deptKind } = await import('/static/office/builders.js');
      return ['Research', 'Coding', 'Documents', 'Emails', 'Marketing', 'Sales', 'Finance', 'Operations',
              'Delivery', 'General', 'Something else'].map(deptKind);
    }""")
    assert kinds == ["research", "coding", "documents", "emails", "marketing", "sales", "finance",
                     "operations", "delivery", "general", "general"]


def test_leaving_and_returning_reuses_the_scene(page):
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_function("() => window.HermesOffice && window.HermesOffice.isRunning()", polling=100, timeout=60000)
    page.evaluate("() => { window.__canvas = document.getElementById('officeCanvas'); }")
    before = page.evaluate("() => window.__contexts")
    page.evaluate("async () => { await switchPanel('chat'); }")
    assert page.evaluate("() => window.HermesOffice.isRunning()") is False, "a suspended scene draws nothing"
    page.evaluate("async () => { await switchPanel('office'); }")
    page.wait_for_function("() => window.HermesOffice.isRunning()", polling=100, timeout=30000)
    out = page.evaluate("() => ({ same: document.getElementById('officeCanvas') === window.__canvas, contexts: window.__contexts })")
    assert out["same"], "the same canvas comes back"
    assert out["contexts"] == before, "no new WebGL context was created"
