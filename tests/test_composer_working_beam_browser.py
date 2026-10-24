"""The composer shows the agent is working: a border beam runs while S.busy,
on every path that changes it (not only setBusy), and a changed send-button
action swaps its icon in."""

import pytest

from tests._pytest_port import BASE


def test_beam_follows_busy_and_the_send_icon_swaps_on_a_new_action():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            out = page.evaluate("""() => {
              const box = document.getElementById('composerBox'), btn = document.getElementById('btnSend');
              const beam = () => [box.classList.contains('is-working'), getComputedStyle(box, '::after').content !== 'none'];
              const idle = beam();
              btn.classList.remove('icon-swap');
              S.activeStreamId = 'stream-test';
              setBusy(true);
              const busy = beam();
              const swapped = btn.classList.contains('icon-swap');
              // A stream end that only flips S.busy and re-syncs the button.
              S.busy = false; S.activeStreamId = null; updateSendBtn();
              const after = beam();
              btn.classList.remove('icon-swap');
              updateSendBtn();
              const unchanged = btn.classList.contains('icon-swap');
              return {idle, busy, swapped, after, unchanged};
            }""")
        finally:
            browser.close()
    assert out["idle"] == [False, False]
    assert out["busy"] == [True, True]
    assert out["swapped"] is True
    assert out["after"] == [False, False]
    assert out["unchanged"] is False, "re-syncing the same action does not replay the swap"
