"""Chat page polish: the composer menus' square clear/add buttons as tall as
their inputs, placeholders 1px higher, tighter menu rows, the profile switch's
name shimmer in place of a spinner, suggestions on the page background, and
the deeper blue on the usage card's selected window."""
import json

import pytest

from tests._pytest_port import BASE

USAGE = {"available": True, "provider": "openai-codex", "plan": "ChatGPT Pro",
         "windows": [{"key": "session", "label": "5-hour", "used_percent": 20, "reset_at": None},
                     {"key": "weekly", "label": "Weekly", "used_percent": 40, "reset_at": None}]}


@pytest.fixture
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1899, "height": 990})
        page.route("**/api/account_usage*", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(USAGE)))
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof S !== 'undefined' && S._bootReady === true", polling=100, timeout=30000)
        page.evaluate("() => document.querySelectorAll('#onboardingOverlay,#appTourOverlay').forEach(e => e.remove())")
        page.evaluate("async () => { await switchPanel('chat'); }")
        page.wait_for_timeout(500)
        yield page
        browser.close()


def _box(page, sel):
    return page.evaluate("(s) => { const e = document.querySelector(s); return [e.offsetWidth, e.offsetHeight]; }", sel)


def test_model_menu_buttons_are_squares_as_tall_as_their_inputs(page):
    page.evaluate("() => toggleModelDropdown()")
    page.wait_for_selector("#composerModelDropdown .model-search-clear", state="visible", timeout=10000)
    page.wait_for_timeout(600)  # the menu opens with a short scale-in
    for button, field in ((".model-search-clear", ".model-search-input"), (".model-custom-btn", ".model-custom-input")):
        b = _box(page, "#composerModelDropdown " + button)
        f = _box(page, "#composerModelDropdown " + field)
        assert b[0] == b[1] == f[1], (button, b, f)
        radius = page.evaluate("(s) => getComputedStyle(document.querySelector(s)).borderTopLeftRadius", "#composerModelDropdown " + button)
        assert radius == "6px", (button, radius)
    pads = page.evaluate("""() => ['.model-search-input', '.model-custom-input'].map(s => {
      const c = getComputedStyle(document.querySelector('#composerModelDropdown ' + s));
      return parseFloat(c.paddingBottom) - parseFloat(c.paddingTop); })""")
    assert pads == [4, 4], pads


def test_workspace_search_clear_matches_its_input(page):
    page.evaluate("() => toggleComposerWsDropdown()")
    page.wait_for_selector("#composerWsDropdown .ws-search-clear", state="visible", timeout=10000)
    page.wait_for_timeout(600)
    b = _box(page, "#composerWsDropdown .ws-search-clear")
    f = _box(page, "#composerWsDropdown .ws-search-input")
    assert b[0] == b[1] == f[1], (b, f)


def test_composer_menu_rows_are_compact(page):
    page.evaluate("() => toggleComposerWsDropdown()")
    page.wait_for_selector("#composerWsDropdown .ws-opt", state="visible", timeout=10000)
    ws = page.evaluate("() => { const c = getComputedStyle(document.querySelector('#composerWsDropdown .ws-opt')); return [c.paddingTop, c.paddingBottom]; }")
    assert ws == ["6px", "6px"], ws
    page.evaluate("() => toggleProfileDropdown()")
    page.wait_for_selector("#profileDropdown .profile-opt", state="visible", timeout=10000)
    prof = page.evaluate("() => { const c = getComputedStyle(document.querySelector('#profileDropdown .profile-opt')); return [c.paddingTop, c.paddingBottom]; }")
    assert prof == ["6px", "6px"], prof


def test_profile_switch_shimmers_the_name_instead_of_spinning(page):
    state = page.evaluate("""() => {
      const chip = document.getElementById('profileChip');
      chip.classList.add('switching');
      const icon = getComputedStyle(chip.querySelector('.composer-profile-icon'), '::after').content;
      const label = getComputedStyle(document.getElementById('profileChipLabel')).animationName;
      chip.classList.remove('switching');
      return {icon, label};
    }""")
    assert state["icon"] in ("none", "normal"), state
    assert state["label"] == "mi-shimmer", state


def test_suggestions_sit_on_the_page_background(page):
    bg = page.evaluate("() => getComputedStyle(document.querySelector('.suggestion')).backgroundColor")
    assert bg == "rgba(0, 0, 0, 0)", bg


def test_selected_usage_window_is_a_deeper_blue(page):
    page.evaluate("() => loadAccountUsage()")
    page.wait_for_selector("#chatUsageWidgetWindowToggle:not([hidden])", timeout=10000)
    fill = page.evaluate("() => getComputedStyle(document.getElementById('chatUsageWidgetWindowToggle'), '::before').backgroundColor")
    # An opaque mix with the page colour, not the old 16% wash over transparent.
    assert "/ 0.16" not in fill and not fill.startswith("rgba"), fill
