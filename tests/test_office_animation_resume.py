"""Regression: switching to another chat must not strand the previous chat's
delegation frozen on the Office floor.

Symptom report: the Office animates while a delegation is live — figures move,
the connector lines march — then after clicking a different chat in the sidebar
(or ~30s later) the connector lines are dead and the floor is frozen on a run
whose subagents have already finished.

Root cause: static/messages.js gates the subagent_* SSE feed on the active
session id, so once you leave a chat its still-open desks never receive their
completion events; the reconcile poll eventually retires them and the floor is
left frozen. The Office live view is meant to track the running session, so
loadSession() resets it on a cross-session switch — the wiring is asserted by
test_office_panel.py. This test covers the other half: HermesOffice.reset()
actually clears the floor and leaves the render loop running.

Opt-in like the other browser check: HERMES_WEBUI_BROWSER_TESTS=1.
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


def test_office_reset_clears_the_floor_without_stopping_the_loop(base_url, tmp_path):
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
        pg.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        pg.evaluate('''() => {
          document.querySelectorAll('#onboardingOverlay, [role="dialog"]').forEach(el => el.remove());
        }''')

        pg.evaluate("() => window.switchPanel('office')")
        # Software WebGL here can take seconds per frame, and the floor only
        # changes on frames, so every step waits for its state, never a fixed time.
        pg.wait_for_function("() => window.HermesOffice && window.HermesOffice.isRunning()", polling=100, timeout=60000)

        # A live delegation: two running desks, connector lines marching.
        pg.evaluate("""() => {
          const O = window.HermesOffice;
          O.onSpawn({subagent_id:'w1', goal:'do the thing', model:'opus', depth:1, run_id:'runA'});
          O.onSpawn({subagent_id:'w2', goal:'do the other thing', depth:1, run_id:'runA'});
          O.onToolActivity({subagent_id:'w1', tool:'Read', preview:'x.py'});
        }""")
        pg.wait_for_function(
            "() => ['w1', 'w2'].every(id => id in window.HermesOffice.getView().poses)",
            polling=100, timeout=60000,
        )

        before = pg.evaluate("""() => ({
          workers: window.HermesOffice.getState().workers.map(w => w.id),
          running: window.HermesOffice.isRunning(),
          seats: Object.keys(window.HermesOffice.getView().poses),
        })""")

        # What loadSession() now does on a cross-session switch.
        pg.evaluate("() => window.HermesOffice.reset()")
        pg.wait_for_function(
            "() => !window.HermesOffice.getState().workers.length && !Object.keys(window.HermesOffice.getView().poses).length",
            polling=100, timeout=60000,
        )

        after = pg.evaluate("""() => ({
          workers: window.HermesOffice.getState().workers.map(w => w.id),
          running: window.HermesOffice.isRunning(),
          seats: Object.keys(window.HermesOffice.getView().poses),
          pill: (document.getElementById('officePill') || {}).textContent,
        })""")

        # The loop is still alive after the reset: a fresh spawn walks to its
        # desk (an arrival the render loop drives frame by frame) and settles
        # into a working pose.
        pg.evaluate("""() => {
          window.HermesOffice.onSpawn({subagent_id:'w3', goal:'new run', depth:1, run_id:'runB'});
        }""")
        w3_running_seat = pg.evaluate("() => window.HermesOffice.getState().workers.map(w=>w.id)")
        # Settling onto the desk is an arrival walk the render loop advances
        # frame by frame: it only completes if the loop survived the reset.
        try:
            pg.wait_for_function(
                "() => ['work', 'think', 'idle'].includes(window.HermesOffice.getView().poses.w3)",
                polling=200, timeout=120000,
            )
        except Exception:
            pass
        w3_end = pg.evaluate("() => window.HermesOffice.getView().poses.w3")

        b.close()

    errors = [line for line in logs
              if line.startswith("pageerror") or line.startswith("error:")]

    assert set(before["workers"]) == {"w1", "w2"}, before
    assert before["running"] is True
    assert set(before["seats"]) == {"w1", "w2"}, before

    assert after["workers"] == [], f"reset must clear the desks: {after['workers']}"
    assert after["seats"] == [], f"reset must clear the scene seats: {after['seats']}"
    assert after["running"] is True, "reset must not stop the render loop"

    assert w3_running_seat == ["w3"], "the new run seats a worker after reset"
    assert w3_end in ("work", "think", "idle"), (
        f"loop frozen after reset: w3 never settled onto its desk (pose {w3_end!r})"
    )
    assert not errors, f"console errors: {errors}"
