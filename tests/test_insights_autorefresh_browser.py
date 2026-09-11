"""Browser check: the Insights panel re-fetches /api/insights on a timer while
it is the visible panel, and stops once you leave it. Opt-in."""
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


def test_insights_refetches_on_a_timer_then_stops(base_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    hits = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=swiftshader"])
        pg = b.new_page(viewport={"width": 1300, "height": 900})
        pg.on("request", lambda r: hits.append(r.url) if "/api/insights?" in r.url else None)
        pg.goto(base_url, wait_until="load")
        pg.wait_for_timeout(2500)
        pg.evaluate('() => document.querySelectorAll(\'#onboardingOverlay,[role="dialog"]\').forEach(e => e.remove())')

        pg.evaluate("() => window.switchPanel('insights')")
        pg.wait_for_timeout(1500)
        after_open = len(hits)

        # Shorten the interval so the test doesn't wait 15s a few times over.
        pg.evaluate("""() => {
          // The interval is already running at 15s; just wait one real cycle.
        }""")
        pg.wait_for_timeout(16000)
        after_wait = len(hits)

        pg.evaluate("() => window.switchPanel('chat')")
        pg.wait_for_timeout(500)
        at_leave = len(hits)
        pg.wait_for_timeout(16000)
        after_leave = len(hits)

        b.close()

    print("open:", after_open, "wait:", after_wait, "leave:", at_leave, "after_leave:", after_leave)
    assert after_open >= 1, "panel open fetches insights"
    assert after_wait > after_open, "the timer re-fetched while the panel was visible"
    assert after_leave == at_leave, "the timer stopped after leaving the panel"
