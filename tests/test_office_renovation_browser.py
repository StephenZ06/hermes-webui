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


def test_rails_run_round_the_corners_and_open_only_for_the_bridge(page):
    """The rail is one run round the rounded slab (posts at its four corners),
    cut once where the bridge lands, with a marker post either side of that
    gap set symmetrically about the bridge."""
    out = page.evaluate("""async () => {
      const b = await import('/static/office/builders.js');
      const closed = b.makeGuardRails(12, 11, '#7c8cff', []).userData.markerPosts;
      const entry = { x: 6, z: 0 };
      const open = b.makeGuardRails(12, 11, '#7c8cff', [{ ...entry, r: b.bridgeGapHalfWidth(1, 0) }]).userData.markerPosts;
      const gap = open.filter(p => Math.abs(p.x - 6) < 1 && Math.abs(p.z) < 4);
      return { closed: closed.length, open: open.length, gapZ: gap.map(p => p.z) };
    }""")
    assert out["closed"] == 4, "one post per corner and no gaps on a rail with no bridge"
    assert out["open"] == 6, "four corners plus two posts at the bridge gap"
    assert len(out["gapZ"]) == 2 and abs(sum(out["gapZ"])) < 0.2, out
    assert all(abs(z) > 1.8 for z in out["gapZ"]), "the posts stand outside the deck"


def test_hub_posts_flank_each_bridge_and_never_double_up(page):
    out = page.evaluate("""async () => {
      const b = await import('/static/office/builders.js');
      const hub = (bridges) => {
        const g = b.makeHubCentrepiece(15.4, '#4f8cff', { bridges });
        return g;
      };
      // Two bridges landing side by side on one edge, as on the Business floor.
      // Landings 2 x 2.43 apart along the +x edge: their inner posts coincide.
      const g = hub([Math.PI / 2 - 0.306, Math.PI / 2 + 0.306, 0]);
      const posts = g.userData.markerPosts;
      let closest = Infinity;
      posts.forEach((p, i) => posts.slice(i + 1).forEach(q => { closest = Math.min(closest, Math.hypot(p.x - q.x, p.z - q.z)); }));
      const single = hub([0]).userData.markerPosts.filter(p => p.z > 6 && Math.abs(p.x) < 4);
      return { orbits: g.userData.orbits.length, closest, count: posts.length, singleX: single.map(p => p.x) };
    }""")
    assert out["orbits"] == 3, "the globe carries three electron orbits"
    assert out["closest"] >= 1.0, "side-by-side landings share a post instead of doubling it"
    assert out["count"] < 4 + 6, "the shared post was merged"
    assert len(out["singleX"]) == 2 and abs(sum(out["singleX"])) < 0.05, "a bridge's posts are symmetric about it"


def test_platform_band_has_no_halo_round_it(page):
    out = page.evaluate("""async () => {
      const b = await import('/static/office/builders.js');
      const pod = b.makePod(12, 11, { podTop: '#0d172b' }, '#7c8cff');
      let halos = 0;
      pod.traverse(o => { if (o.userData && o.userData.bandGlow) halos += 1; });
      return { halos, band: !!pod.userData.deliveryLayer };
    }""")
    assert out == {"halos": 0, "band": True}
