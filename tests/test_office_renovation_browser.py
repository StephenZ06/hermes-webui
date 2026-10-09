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


def test_decorations_never_overlap_a_desk_a_walkway_or_the_bridge(page):
    out = page.evaluate("""async () => {
      const b = await import('/static/office/builders.js');
      const palette = { podTop: '#0d172b', deskLeg: '#2e3547', pot: '#7a5236', plant: '#3f5f45' };
      const results = [];
      // A desk turned 45 degrees (as Projects pods face the hub), and one square-on.
      for (const rot of [Math.PI * 0.25, Math.PI * 0.5, Math.PI * 1.25]) {
        const c = Math.cos(rot), s = Math.sin(rot);
        const blocked = [{ lx: 0, lz: 0.62, w: 6.9, d: 5.4 }, { lx: 0, lz: 4.1, w: 4.2, d: 3.4 }]
          .map(r => ({ x: r.lx * c + r.lz * s, z: -r.lx * s + r.lz * c, w: r.w, d: r.d, rot }));
        const entry = { x: 6 * Math.sin(rot + Math.PI), z: 5.5 * Math.cos(rot + Math.PI) };
        for (const kind of ['general', 'research', 'coding', 'documents', 'sales', 'delivery']) {
          const g = b.makePodScenery(kind, 12, 11, palette, '#7c8cff', { blocked, entry, seed: kind + rot, key: kind + rot });
          const placed = g.userData.placed;
          const bad = placed.filter(p => blocked.some(r => b.rectsOverlap(p, r)));
          results.push({ kind, rot, count: placed.length, bad: bad.length });
        }
      }
      return results;
    }""")
    assert all(r["bad"] == 0 for r in out), out
    assert all(r["count"] >= 3 for r in out), "each pod still gets several pieces"
