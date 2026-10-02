"""Static integration checks for the native Job OS navigation shell."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_jobs_panel_has_desktop_mobile_navigation_and_five_subpages():
    """Jobs is a first-class responsive panel, not an embedded external application."""
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    renderer = (ROOT / "static" / "job-os" / "render.js").read_text(encoding="utf-8")

    assert html.count('data-panel="jobs"') == 2
    assert 'id="panelJobs"' in html
    for label in ("Dashboard", "Scout", "Pipeline", "Resume Studio", "Applications"):
        assert label in renderer


def test_jobs_panel_loads_its_lifecycle_modules_and_mx_icon():
    """The shell loads one bounded Job OS module set and uses the shared icon surface."""
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    panels = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
    icons = (ROOT / "static" / "vendor" / "mx-icons" / "work-hub-icons.js").read_text(encoding="utf-8")

    for asset in ("static/job-os/state.js", "static/job-os/api.js", "static/job-os/render.js", "static/job-os/index.js"):
        assert asset in html
    assert "window.JobOS.mount" in panels
    assert "jobs" in icons
