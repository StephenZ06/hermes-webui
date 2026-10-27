"""Dictation picks server Whisper again after an old browser-STT pin.

Older builds stored ``mic_force_mediarecorder='0'`` after one server STT error
and never probed again, so the mic stayed on browser SpeechRecognition for good.
The stale value is dropped at boot and the capability probe runs again.
"""

import pytest

from tests._pytest_port import BASE


def _boot(page):
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)


@pytest.mark.parametrize("stored, kept", [("0", None), ("1", "1")])
def test_stale_browser_stt_pin_is_dropped_and_probe_runs(stored, kept):
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context()
            context.add_init_script(f"""
                try {{ localStorage.setItem('mic_force_mediarecorder', '{stored}'); }} catch (e) {{}}
                window.__probes = 0;
                const realFetch = window.fetch;
                window.fetch = function (url, opts) {{
                    if (String(url).includes('api/transcribe/capability')) window.__probes += 1;
                    return realFetch.apply(this, arguments);
                }};
            """)
            page = context.new_page()
            _boot(page)
            state = page.evaluate("() => [localStorage.getItem('mic_force_mediarecorder'), window.__probes]")
            assert state[0] == kept
            # '1' already means server STT, so there is nothing to probe.
            assert state[1] == (1 if kept is None else 0)
        finally:
            browser.close()
