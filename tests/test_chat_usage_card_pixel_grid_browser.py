"""The chat sidebar usage card keeps everything under it on whole pixels.

A fractional card height (the plan/percent row inherited line-height 1.7 at
11px = 18.7px) put every row below it on a half pixel. Text snaps to the pixel
grid differently from the CSS-drawn date-group caret, so the caret sat a row
above "LAST WEEK" / "OLDER".
"""

import pytest

from tests._pytest_port import BASE


def test_usage_card_height_is_a_whole_number_of_pixels():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            heights = page.evaluate("""() => {
              switchPanel('chat');
              const out = [];
              for (const skin of ['zeus-2', '']) {
                if (skin) document.documentElement.dataset.skin = skin; else delete document.documentElement.dataset.skin;
                _renderAccountUsage({available: true, provider: 'openai-codex', plan: 'Pro',
                  windows: [{label: 'Weekly', used_percent: 42, reset_at: Date.now() / 1000 + 3600},
                            {label: '5h session', used_percent: 10, reset_at: Date.now() / 1000 + 600}]});
                const card = document.getElementById('chatUsageWidget');
                out.push([skin || 'default', card.hidden, card.getBoundingClientRect().height]);
              }
              return out;
            }""")
        finally:
            browser.close()
    for skin, hidden, height in heights:
        assert hidden is False, skin
        assert height == round(height), (skin, height)
