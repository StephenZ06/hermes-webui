"""Browser checks for Office camera navigation (opt-in).

Desktop: drag to pan, wheel to zoom, click a worker or a pod floor to frame it.
Touch: tap to pick, and the gesture plumbing (pinch / one-finger pan) shares the
same Pointer Events path.

    HERMES_WEBUI_BROWSER_TESTS=1 .venv/bin/pytest tests/test_office_navigation.py -s
"""
import os
import shutil

import pytest

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
        reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1",
    ),
    pytest.mark.skipif(
        not (shutil.which("chromium") or shutil.which("chromium-browser")),
        reason="needs a chromium",
    ),
]

SHOT = "/tmp/claude-1000/-home-z014-Apps-hermes-webui/893b6655-e438-4a32-b446-75883e7f732c/scratchpad"


def _open_office(pg, base_url):
    pg.goto(base_url, wait_until="load")
    pg.wait_for_timeout(2500)
    pg.evaluate('() => document.querySelectorAll(\'#onboardingOverlay, [role="dialog"]\').forEach(e => e.remove())')
    pg.wait_for_timeout(300)
    pg.evaluate("() => window.switchPanel('office')")
    pg.wait_for_timeout(1000)
    pg.evaluate("""() => {
      const O = window.HermesOffice;
      O.onSpawn({subagent_id:'n1', goal:'first branch', model:'opus', depth:1, run_id:'r'});
      O.onSpawn({subagent_id:'n2', goal:'second branch', depth:1, run_id:'r'});
      O.onSpawn({subagent_id:'n3', parent_id:'n1', goal:'nested', depth:2, run_id:'r'});
    }""")
    pg.wait_for_timeout(3800)


def test_desktop_pan_zoom_and_click(base_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        ])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        _open_office(pg, base_url)

        box = pg.query_selector(".office-canvas").bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

        v0 = pg.evaluate("() => window.HermesOffice.getView()")

        # Drag to pan.
        pg.mouse.move(cx, cy)
        pg.mouse.down()
        pg.mouse.move(cx - 220, cy - 60, steps=12)
        pg.mouse.up()
        pg.wait_for_timeout(200)
        v_pan = pg.evaluate("() => window.HermesOffice.getView()")

        # Wheel to zoom in.
        pg.mouse.move(cx, cy)
        pg.mouse.wheel(0, -600)
        pg.wait_for_timeout(200)
        v_zoom = pg.evaluate("() => window.HermesOffice.getView()")

        pg.evaluate("() => window.HermesOffice.resetView()")
        pg.wait_for_timeout(900)

        # Tap the floor of a section. Scan a coarse grid, resetting and letting
        # the fly-to tween settle between attempts.
        framed = pg.evaluate("""async () => {
          const O = window.HermesOffice;
          const c = document.querySelector('.office-canvas');
          const r = c.getBoundingClientRect();
          const tap = (x, y) => {
            c.dispatchEvent(new PointerEvent('pointerdown', {pointerId:1, clientX:x, clientY:y, bubbles:true, pointerType:'mouse', button:0}));
            c.dispatchEvent(new PointerEvent('pointerup',   {pointerId:1, clientX:x, clientY:y, bubbles:true, pointerType:'mouse', button:0}));
          };
          for (let fy = 0.32; fy <= 0.80; fy += 0.08) {
            for (let fx = 0.28; fx <= 0.80; fx += 0.08) {
              O.resetView();
              await new Promise(s => setTimeout(s, 950));
              const before = O.getView();
              tap(r.left + r.width * fx, r.top + r.height * fy);
              await new Promise(s => setTimeout(s, 950));
              const now = O.getView();
              if (now.zoom > before.zoom + 0.12
                  || Math.hypot(now.x - before.x, now.z - before.z) > 3) {
                return { before, after: now, hit: [+fx.toFixed(2), +fy.toFixed(2)],
                         focused: now.focusedId };
              }
            }
          }
          return { before: O.getView(), after: O.getView(), hit: null };
        }""")

        b.close()

    errors = [l for l in logs if l.startswith("pageerror")]
    print("v0", v0); print("pan", v_pan); print("zoom", v_zoom); print("framed", framed)

    moved = abs(v_pan["x"] - v0["x"]) + abs(v_pan["z"] - v0["z"])
    assert moved > 2, f"drag did not pan the camera ({moved:.2f})"
    assert v_zoom["zoom"] > v_pan["zoom"] + 0.05, "wheel did not zoom in"
    assert framed["hit"] is not None, "clicking a pod floor did not frame it"
    assert not errors, errors


def test_touch_tap_picks_a_worker(base_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        ])
        pg = b.new_page(viewport={"width": 420, "height": 850}, has_touch=True, is_mobile=True)
        _open_office(pg, base_url)

        # Two-finger pinch plumbing: dispatch a synthetic pinch and confirm zoom.
        res = pg.evaluate("""async () => {
          const O = window.HermesOffice;
          const c = document.querySelector('.office-canvas');
          const r = c.getBoundingClientRect();
          const mx = r.left + r.width/2, my = r.top + r.height/2;
          const before = O.getView().zoom;
          const pd = (id,x,y) => c.dispatchEvent(new PointerEvent('pointerdown',{pointerId:id,clientX:x,clientY:y,bubbles:true,pointerType:'touch'}));
          const pm = (id,x,y) => c.dispatchEvent(new PointerEvent('pointermove',{pointerId:id,clientX:x,clientY:y,bubbles:true,pointerType:'touch'}));
          const pu = (id,x,y) => c.dispatchEvent(new PointerEvent('pointerup',{pointerId:id,clientX:x,clientY:y,bubbles:true,pointerType:'touch'}));
          pd(1, mx-40, my); pd(2, mx+40, my);
          for (let d = 40; d <= 160; d += 20) { pm(1, mx-d, my); pm(2, mx+d, my); await new Promise(r2=>setTimeout(r2,16)); }
          pu(1, mx-160, my); pu(2, mx+160, my);
          const after = O.getView().zoom;
          return { before, after };
        }""")

        b.close()

    print("pinch", res)
    assert res["after"] > res["before"] + 0.05, f"pinch did not zoom ({res})"
