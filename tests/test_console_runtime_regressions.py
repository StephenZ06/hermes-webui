"""Regression coverage for browser-console failures fixed in the WebUI shell."""

from pathlib import Path

from tests.conftest import requires_agent_modules


ROOT = Path(__file__).resolve().parents[1]


def test_viewport_resizes_the_visual_viewport_for_blocknote_keyboard():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    assert 'interactive-widget=resizes-content' in html


def test_job_os_triage_shortcut_normalizes_a_missing_key_before_comparing_it():
    source = (ROOT / "static/job-os/index.js").read_text(encoding="utf-8")
    start = source.index("function onTriageKey(event)")
    end = source.index("document.addEventListener('keydown', onTriageKey);", start)
    handler = source[start:end]

    assert "const key=String(event.key||'').toLowerCase();" in handler
    assert handler.index("const key=String(event.key||'').toLowerCase();") < handler.index(
        "state.activeView"
    )
    assert "event.key.toLowerCase()" not in handler


@requires_agent_modules
def test_profile_scoped_skill_listing_uses_the_agent_public_sort_helper(monkeypatch, tmp_path):
    """Agent upgrades may expose ``sort_skills`` without its old private alias."""
    from api import routes

    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "example"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: example\ndescription: A test skill\n---\n\n# Example\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(routes, "_get_disabled_skill_names_for_profile", lambda: set())

    result = routes._skills_list_from_dir(skills_dir)

    assert result["success"] is True
    assert [skill["name"] for skill in result["skills"]] == ["example"]


def test_notes_editor_marks_its_media_surface_safe_for_sidebar_layout_slides():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    assert 'id="mainNotebook" class="main-view" data-slide-safe' in html


def test_notes_video_keeps_sidebar_expand_on_the_layout_motion_path():
    """A BlockNote video must not demote only Notes to the jumpy FLIP fallback."""
    import pytest

    sync_api = pytest.importorskip("playwright.sync_api")
    from tests._pytest_port import BASE

    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_function(
                "() => typeof S !== 'undefined' && S._bootReady === true",
                polling=100,
                timeout=30000,
            )
            page.evaluate(
                "() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())"
            )
            page.evaluate("async () => { await switchPanel('notebook'); }")
            outcome = page.evaluate("""() => new Promise((resolve) => {
              const main = document.querySelector('.main');
              const layout = document.querySelector('.layout');
              const video = document.createElement('video');
              document.querySelector('#mainNotebook').appendChild(video);
              toggleSidebar(true);
              requestAnimationFrame(() => requestAnimationFrame(() => resolve({
                layoutSlide: layout.classList.contains('panel-sliding'),
                margin: main.style.marginLeft,
                transform: getComputedStyle(main).transform,
              })));
            })""")
        finally:
            browser.close()

    assert outcome["layoutSlide"], outcome
    assert outcome["margin"].endswith("px"), outcome
    assert outcome["transform"] == "none", outcome
