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
    """The rail is one run round the rounded slab, corners included, cut once
    where the bridge lands, with a marker post either side of that gap set
    symmetrically about the bridge -- and no other posts."""
    out = page.evaluate("""async () => {
      const b = await import('/static/office/builders.js');
      const closed = b.makeGuardRails(12, 11, '#7c8cff', []).userData.markerPosts;
      const entry = { x: 6, z: 0 };
      const open = b.makeGuardRails(12, 11, '#7c8cff', [{ ...entry, r: b.bridgeGapHalfWidth(1, 0) }]).userData.markerPosts;
      const gap = open.filter(p => Math.abs(p.x - 6) < 1 && Math.abs(p.z) < 4);
      return { closed: closed.length, open: open.length, gapZ: gap.map(p => p.z) };
    }""")
    assert out["closed"] == 0, "a rail with no bridge has no posts (none on the corners)"
    assert out["open"] == 2, "just the two posts at the bridge gap"
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
      const single = hub([0]).userData.markerPosts.filter(p => p.z > 6);
      return { orbits: g.userData.orbits.length, closest, count: posts.length, singleX: single.map(p => p.x) };
    }""")
    assert out["orbits"] == 3, "the globe carries three electron orbits"
    assert out["closest"] >= 1.0, "side-by-side landings share a post instead of doubling it"
    assert out["count"] < 6, "the side-by-side landings make one gap, not two"
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


def test_idle_conductor_sits_emotes_and_drops_it_all_for_a_delegation(page):
    out = page.evaluate("""async () => {
      const { createWanderer } = await import('/static/office/motion.js');
      const { createConductorLife } = await import('/static/office/conductor-life.js');
      let seed = 5; const rand = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
      const w = createWanderer({ radius: 3.55, minRadius: 3.35, maxTurn: Math.PI * 0.3, rand, pauseMinMs: 0, pauseMaxMs: 300 });
      const life = createConductorLife({ rand });
      const chairs = [{ x: 4.1, z: 4.1, facing: Math.PI / 4 }, { x: -4.1, z: -4.1, facing: -3 * Math.PI / 4 }];
      const seen = { sat: 0, emoted: 0, icons: new Set(), poses: new Set(), satAtChair: true, closest: Infinity };
      let t = 0;
      for (let i = 0; i < 20000; i += 1) {
        t += 0.05;
        const now = life.step({ t, dtMs: 50, wanderer: w, chairs });
        if (now.icon) seen.icons.add(now.icon);
        if (now.seated) {
          seen.sat += 1;
          if (!chairs.some(c => Math.hypot(c.x - now.x, c.z - now.z) < 1e-6)) seen.satAtChair = false;
        }
        if (!now.walking && !now.seated && now.pose !== 'idle') seen.emoted += 1;
        seen.poses.add(now.pose);
        seen.closest = Math.min(seen.closest, Math.hypot(now.x, now.z));
      }
      life.cancel();
      return { sat: seen.sat, emoted: seen.emoted, icons: [...seen.icons], poses: [...seen.poses],
               satAtChair: seen.satAtChair, closest: seen.closest, mode: life.mode };
    }""")
    assert out["sat"] > 0 and out["satAtChair"], "it sits down, in a chair"
    assert out["emoted"] > 0 and out["icons"], "it stretches or sips, with a bubble"
    assert not {"work", "tool", "orchestrate"} & set(out["poses"]), "idle life never shows work"
    assert out["closest"] > 2.75, "it never walks through the pedestal"
    assert out["mode"] == "wander", "a delegation cancels whatever it was doing"


def test_sign_wall_stands_in_the_rail_line_without_extra_posts(page):
    out = page.evaluate("""async () => {
      const b = await import('/static/office/builders.js');
      const palette = { podTop: '#0d172b', deskLeg: '#2e3547', pot: '#7a5236', plant: '#3f5f45' };
      const blocked = [{ x: 0, z: 0.62, w: 6.9, d: 5.4, rot: Math.PI / 2 }];
      const g = b.makePodScenery('research', 12, 11, palette, '#7c8cff', { blocked, entry: { x: 6, z: 0 }, seed: 's', key: 'sign-test' });
      const sign = g.userData.placed[0];
      // How far the sign's centre is in from the edge it stands on.
      const inset = Math.min(6 - Math.abs(sign.x), 5.5 - Math.abs(sign.z));
      const rails = b.makeGuardRails(12, 11, '#7c8cff', [{ x: 6, z: 0, r: b.bridgeGapHalfWidth(1, 0) }, { x: sign.x, z: sign.z, r: 1.15, post: false }]);
      return { inset, posts: rails.userData.markerPosts.length };
    }""")
    assert abs(out["inset"] - 0.32) < 0.01, "the wall stands on the rail line"
    assert out["posts"] == 2, "the rail meets the wall with no posts; only the bridge gap has them"


def test_bridge_from_the_hub_drops_its_first_chevron(page):
    out = page.evaluate("""async () => {
      const b = await import('/static/office/builders.js');
      const palette = { bridgeDeck: '#1c2740', bridgeBeam: '#0b1020' };
      const count = opts => {
        const seg = b.makeBridgeSegment(14, palette, opts);
        const group = seg.children.find(c => c.userData && c.userData.activityChevrons);
        return group.userData.activityChevrons.map(c => c.position.z);
      };
      return { all: count({ railColor: '#7c8cff' }), hub: count({ railColor: '#7c8cff', skipFirstChevron: true }) };
    }""")
    assert len(out["hub"]) == len(out["all"]) - 1
    assert min(out["hub"]) > min(out["all"]), "the one dropped is at the conductor's (-z) end"


def test_conductor_hops_in_low_gravity_and_shooting_stars_fade(page):
    out = page.evaluate("""async () => {
      const b = await import('/static/office/builders.js');
      const L = b.HOP_LENGTH;
      const heights = [0, 0.25, 0.5, 0.75, 1].map(f => b.hopHeight(f * L));
      const star = b.makeShootingStar();
      star.userData.place({ x: 0, y: -18, z: 0 }, { x: 1, z: 0 }, 6, 2, 1);
      const head = star.children[1].position;
      return { heights, max: b.HOP_HEIGHT, headX: head.x };
    }""")
    h = out["heights"]
    assert h[0] == 0 and abs(h[4]) < 1e-9, "each hop starts and ends on the floor"
    assert abs(h[2] - out["max"]) < 1e-9 and abs(h[1] - h[3]) < 1e-9, "a symmetric parabola peaking mid-hop"
    assert out["headX"] == 6, "the shooting star's head leads its trail"
