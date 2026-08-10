"""Onboarding tour (Priority 3) wiring guards.

hermes-webui's existing static/onboarding.js is only the first-run setup
wizard -- provider/workspace/password configuration, never a guided
walkthrough of the live UI (see docs/HERMES_STUDIO_PARITY_PLAN.md,
"Onboarding tour" for the investigation that confirmed this before any code
was written). These tests pin the new static/tour.js spotlight-and-tooltip
engine that was built to close that specific, confirmed gap.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOUR_JS = (ROOT / "static" / "tour.js").read_text(encoding="utf-8")
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
I18N_JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
CONFIG_PY = (ROOT / "api" / "config.py").read_text(encoding="utf-8")


def test_tour_engine_defines_core_functions():
    for fn in (
        "APP_TOUR_STEPS",
        "function startAppTour(",
        "function _maybeAutoStartAppTour(",
        "function _endAppTour(",
        "function nextAppTourStep(",
        "function prevAppTourStep(",
        "function skipAppTour(",
    ):
        assert fn in TOUR_JS, f"{fn} missing from static/tour.js"


def test_step_targets_reference_real_elements_in_index_html():
    """Every step selector (except the no-target welcome step) must point at
    an id or data-panel value that actually exists in index.html today --
    guards against a step silently pointing at a removed/renamed element."""
    selector_lists = re.findall(r"selectors:\[(.*)\],$", TOUR_JS, re.MULTILINE)
    assert len(selector_lists) == 5, "expected 5 steps with real targets (6 total minus the welcome step)"
    for raw in selector_lists:
        selectors = re.findall(r"'([^']+)'", raw)
        assert selectors, f"no selectors parsed from {raw!r}"
        found_any = False
        for sel in selectors:
            m = re.search(r'id="([^"]+)"', sel)
            if m:
                if f'id="{m.group(1)}"' in INDEX_HTML:
                    found_any = True
                continue
            m = re.search(r'#([\w-]+)', sel)
            if m and f'id="{m.group(1)}"' in INDEX_HTML:
                found_any = True
                continue
            m = re.search(r'data-panel="([^"]+)"', sel)
            if m and f'data-panel="{m.group(1)}"' in INDEX_HTML:
                found_any = True
        assert found_any, f"none of {selectors} found in index.html"


def test_welcome_step_has_no_target():
    idx = TOUR_JS.index("const APP_TOUR_STEPS")
    end = TOUR_JS.index("];", idx)
    block = TOUR_JS[idx:end]
    assert "selectors:null" in block


def test_step_skipped_gracefully_when_target_not_visible():
    body = TOUR_JS[TOUR_JS.index("function _renderAppTourStep("):]
    body = body[:body.index("\nfunction ", 1)]
    assert "_appTourIndex++" in body
    assert "offsetParent" in TOUR_JS  # visibility check lives in _appTourVisibleTarget


def test_boot_js_triggers_tour_after_onboarding_settles():
    idx = BOOT_JS.index("await _onboardingReady;")
    tail = BOOT_JS[idx: idx + 600]
    assert "_maybeAutoStartAppTour()" in tail
    assert "window._tourCompleted=!!s.tour_completed;" in BOOT_JS


def test_tour_completed_setting_registered_like_other_toggles():
    assert '"tour_completed": False' in CONFIG_PY
    bool_keys_idx = CONFIG_PY.index("_SETTINGS_BOOL_KEYS = {")
    bool_keys_end = CONFIG_PY.index("\n}", bool_keys_idx)
    assert '"tour_completed",' in CONFIG_PY[bool_keys_idx:bool_keys_end]


def test_end_tour_persists_via_existing_settings_endpoint():
    idx = TOUR_JS.index("async function _endAppTour(")
    end = TOUR_JS.index("\nfunction ", idx)
    body = TOUR_JS[idx:end]
    assert "/api/settings" in body
    assert "tour_completed" in body


def test_overlay_and_help_card_markup_present():
    assert 'id="appTourOverlay"' in INDEX_HTML
    assert 'id="appTourSpotlight"' in INDEX_HTML
    assert 'id="appTourCard"' in INDEX_HTML
    assert 'onclick="startAppTour()"' in INDEX_HTML.replace(
        'onclick="event.preventDefault();startAppTour();"',
        'onclick="startAppTour()"',
    ) or "startAppTour();" in INDEX_HTML
    assert 'data-i18n="settings_help_tour_label"' in INDEX_HTML


def test_tour_js_script_tag_loaded_before_boot_js():
    tour_idx = INDEX_HTML.index('src="static/tour.js')
    boot_idx = INDEX_HTML.index('src="static/boot.js')
    assert tour_idx < boot_idx


def test_css_card_uses_theme_tokens_not_hardcoded_hex():
    idx = STYLE_CSS.index("/* App tour (Priority 3)")
    end = STYLE_CSS.index(".reconnect-banner{", idx)
    block = STYLE_CSS[idx:end]
    card_block = block[block.index(".app-tour-card{"):]
    assert "var(--text)" in card_block or "var(--accent-bg-strong)" in card_block
    # Hardcoded rgba() dim for the backdrop/spotlight is an explicit,
    # documented exception (matches .onboarding-overlay's own precedent) --
    # only the card itself is checked for hex-literal colors.
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", card_block)


def test_i18n_keys_present_in_all_15_locales():
    required_keys = [
        "tour_step_welcome_title", "tour_step_welcome_body",
        "tour_step_new_chat_title", "tour_step_new_chat_body",
        "tour_step_composer_title", "tour_step_composer_body",
        "tour_step_kanban_title", "tour_step_kanban_body",
        "tour_step_skills_title", "tour_step_skills_body",
        "tour_step_settings_title", "tour_step_settings_body",
        "tour_next", "tour_back", "tour_skip", "tour_done", "tour_step_counter",
        "settings_help_tour_label", "settings_help_tour_desc", "settings_help_tour_link",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", I18N_JS, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert len(locales) == 15, locales

    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", I18N_JS, re.MULTILINE)]
    starts.append(len(I18N_JS))
    for name, start, end in zip(locales, starts, starts[1:]):
        block = I18N_JS[start:end]
        missing = [k for k in required_keys if f"{k}:" not in block]
        assert not missing, f"locale {name!r} missing keys: {missing}"


def test_esc_key_handler_wired_and_removed_on_end():
    assert "document.addEventListener('keydown',_appTourEsc)" in TOUR_JS
    assert "document.removeEventListener('keydown',_appTourEsc)" in TOUR_JS
