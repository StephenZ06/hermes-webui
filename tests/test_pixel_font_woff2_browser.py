"""The Dashboard's pixel font loads as WOFF2 (30 KB), not the 118 KB TTF."""

import pytest

from tests._pytest_port import BASE


def test_the_pixel_font_is_fetched_as_woff2():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page()
            fonts = []
            page.on("response", lambda r: fonts.append((r.url.rsplit("/", 1)[1].split("?")[0], r.headers.get("content-type", "")))
                    if "press-start-2p/" in r.url else None)
            page.goto(BASE + "/", wait_until="load")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            page.evaluate("async () => { await document.fonts.load('16px \"Press Start 2P\"'); }")
            page.wait_for_timeout(300)
        finally:
            browser.close()
    assert fonts == [("PressStart2P-Regular.woff2", "font/woff2")], fonts
