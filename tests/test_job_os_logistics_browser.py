"""Logistics centre: jobs become parcels in their stage's zone; leaving the view frees the WebGL scene."""

import json
import os
import sqlite3
import urllib.request
import uuid

import pytest

from tests._pytest_port import BASE, TEST_STATE_DIR

DB = TEST_STATE_DIR / "webui_state" / "job_os" / "job_os.db"


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or b"{}")


def _open(page):
    page.goto(BASE + "/#jobs/logistics", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
    page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
    page.evaluate("async () => { await switchPanel('jobs'); }")


def test_logistics_view_degrades_without_webgl():
    """CPU-only headless Chromium has no WebGL: the view says so instead of breaking."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-webgl", "--disable-3d-apis"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page)
            page.wait_for_selector(".logistics-host .logistics-fallback", timeout=20000)
            text = page.inner_text(".logistics-fallback")
            legend = page.inner_text(".logistics-legend")
            page.click("#jobOsSidebar [data-job-os-view='dashboard']")
            page.wait_for_function("() => !document.querySelector('.logistics-host')", timeout=10000)
        finally:
            browser.close()
    assert not errors, errors
    assert "WebGL" in text and "Strong fit" in legend


@pytest.mark.skipif(os.environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
                    reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1 (WebGL under SwiftShader is slow)")
def test_logistics_centre_places_parcels_and_disposes_on_leave():
    sync_api = pytest.importorskip("playwright.sync_api")
    tag = uuid.uuid4().hex[:6]
    ids = {}
    for status in ("scraped", "tailoring", "submitted"):
        job = _post("/api/job-os/jobs", {"title": f"Parcel {status} {tag}", "canonical_url": f"https://jobs.example.test/{uuid.uuid4().hex}"})["job"]
        ids[status] = job["id"]
        with sqlite3.connect(DB) as conn:
            conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job["id"]))
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox",
                                           "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")  # render on demand: SwiftShader frames are slow
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open(page)
            page.wait_for_selector(".logistics-host canvas.logistics-canvas", state="attached", timeout=90000)
            page.wait_for_function("() => [...document.querySelectorAll('.logistics-label small')].some(e => /^\\d+ ·/.test(e.textContent))", timeout=60000)
            labels = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('.logistics-label')].map(e => [e.querySelector('strong').textContent, parseInt(e.querySelector('small').textContent, 10)]))")
            # A re-render (refresh) keeps the same canvas rather than rebuilding the scene.
            page.evaluate("() => { window.__canvas = document.querySelector('.logistics-canvas'); }")
            page.evaluate("async () => { await window.JobOS.refresh(); }")
            same = page.evaluate("() => document.querySelector('.logistics-canvas') === window.__canvas")
            page.click("#jobOsRoot .job-os-tabs [data-job-os-view='dashboard'], #jobOsSidebar [data-job-os-view='dashboard']")
            page.wait_for_function("() => !document.querySelector('.logistics-canvas')", timeout=10000)
        finally:
            browser.close()
    assert not errors, errors
    assert labels["Receiving dock"] >= 1 and labels["Tailoring workshop"] >= 1 and labels["Shipping bay"] >= 1
    assert same


@pytest.mark.skipif(os.environ.get("HERMES_WEBUI_BROWSER_TESTS") != "1",
                    reason="opt-in: set HERMES_WEBUI_BROWSER_TESTS=1 (WebGL under SwiftShader is slow)")
def test_logistics_canvas_keeps_one_drawing_buffer_through_a_sidebar_slide():
    """Reallocating the WebGL buffer every frame of a slide stutters and blanks.

    The canvas keeps the widest width the stage reaches, centred in the
    clipping stage, and is resized once when the slide ends.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox",
                                           "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="no-preference")
            _open(page)
            page.wait_for_selector(".logistics-host canvas.logistics-canvas", state="attached", timeout=240000)
            page.wait_for_timeout(3000)
            result = page.evaluate("""() => new Promise((resolve) => {
              const canvas = document.querySelector('.logistics-canvas');
              const host = document.querySelector('.logistics-host');
              const layout = document.querySelector('.layout');
              const widths = new Set(); let frames = 0;
              toggleSidebar(true);
              const tick = () => {
                if (layout.classList.contains('panel-sliding')) { widths.add(canvas.width); frames += 1; requestAnimationFrame(tick); return; }
                setTimeout(() => resolve({widths: [...widths], frames, final: canvas.width, hostWidth: host.clientWidth,
                                          dpr: window.devicePixelRatio, style: canvas.style.cssText}), 300);
              };
              requestAnimationFrame(tick);
            })""")
        finally:
            browser.close()
    assert result["frames"] >= 5, result
    assert len(result["widths"]) == 1, result  # one drawing buffer for the whole slide
    assert result["style"] == "", result  # slide-time overrides are gone
    assert abs(result["final"] - result["hostWidth"] * result["dpr"]) <= 2, result  # settled to the stage
