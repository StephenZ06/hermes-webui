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
          O.onSpawn({subagent_id:'demo-2', goal:'reconcile the monthly invoice', depth:1});
          O.onSpawn({subagent_id:'demo-3', parent_id:'demo-1', goal:'inspect the routes configuration file', depth:2});
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

        # Projects is a permanent workstream office: the Conductor and all
        # four named floors remain visible, while the invoice delegate stays
        # exclusively on Business.
        projects_cards = pg.evaluate("""() => Array.from(document.querySelectorAll('.office-dept-card')).map(el => ({
          name: (el.querySelector('.office-dept-card-name') || {}).textContent || '',
          hasName: !!el.querySelector('.office-dept-card-name'),
          hasColor: !!el.style.getPropertyValue('--office-dept-color'),
          left: el.style.left, top: el.style.top,
        }))""")

        # Camera: focusing flies to a desk and zooms in; reset returns exactly.
        camera = pg.evaluate("""async () => {
          const O = window.HermesOffice;
          const overview = O.getView();
          O.focusWorker('demo-1');
          await new Promise(r => setTimeout(r, 1200));
          const focused = O.getView();
          O.resetView();
          await new Promise(r => setTimeout(r, 1200));
          return { overview, focused, back: O.getView() };
        }""")

        pg.evaluate("() => document.querySelector('[data-outlet=\\\"business\\\"]').click()")
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(tmp_path / "office-business.png"))
        # The flip side of demo-2 being held off the Projects floor: it must
        # actually be seated somewhere real on Business, not just dropped.
        business_poses = pg.evaluate("() => window.HermesOffice.getView().poses")

        # Per-department floating stat cards: only the real page can prove the
        # world-to-screen projection actually lands somewhere on the canvas --
        # a node test can check the math is *called*, not that a real
        # OrthographicCamera answers something sane.
        dept_cards = pg.evaluate("""() => Array.from(document.querySelectorAll('.office-dept-card')).map(el => ({
          name: el.querySelector('.office-dept-card-name')?.textContent,
          left: el.style.left, top: el.style.top,
          hasColor: !!el.style.getPropertyValue('--office-dept-color'),
          rect: (() => {
            const r = el.getBoundingClientRect();
            return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
          })(),
        }))""")

        # Task Status panel: whole-office, so it must show the same 3 demo
        # workers on the Business floor too, not just on Projects.
        tasks_on_business = pg.evaluate("""() => ({
          filterCounts: Array.from(document.querySelectorAll('.office-tasks-filter')).map(
            b => b.textContent.trim()),
          rowCount: document.querySelectorAll('.office-tasks-row').length,
        })""")

        pg.evaluate("() => document.querySelector('[data-outlet=\\\"projects\\\"]').click()")
        pg.wait_for_timeout(500)
        # Leaving Business restores the named, coloured Projects floors.
        cards_after_leaving_business = pg.evaluate("""() => Array.from(document.querySelectorAll('.office-dept-card')).map(el => ({
          hasName: !!el.querySelector('.office-dept-card-name'),
          hasColor: !!el.style.getPropertyValue('--office-dept-color'),
        }))""")
        # Still held back the second time, not just on first load.
        projects_poses_again = pg.evaluate("() => window.HermesOffice.getView().poses")
        rows_on_projects = pg.evaluate(
            "() => document.querySelectorAll('.office-tasks-row').length"
        )

        # Filtering to "Done" only shows the one demo worker that completed;
        # clicking a row flies the camera to that worker.
        focus_from_task_row = pg.evaluate("""async () => {
          const before = window.HermesOffice.getView().focusedId;
          document.querySelector('[data-filter="done"]').click();
          const doneRows = document.querySelectorAll('.office-tasks-row').length;
          const row = document.querySelector('.office-tasks-row');
          if (row) row.click();
          await new Promise(r => setTimeout(r, 900));
          return { before, doneRows, after: window.HermesOffice.getView().focusedId };
        }""")
        pg.evaluate("() => window.HermesOffice.resetView()")

        # Collapsing the Task Status column frees canvas width and remembers
        # its state; expanding again gives the width back.
        collapse_toggle = pg.evaluate("""async () => {
          // The floating card's disclosure animates independently of the
          // canvas; wait for the body geometry rather than guessing a delay.
          // Generous ceiling: under SwiftShader WebGL frames are slow, so a
          // .26s transition can take seconds of wall time to finish.
          const settled = async (isDone, timeoutMs) => {
            const start = performance.now();
            let last = null;
            while (performance.now() - start < timeoutMs) {
              const h = body.getBoundingClientRect().height;
              if (isDone(h) && h === last && !card.getAnimations({ subtree: true }).length) return h;
              last = h;
              await new Promise(r => setTimeout(r, 30));
            }
            return body.getBoundingClientRect().height;
          };
          const body = document.getElementById('officeTasksBody');
          // resetView() above closes the selected row's inline details. Wait
          // until no CSS transition is running inside the card (frame-rate
          // independent -- a quiet height can just mean a slow frame), or
          // "before" is a mid-animation height.
          const card = document.getElementById('officeTasks');
          const idle = async (timeoutMs) => {
            const start = performance.now();
            while (performance.now() - start < timeoutMs) {
              if (!card.getAnimations({ subtree: true }).length) return true;
              await new Promise(r => setTimeout(r, 30));
            }
            return false;
          };
          await idle(15000);
          const before = body.getBoundingClientRect().height;
          const btn = document.getElementById('officeTasksCollapseBtn');
          btn.click();
          const collapsedHeight = await settled(h => h < before, 10000);
          const collapsedClass = document.getElementById('officeTasks').classList.contains('is-collapsed');
          const stored = localStorage.getItem('hermes-webui-office-tasks-collapsed');
          btn.click();
          const expandedHeight = await settled(h => h >= before, 10000);
          const expandedClass = document.getElementById('officeTasks').classList.contains('is-collapsed');
          return { before, collapsedClass, collapsedHeight, stored, expandedClass, expandedHeight };
        }""")

        pg.evaluate("() => window.switchPanel('chat')")
        pg.wait_for_timeout(800)
        after = pg.evaluate("""() => ({
          canvasGone: !document.querySelector('.office-canvas'),
          agentCanvasPanelGone: !document.querySelector('#panelAgentCanvas'),
          agentCanvasTabGone: !document.querySelector('[data-panel="agentCanvas"]'),
          // The module stays loaded for the Scheduled-jobs delegation diagram.
          staticTreeRendererAlive:
            !!(window.AgentCanvas && typeof window.AgentCanvas.renderStaticTree === 'function'),
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
    assert camera["focused"]["focusedId"] == "demo-1"
    assert camera["focused"]["zoom"] > camera["overview"]["zoom"], (
        "focusing must zoom in, not merely re-centre"
    )
    assert camera["overview"]["poses"], (
        "the scene reports each figure's rendered pose — an idle behaviour "
        "plays over plain work and is otherwise invisible from outside"
    )
    # demo-2 is business-classified (Finance, via "invoice") and so has no
    # seat on the Projects floor at all.
    assert set(camera["overview"]["poses"]) == {"demo-1", "demo-3"}
    assert camera["back"]["focusedId"] is None
    assert abs(camera["back"]["zoom"] - camera["overview"]["zoom"]) < 1e-6, (
        "reset must return to the framed overview, not an approximation of it"
    )

    assert after["agentCanvasPanelGone"] and after["agentCanvasTabGone"], (
        "the Agent Canvas panel was removed in favour of the office"
    )
    assert after["staticTreeRendererAlive"], (
        "its module stays loaded: the Scheduled-jobs page draws each cron run's "
        "delegation diagram with renderStaticTree"
    )
    assert not errors, f"console errors in the real app: {errors}"

    # 6 standing departments plus "The Floor" -- roster.js's buildRoster()
    # always appends the overflow as a 7th standing entry (the same "a
    # visible overflow is the honest answer" reasoning as everything else on
    # this floor), so it gets a card too. Uncoloured: only a real department
    # tints its floor. The central conductor platform has its own overview
    # card too (officeCardSpecs puts it first; test_office_pod_stat_cards).
    assert len(dept_cards) == 8, "the conductor, every standing department and the overflow get a card"
    by_name = {c["name"]: c for c in dept_cards}
    assert set(by_name) == {
        "Conductor", "Marketing", "Emails", "Sales", "Operations", "Finance", "Delivery", "The Floor",
    }
    for card in dept_cards:
        assert card["left"] and card["top"], (
            f"{card['name']}'s card was never positioned over its pod"
        )
    for name in ("Marketing", "Emails", "Sales", "Operations", "Finance", "Delivery"):
        assert by_name[name]["hasColor"], f"{name}'s card carries no floor colour"
    assert not by_name["The Floor"]["hasColor"], "the overflow is not a department and stays uncoloured"
    for i, card in enumerate(dept_cards):
        for other in dept_cards[i + 1:]:
            a, b = card["rect"], other["rect"]
            overlaps = (a["left"] < b["right"] and a["right"] > b["left"]
                        and a["top"] < b["bottom"] and a["bottom"] > b["top"])
            assert not overlaps, (
                f"{card['name']} and {other['name']} cards overlap on the Business floor"
            )

    # Projects cards are permanent named workstreams around the Conductor.
    assert len(projects_cards) == 5, "Conductor and four Projects workstreams each need one card"
    assert {card["name"] for card in projects_cards if card["hasName"]} == {
        "Conductor", "General", "Research", "Coding", "Documents",
    }
    for card in projects_cards:
        assert card["hasColor"], "a Projects card must match its pod's derived floor colour"
        assert card["left"] and card["top"], "a Projects card was never positioned over its pod"

    assert len(cards_after_leaving_business) == 5, "returning to Projects must restore the four workstream cards"
    for card in cards_after_leaving_business:
        assert card["hasName"], "a Projects workstream card needs its named floor"
        assert card["hasColor"], "a Projects card must match its semantic floor colour"

    # demo-2 ("reconcile the monthly invoice") is business-classified as
    # Finance: held off the Projects floor entirely (both times it's shown,
    # not just on first load), but actually seated for real on Business --
    # not merely dropped everywhere.
    assert "demo-2" in business_poses, "a business-classified worker must actually be seated on Business"
    assert "demo-2" not in projects_poses_again, (
        "a business-classified worker must stay off the Projects floor after switching back to it too"
    )

    assert tasks_on_business["rowCount"] == 3, (
        "the Task Status panel is whole-office and must show the same 3 "
        "workers on Business as it does on Projects"
    )
    assert any("All" in c and "3" in c for c in tasks_on_business["filterCounts"])
    assert rows_on_projects == 3, "leaving Business must not empty the panel"

    assert focus_from_task_row["before"] is None
    assert focus_from_task_row["doneRows"] == 1, (
        "exactly one demo worker (demo-3) completed; the Done filter must show only it"
    )
    assert focus_from_task_row["after"] == "demo-3", (
        "clicking a task row must fly the camera to that worker, same as clicking its desk"
    )

    assert collapse_toggle["collapsedClass"], "the collapse button must add is-collapsed"
    assert collapse_toggle["collapsedHeight"] < collapse_toggle["before"], (
        "collapsing must close the actual Task Status body, not merely relabel the button"
    )
    assert collapse_toggle["stored"] == "1", "the collapsed state must be remembered across visits"
    assert not collapse_toggle["expandedClass"], "clicking again must expand it back"
    assert collapse_toggle["expandedHeight"] == collapse_toggle["before"], (
        f"expanding again must restore the Task Status body to its prior height: {collapse_toggle}"
    )


def test_business_cards_do_not_overlap(base_url):
    """Perspective-compressed Business pods still need individually readable cards."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        ])
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(base_url, wait_until="load")
        page.wait_for_timeout(2500)
        page.evaluate('''() => {
          const kill = sel => document.querySelectorAll(sel).forEach(el => el.remove());
          kill('#onboardingOverlay');
          kill('.onboarding-overlay, .tour-overlay, .tour-popover, [class*="coachmark"]');
          document.querySelectorAll('[role="dialog"]').forEach(el => el.remove());
          window.switchPanel('office');
        }''')
        page.wait_for_timeout(1200)
        page.evaluate("""() => {
          const office = window.HermesOffice;
          office.onSpawn({subagent_id:'card-1', goal:'plan campaign', depth:1});
          office.onSpawn({subagent_id:'card-2', goal:'answer customer emails', depth:1});
          office.onSpawn({subagent_id:'card-3', goal:'close a sales lead', depth:1});
          document.querySelector('[data-outlet="business"]').click();
        }""")
        page.wait_for_timeout(1500)
        cards = page.evaluate("""() => Array.from(document.querySelectorAll('.office-dept-card')).map(el => {
          const r = el.getBoundingClientRect();
          return { name: el.querySelector('.office-dept-card-name')?.textContent,
            left: r.left, top: r.top, right: r.right, bottom: r.bottom };
        })""")
        browser.close()

    assert len(cards) == 8, "Conductor, six departments, and The Floor each keep a card"
    for i, card in enumerate(cards):
        for other in cards[i + 1:]:
            overlaps = (card["left"] < other["right"] and card["right"] > other["left"]
                        and card["top"] < other["bottom"] and card["bottom"] > other["top"])
            assert not overlaps, f"{card['name']} and {other['name']} overlap"
