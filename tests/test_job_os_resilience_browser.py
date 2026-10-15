"""Job OS survives a server that is briefly unavailable when the page opens."""

import pytest

from tests._pytest_port import BASE


def _boot(page, hash_="#jobs/dashboard"):
    page.goto(BASE + "/" + hash_, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")


def test_opening_the_page_rides_out_a_restarting_server():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 430, "height": 932}, is_mobile=True, has_touch=True)
            calls = {"n": 0}

            def flaky(route):
                calls["n"] += 1
                if calls["n"] <= 2:  # a restarting server answers with an HTML error page
                    route.fulfill(status=503, content_type="text/html", body="<h1>Bad gateway</h1>")
                else:
                    route.continue_()

            page.route("**/api/job-os/dashboard", flaky)
            _boot(page)
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(".job-os-content", timeout=20000)
            assert calls["n"] >= 3
            assert page.locator(".job-os-error").count() == 0 or not page.locator(".job-os-error").first.inner_text().strip()
        finally:
            browser.close()


def test_a_failed_first_open_offers_a_retry_not_a_dead_end():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 430, "height": 932}, is_mobile=True, has_touch=True)
            state = {"down": True}
            page.route("**/api/job-os/dashboard", lambda route: route.fulfill(status=502, content_type="text/html", body="x") if state["down"] else route.continue_())
            _boot(page)
            page.evaluate("async () => { await switchPanel('jobs'); }")
            page.wait_for_selector(".job-os-error-retry", timeout=30000)
            message = page.inner_text(".job-os-error")
            assert "Job OS request failed" not in message and "restarting" in message
            state["down"] = False
            page.click(".job-os-error-retry")
            page.wait_for_selector(".job-os-content", timeout=20000)
        finally:
            browser.close()
