"""The Chat page's usage card keeps its last reading when a later refresh
fails or comes back empty; it used to vanish after the next 10-minute poll."""

import pytest

from tests._pytest_port import BASE

GOOD = {"available": True, "provider": "openai-codex", "plan": None,
        "windows": [{"label": "Session", "used_percent": 5.0, "reset_at": None, "detail": None},
                    {"label": "Weekly", "used_percent": 3.0, "reset_at": None, "detail": None}]}


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            tab = browser.new_page(viewport={"width": 1440, "height": 900})
            tab.answer = {"json": GOOD}
            tab.route("**/api/account_usage*", lambda r: r.fulfill(**tab.answer))
            tab.goto(BASE + "/", wait_until="domcontentloaded")
            tab.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
            tab.evaluate("async () => { await loadAccountUsage('alpha'); }")
            yield tab
        finally:
            browser.close()


def _shown(page):
    return page.evaluate("() => { const w = document.getElementById('chatUsageWidget'); return w && !w.hidden ? document.getElementById('chatUsageWidgetPercent').textContent : null; }")


def test_a_failed_or_empty_refresh_keeps_the_last_reading(page):
    first = _shown(page)
    assert first and first.startswith("95%"), first
    page.answer = {"status": 500, "json": {"error": "boom"}}
    page.evaluate("async () => { await loadAccountUsage('alpha'); }")
    assert _shown(page) == first
    page.answer = {"json": {"available": False, "provider": "openai-codex", "windows": []}}
    page.evaluate("async () => { await loadAccountUsage('alpha'); }")
    assert _shown(page) == first


def test_another_profile_without_a_reading_still_hides_the_card(page):
    page.answer = {"status": 500, "json": {"error": "boom"}}
    page.evaluate("async () => { await loadAccountUsage('beta'); }")
    assert _shown(page) is None
