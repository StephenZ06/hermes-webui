"""The app shell must keep producing frames at idle.

Playwright's waits and actionability checks (wait_for_function's default
polling, hover/click "stable" checks) run on requestAnimationFrame. The Hermes
CLI launcher's progress segments pulsed forever even while invisible (not
loading); under the first-run onboarding overlay's full-screen backdrop blur
and large card shadow, that per-frame repaint stalled the first frame for tens
of seconds in headless Chromium, and every such wait timed out.
"""
import pytest

from tests._pytest_port import BASE

_FRAMES = (
    "() => new Promise(resolve => { let n = 0; const start = performance.now();"
    " function tick() { n++; if (performance.now() - start < 1000) requestAnimationFrame(tick); else resolve(n); }"
    " requestAnimationFrame(tick); setTimeout(() => resolve(n), 3000); })"
)


def test_the_app_shell_renders_frames_in_headless_chromium():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(
                viewport={"width": 360, "height": 800},
                is_mobile=True, has_touch=True, device_scale_factor=2,
            )
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=15000
            )
            assert page.evaluate(_FRAMES) > 10
        finally:
            browser.close()
