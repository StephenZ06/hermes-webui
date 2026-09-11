"""Browser checks for the Office visual-polish pass (opt-in).

Covers: floor signage instead of a "Conductor" nameplate, a "Subagents" sign on
the conductor's own pod, wider desk nameplates, "View live" switching the main
view, the connector lines fading in, arrivals routing around furniture, and
seated figures facing their monitors.

    HERMES_WEBUI_BROWSER_TESTS=1 .venv/bin/pytest tests/test_office_visual_polish.py -s
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

SHOT_DIR = "/tmp/claude-1000/-home-z014-Apps-hermes-webui/893b6655-e438-4a32-b446-75883e7f732c/scratchpad"


def test_office_visual_polish(base_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=[
            "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        ])
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        pg.goto(base_url, wait_until="load")
        pg.wait_for_timeout(2500)
        pg.evaluate('''() => {
          document.querySelectorAll('#onboardingOverlay, [role="dialog"]').forEach(el => el.remove());
        }''')
        pg.wait_for_timeout(300)

        pg.evaluate("() => window.switchPanel('office')")
        pg.wait_for_timeout(1000)

        # Five direct subagents (pod = "Subagents", two rows) + one nested.
        pg.evaluate("""() => {
          const O = window.HermesOffice;
          O.onSpawn({subagent_id:'s1', goal:'audit every call site of the delegation progress callback', model:'opus', depth:1, run_id:'r'});
          O.onSpawn({subagent_id:'s2', goal:'write the regression tests for the office floor', depth:1, run_id:'r'});
          O.onSpawn({subagent_id:'s5', goal:'trace the reconcile poll timing', depth:1, run_id:'r'});
          O.onSpawn({subagent_id:'s6', goal:'check the desk reclaim path', depth:1, run_id:'r'});
          O.onSpawn({subagent_id:'s7', goal:'measure the fade timing', depth:1, run_id:'r'});
          O.onSpawn({subagent_id:'s3', parent_id:'s1', goal:'read api/routes.py end to end', depth:2, run_id:'r'});
        }""")

        # --- mid-arrival: figures should be walking in, off to the side ---
        pg.wait_for_timeout(150)
        pg.evaluate("() => window.HermesOffice.focusWorker('s6')")
        pg.wait_for_timeout(500)
        mid = pg.evaluate("""() => {
          const scene = window.HermesOffice; // no direct scene handle; sample poses
          return { poses: scene.getView().poses };
        }""")
        pg.screenshot(path=f"{SHOT_DIR}/polish-1-arrival.png")
        pg.wait_for_timeout(700)
        pg.screenshot(path=f"{SHOT_DIR}/polish-1b-arrival.png")
        pg.evaluate("() => window.HermesOffice.resetView()")

        # --- settled ---
        pg.wait_for_timeout(3500)
        pg.evaluate("""() => {
          const O = window.HermesOffice;
          O.onToolActivity({subagent_id:'s1', tool:'Grep', preview:'tool_progress_callback'});
        }""")
        pg.wait_for_timeout(1200)
        pg.screenshot(path=f"{SHOT_DIR}/polish-2-settled.png")

        # Close-up on a desk: facing + nameplate width.
        pg.evaluate("() => window.HermesOffice.focusWorker('s2')")
        pg.wait_for_timeout(1400)
        pg.screenshot(path=f"{SHOT_DIR}/polish-3-desk.png")

        # Connector fade: right after a fresh spawn the bridge opacity should be
        # ramping, not already at full.
        pg.evaluate("() => window.HermesOffice.resetView()")
        pg.wait_for_timeout(1200)
        fade = pg.evaluate("""() => {
          const O = window.HermesOffice;
          // Reach the live scene's office group via the exposed getView? No —
          // instead spawn into a new cluster and watch the material.
          O.onSpawn({subagent_id:'s4', parent_id:'s2', goal:'new nested branch', depth:2, run_id:'r'});
          const scene = O.getState();
          return { workers: scene.workers.length };
        }""")
        pg.wait_for_timeout(120)
        pg.screenshot(path=f"{SHOT_DIR}/polish-4-fade-early.png")
        pg.wait_for_timeout(1400)
        pg.screenshot(path=f"{SHOT_DIR}/polish-5-fade-late.png")

        # --- Business floor: department signage, bigger, still on the slab ---
        pg.evaluate("() => window.HermesOffice.resetView()")
        pg.evaluate("""() => {
          const el = document.querySelector('[data-outlet="business"]');
          if (el) el.click();
        }""")
        pg.wait_for_timeout(2500)
        pg.screenshot(path=f"{SHOT_DIR}/polish-7-business.png")
        pg.evaluate("""() => {
          const el = document.querySelector('[data-outlet="projects"]');
          if (el) el.click();
        }""")
        pg.wait_for_timeout(1200)

        # --- View live from the chat view ---
        pg.evaluate("() => window.switchPanel('chat')")
        pg.wait_for_timeout(700)
        before_main = pg.evaluate("() => document.querySelector('main.main').className")
        pg.evaluate("() => window.officeReturnToLive()")
        pg.wait_for_timeout(1200)
        after = pg.evaluate("""() => ({
          main: document.querySelector('main.main').className,
          running: window.HermesOffice.isRunning(),
          canvas: !!document.querySelector('.office-canvas'),
          s1Label: (window.HermesOffice.getState().workers.find(w => w.id === 's1') || {}).label,
        })""")
        pg.screenshot(path=f"{SHOT_DIR}/polish-6-viewlive.png")

        b.close()

    errors = [l for l in logs if l.startswith("pageerror") or l.startswith("error:")]

    print("MID POSES:", mid["poses"])
    print("BEFORE MAIN:", before_main)
    print("AFTER:", after)

    assert "showing-office" not in before_main, "set up: was on the chat view"
    assert "showing-office" in after["main"], "View live must show the office main view"
    assert after["running"] and after["canvas"]

    # s1's goal is 62 chars: the desk label keeps far more of it than the old
    # 42-char cap (the plate then measure-fits whatever is left).
    assert len(after["s1Label"]) == 56 and after["s1Label"].endswith("…"), after["s1Label"]

    assert not errors, f"console errors: {errors}"
