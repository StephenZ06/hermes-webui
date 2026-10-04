"""Job OS navigation lives in the side panel.

The five sections and the per-status pipeline filters render into
#jobOsSidebar; the page itself only keeps a section switcher for narrow
screens, where the side panel is a drawer.
"""

import json
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE


def _post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Origin": BASE},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read() or b"{}")


def _open_jobs(pw, width):
    browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": width, "height": 800})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('jobs'); }")
    page.wait_for_selector("#jobOsRoot .job-os-shell", timeout=15000)
    return browser, page


def test_side_panel_navigates_sections_and_filters_by_stage():
    sync_api = pytest.importorskip("playwright.sync_api")
    marker = uuid.uuid4().hex[:8]
    job = _post("/api/job-os/jobs", {"title": f"Nav role {marker}", "canonical_url": f"https://example.com/{marker}"})["job"]
    with sync_api.sync_playwright() as pw:
        browser, page = _open_jobs(pw, 1280)
        try:
            panel_text = page.inner_text("#panelJobs")
            assert "profile-specific" not in panel_text
            assert "Research, tailor" not in panel_text
            assert not page.is_visible("#jobOsRoot .job-os-tabs"), "desktop has no in-page tab row"

            page.click("#jobOsSidebar [data-job-os-view='scout']")
            page.wait_for_function("() => location.hash === '#jobs/scout'", polling=100, timeout=10000)
            assert page.inner_text("#jobOsSidebar .side-menu-item.active").strip() == "Scout"

            page.click(f"#jobOsSidebar [data-job-os-filter='{job['status']}']")
            page.wait_for_function(
                "(status) => location.hash === '#jobs/pipeline?status=' + status",
                arg=job["status"], polling=100, timeout=10000,
            )
            page.wait_for_selector(f"#jobOsRoot [data-job-id='{job['id']}']", timeout=10000)
            statuses = page.eval_on_selector_all("#jobOsRoot .job-os-job-card .job-os-badge", "els => els.map(e => e.textContent.trim().toLowerCase())")
            assert statuses and set(statuses) == {job["status"].replace("_", " ")}
        finally:
            browser.close()


def test_dashboard_import_saves_a_job_and_escapes_its_title():
    sync_api = pytest.importorskip("playwright.sync_api")
    marker = uuid.uuid4().hex[:8]
    title = f"<img src=x onerror=window.__jobXss=1> {marker}"
    with sync_api.sync_playwright() as pw:
        browser, page = _open_jobs(pw, 1280)
        try:
            page.click("#jobOsSidebar [data-job-os-view='dashboard']")
            page.fill("#job-os-import-form input[name='title']", title)
            page.fill("#job-os-import-form input[name='canonical_url']", f"https://example.com/import-{marker}")
            page.click("#job-os-import-form button[type='submit']")
            page.wait_for_function(
                "(marker) => [...document.querySelectorAll('#jobOsRoot .job-os-job-card strong')].some(e => e.textContent.includes(marker))",
                arg=marker, polling=100, timeout=10000,
            )
            assert page.evaluate("() => window.__jobXss") is None
        finally:
            browser.close()


def test_narrow_screen_keeps_an_in_page_section_switcher():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open_jobs(pw, 390)
        try:
            assert page.is_visible("#jobOsRoot .job-os-tabs")
            page.click("#jobOsRoot .job-os-tabs [data-job-os-view='applications']")
            page.wait_for_function("() => location.hash === '#jobs/applications'", polling=100, timeout=10000)
            assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        finally:
            browser.close()
