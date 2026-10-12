from pathlib import Path

import pytest

from tests._pytest_port import BASE


ROOT = Path(__file__).resolve().parents[1]


def test_resume_preview_exposes_zoom_controls_and_pinch_binding():
    render = (ROOT / "static/job-os/render.js").read_text(encoding="utf-8")
    index = (ROOT / "static/job-os/index.js").read_text(encoding="utf-8")
    state = (ROOT / "static/job-os/state.js").read_text(encoding="utf-8")

    assert 'data-job-os-action="preview-zoom"' in render
    assert "data-step=\"${step}\"" in render
    assert 'data-job-os-action="resume-preview-close"' in render
    assert "previewZoom" not in state or "previewZoom" in index
    assert "function setPreviewZoom" in index
    assert "event.touches.length !== 2" in index
    assert "--preview-zoom" in index


def test_mobile_job_os_controls_have_containment_and_safe_area_rules():
    css = (ROOT / "static/style.css").read_text(encoding="utf-8")

    assert ".resume-preview-tools" in css
    assert ".resume-preview-ctl" in css
    assert ".match-ring small" in css and "white-space:normal" in css
    assert ".job-os-savebar-note{margin-left:auto" in css
    assert "padding-bottom:max(12px,env(safe-area-inset-bottom,0px))" in css


def test_resume_preview_zoom_controls_update_the_live_mobile_preview():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 430, "height": 932}, is_mobile=True, has_touch=True)
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true && window.JobOSRender && window.JobOS")
            page.evaluate("""async () => {
              document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach((node) => node.remove());
              await switchPanel('jobs');
              await JobOS.refresh();
              JobOSState.activeView = 'resume-studio';
              JobOSState.resumePreview = {kind: 'html', url: 'about:blank', title: 'Mobile preview'};
              JobOSState.previewZoom = 1;
              const root = document.getElementById('jobOsRoot');
              root.innerHTML = JobOSRender.shell(JobOSState);
            }""")
            zoom = page.locator(".resume-preview-level")
            pages = page.locator(".resume-preview-pages")
            page.get_by_role("button", name="Zoom in").click()
            assert zoom.inner_text() == "125%"
            width_after_in = pages.evaluate("node => node.getBoundingClientRect().width")
            page.get_by_role("button", name="Zoom out").click()
            assert zoom.inner_text() == "100%"
            width_after_out = pages.evaluate("node => node.getBoundingClientRect().width")
            assert width_after_in > width_after_out
            page.get_by_role("button", name="Close preview").click()
            page.wait_for_selector(".resume-preview", state="detached")
        finally:
            browser.close()
