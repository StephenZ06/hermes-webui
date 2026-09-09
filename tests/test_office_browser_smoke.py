"""End-to-end browser check: the office panel inside the real running app.

Opt-in — set HERMES_WEBUI_BROWSER_TESTS=1 to run it. It needs playwright and a
chromium with a working (software is fine) WebGL stack, and it costs ~15s, so
it is not part of the default suite.

It exists because this panel has a failure mode nothing else here can catch:
the module graph resolving, the import map applying, and WebGL coming up are
all things that fail *silently* in a browser and leave a blank panel, while
every source-structure and node test still passes. See
docs/rfcs/office-visualization.md.

Run it with:

    HERMES_WEBUI_BROWSER_TESTS=1 .venv/bin/pytest tests/test_office_browser_smoke.py
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


def test_office_panel_in_the_real_app(base_url, tmp_path):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        ])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        pg.goto(base_url, wait_until="load")
        pg.wait_for_timeout(2500)
        # A fresh isolated state dir means first-run: hide the setup wizard and
        # the guided tour so the panel underneath is actually visible. This is
        # about the screenshot, not the assertions — the app works either way.
        pg.evaluate('''() => {
          const kill = sel => document.querySelectorAll(sel).forEach(el => el.remove());
          kill('#onboardingOverlay');
          kill('.onboarding-overlay, .tour-overlay, .tour-popover, [class*="coachmark"]');
          document.querySelectorAll('[role="dialog"]').forEach(el => el.remove());
        }''')
        pg.wait_for_timeout(600)

        boot = pg.evaluate("""() => ({
          office: typeof window.HermesOffice,
          canvasTab: !!document.querySelector('[data-panel="office"]'),
          importMap: !!document.querySelector('script[type="importmap"]'),
        })""")
        pg.evaluate("() => window.switchPanel('office')")
        pg.wait_for_timeout(1500)
        pg.evaluate("""() => {
          const O = window.HermesOffice;
          O.onSpawn({subagent_id:'demo-1', goal:'audit the delegation path', model:'opus', depth:1});
          O.onSpawn({subagent_id:'demo-2', goal:'write the regression tests', depth:1});
          O.onSpawn({subagent_id:'demo-3', parent_id:'demo-1', goal:'read api/routes.py', depth:2});
          O.onToolActivity({subagent_id:'demo-2', tool:'Read', preview:'tests/test_office.py'});
          O.onComplete({subagent_id:'demo-3', status:'ok', duration_seconds:6.5, summary:'found the branch'});
        }""")
        pg.wait_for_timeout(2000)

        shown = pg.evaluate("""() => {
          const c = document.querySelector('.office-canvas');
          return {
            mainClass: document.querySelector('main.main').className,
            canvas: !!c,
            webgl2: c ? !!c.getContext('webgl2') : false,
            size: c ? [c.width, c.height] : null,
            pill: (document.getElementById('officePill')||{}).textContent,
            outlets: [...document.querySelectorAll('.office-outlet-btn')].map(b=>b.textContent),
            summary: (document.getElementById('officeSummary')||{}).textContent,
            workers: window.HermesOffice.getState().workers.map(w=>[w.id,w.status,w.pose]),
          };
        }""")
        pg.screenshot(path=str(tmp_path / "office-projects.png"))

        # Camera: focusing flies to a desk and zooms in; reset returns exactly.
        camera = pg.evaluate("""async () => {
          const O = window.HermesOffice;
          const overview = O.getView();
          O.focusWorker('demo-2');
          await new Promise(r => setTimeout(r, 1200));
          const focused = O.getView();
          O.resetView();
          await new Promise(r => setTimeout(r, 1200));
          return { overview, focused, back: O.getView() };
        }""")

        pg.evaluate("() => document.querySelector('[data-outlet=\\\"business\\\"]').click()")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(tmp_path / "office-business.png"))

        pg.evaluate("() => window.switchPanel('agentCanvas')")
        pg.wait_for_timeout(800)
        after = pg.evaluate("""() => ({
          canvasGone: !document.querySelector('.office-canvas'),
          agentCanvasAlive: !!document.querySelector('#agentCanvasTree'),
          officeStateKept: window.HermesOffice.getState().workers.length,
        })""")
        pg.screenshot(path=str(tmp_path / "office-left.png"))
        b.close()

    errors = [line for line in logs
              if line.startswith("pageerror") or line.startswith("error:")]

    assert boot["importMap"], "the import map must survive index.html templating"
    assert boot["office"] == "object", "the module graph resolved and published the global"
    assert boot["canvasTab"], "the rail carries an office tab"
    assert "showing-office" in shown["mainClass"]
    assert shown["canvas"] and shown["webgl2"], "WebGL came up in the real page"
    assert shown["outlets"] == ["Projects", "Business"]
    assert len(shown["workers"]) == 3
    assert "3 subagents, 2 running" in shown["summary"], (
        "the spoken summary is the only version of this a screen reader gets"
    )
    # Leaving the panel must release the context while office state survives —
    # the run is still going, and Agent Canvas must be untouched.
    assert after["canvasGone"] and after["officeStateKept"] == 3

    # The camera actually travels, and comes back to where it started.
    assert camera["overview"]["focusedId"] is None
    assert camera["focused"]["focusedId"] == "demo-2"
    assert camera["focused"]["zoom"] > camera["overview"]["zoom"], (
        "focusing must zoom in, not merely re-centre"
    )
    assert camera["overview"]["poses"], (
        "the scene reports each figure's rendered pose — an idle behaviour "
        "plays over plain work and is otherwise invisible from outside"
    )
    assert set(camera["overview"]["poses"]) == {"demo-1", "demo-2", "demo-3"}
    assert camera["back"]["focusedId"] is None
    assert abs(camera["back"]["zoom"] - camera["overview"]["zoom"]) < 1e-6, (
        "reset must return to the framed overview, not an approximation of it"
    )

    assert after["agentCanvasAlive"]
    assert not errors, f"console errors in the real app: {errors}"
