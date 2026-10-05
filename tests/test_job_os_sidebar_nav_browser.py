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
            page.wait_for_selector("#job-os-import-form", timeout=10000)
            page.fill("#job-os-import-form input[name='title']", title)
            page.fill("#job-os-import-form input[name='canonical_url']", f"https://example.com/import-{marker}")
            page.click("#job-os-import-form button[type='submit']")
            page.wait_for_function("() => !document.querySelector('#job-os-import-form input[name=title]')?.value", polling=100, timeout=10000)
            page.click("#jobOsSidebar [data-job-os-view='pipeline']")
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


def test_job_lists_read_newest_first():
    """The API lists jobs oldest first; Recent jobs and the pipeline must not
    show the oldest twelve as 'recent'."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open_jobs(pw, 1280)
        try:
            titles = page.evaluate("""() => {
                const jobs = Array.from({length: 14}, (_, i) => ({id: 'j' + i, title: 'Job ' + i, company: 'Co', status: 'discovered', created_at: 1000 + i, updated_at: 1000 + i}));
                const host = document.createElement('div');
                const render = (view) => {
                    host.innerHTML = window.JobOSRender.shell({activeView: view, statusFilter: null, capability: {available: true}, dashboard: null, jobs});
                    return [...host.querySelectorAll('.job-os-job-card strong')].map(e => e.textContent);
                };
                return {dashboard: render('dashboard'), pipeline: render('pipeline')};
            }""")
            assert titles["dashboard"][0] == "Job 13"
            assert "Job 0" not in titles["dashboard"], "the oldest job is not 'recent'"
            assert titles["pipeline"][0] == "Job 13" and titles["pipeline"][-1] == "Job 0"
        finally:
            browser.close()


def test_a_refresh_keeps_unsaved_import_form_input():
    """Every refresh rebuilds the page; text typed into Import must survive it."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open_jobs(pw, 1280)
        try:
            page.wait_for_selector("#job-os-import-form", timeout=10000)
            page.fill("#job-os-import-form input[name='title']", "Typed before refresh")
            page.fill("#job-os-import-form input[name='company']", "Draft Co")
            page.evaluate("() => window.JobOS.refresh()")
            page.evaluate("() => new Promise(r => setTimeout(r, 300))")
            assert page.input_value("#job-os-import-form input[name='title']") == "Typed before refresh"
            assert page.input_value("#job-os-import-form input[name='company']") == "Draft Co"
        finally:
            browser.close()


def test_a_slow_earlier_refresh_cannot_overwrite_a_newer_view():
    """Filter, then Dashboard, while the filtered fetch is still in flight: the
    late filtered response must not land on the dashboard."""
    sync_api = pytest.importorskip("playwright.sync_api")
    marker = uuid.uuid4().hex[:8]
    _post("/api/job-os/jobs", {"title": f"Race role {marker}", "canonical_url": f"https://example.com/race-{marker}"})
    with sync_api.sync_playwright() as pw:
        browser, page = _open_jobs(pw, 1280)
        try:
            page.evaluate("""() => {
                const original = window.JobOSApi.jobs;
                window.JobOSApi.jobs = (status) => status
                    ? new Promise(resolve => setTimeout(() => resolve({jobs: []}), 800))
                    : original(status);
            }""")
            page.evaluate("() => { window.JobOSState.activeView = 'pipeline'; window.JobOSState.statusFilter = 'offer'; window.JobOS.refresh(); window.JobOSState.activeView = 'dashboard'; window.JobOSState.statusFilter = null; window.JobOS.refresh(); }")
            page.evaluate("() => new Promise(r => setTimeout(r, 1500))")
            assert page.get_attribute("#jobOsRoot .job-os-shell", "data-view") == "dashboard"
            assert page.eval_on_selector_all("#jobOsRoot .job-os-job-card", "els => els.length") > 0, "late empty filtered response replaced the dashboard list"
        finally:
            browser.close()


def test_dashboard_metric_icons_match_their_value_and_label_height():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser, page = _open_jobs(pw, 1280)
        try:
            page.wait_for_selector(".job-os-metric img.job-os-metric-icon", timeout=10000)
            rows = page.evaluate("""() => [...document.querySelectorAll('.job-os-metric')].map(card => {
              const icon = card.querySelector('.job-os-metric-icon');
              const value = card.querySelector('.job-os-metric-body strong').getBoundingClientRect();
              const label = card.querySelector('.job-os-metric-body span').getBoundingClientRect();
              const box = icon.getBoundingClientRect();
              return {src: icon.getAttribute('src'), loaded: icon.complete && icon.naturalWidth > 0,
                      icon: box.height, text: label.bottom - value.top, top: box.top, textTop: value.top};
            })""")
        finally:
            browser.close()
    assert [r["src"].rsplit("/", 1)[-1] for r in rows] == [
        "job-os-metric-total.png", "job-os-metric-active.png", "job-os-metric-attention.png", "job-os-metric-applied.png"]
    for row in rows:
        assert row["loaded"], row
        assert abs(row["icon"] - row["text"]) < 1 and abs(row["top"] - row["textTop"]) < 1, row
