"""Command palette + keyboard-shortcuts help modal UI wiring guards.

Structural checks (not a browser test) pinning that the trigger button,
overlay markup, and JS functions introduced for the Command palette feature
stay wired together -- including the deliberate data-source decision (reuse
commands.js's COMMANDS registry rather than a second, independently-authored
command list) and the Ctrl/Cmd+K "new chat" non-collision. See
docs/HERMES_STUDIO_PARITY_PLAN.md, "Priority 3 -- Command palette".
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_trigger_button_and_overlay_markup_present():
    html = read("static/index.html")
    assert 'id="btnCommandPalette"' in html
    assert 'onclick="openCommandPalette()"' in html
    assert 'id="commandPaletteOverlay"' in html
    assert 'id="commandPaletteModal"' in html
    assert 'id="commandPaletteInput"' in html
    assert 'id="commandPaletteList"' in html
    assert 'id="commandPaletteHint"' in html


def test_shortcuts_help_modal_markup_present():
    html = read("static/index.html")
    assert 'id="shortcutsHelpOverlay"' in html
    assert 'id="shortcutsHelpModal"' in html
    assert 'id="shortcutsHelpTitle"' in html
    assert 'id="shortcutsHelpBody"' in html
    assert 'onclick="closeShortcutsHelp()"' in html


def test_panels_js_core_functions_present():
    js = read("static/panels.js")
    for fn in (
        "openCommandPalette", "closeCommandPalette", "isCommandPaletteOpen",
        "_renderCommandPaletteResults", "_filterCommandPaletteEntries",
        "_commandPaletteNavEntries", "_commandPaletteCommandEntries",
        "_commandPaletteActionEntries", "_selectCommandPaletteEntry",
        "_navigateCommandPalette", "_syncPaletteSelection",
        "openShortcutsHelp", "closeShortcutsHelp", "isShortcutsHelpOpen",
        "_renderShortcutsHelp", "_shortcutsHelpGroups",
    ):
        assert f"function {fn}(" in js, f"{fn} not defined in panels.js"


def test_palette_reuses_commands_registry_not_a_second_list():
    """Guards the plan's core decision: the palette's Commands section must
    read directly from commands.js's COMMANDS array, not a second,
    independently-authored list of command names/descriptions."""
    js = read("static/panels.js")
    fn_match = re.search(
        r"function _commandPaletteCommandEntries\(\)\{(.*?)\n\}",
        js,
        re.DOTALL,
    )
    assert fn_match, "_commandPaletteCommandEntries not found"
    body = fn_match.group(1)
    assert "COMMANDS" in body
    assert "getMatchingCommands" not in body


def test_palette_nav_section_is_dom_driven():
    """Guards that Navigate entries are read live from the rail rather than
    a second hardcoded panel list that could drift from MAIN_VIEW_PANELS."""
    js = read("static/panels.js")
    fn_match = re.search(
        r"function _commandPaletteNavEntries\(\)\{(.*?)\n\}",
        js,
        re.DOTALL,
    )
    assert fn_match, "_commandPaletteNavEntries not found"
    body = fn_match.group(1)
    assert ".rail .nav-tab[data-panel]" in body
    assert "nav-tab-hidden" in body


def test_command_selection_inserts_into_composer_not_auto_execute():
    """Guards the safety decision: selecting a command entry must insert
    into the composer (ta.value=...), never call executeCommand()/send()
    directly from the palette."""
    js = read("static/panels.js")
    fn_match = re.search(
        r"function _selectCommandPaletteEntry\(idx\)\{(.*?)\n\}",
        js,
        re.DOTALL,
    )
    assert fn_match, "_selectCommandPaletteEntry not found"
    body = fn_match.group(1)
    assert "entry.type==='command'" in body
    assert "ta.value=" in body
    assert "executeCommand(" not in body


def test_boot_js_registers_shortcuts_without_new_chat_collision():
    js = read("static/boot.js")
    # Ctrl/Cmd+Shift+P opens the palette.
    assert "openCommandPalette()" in js
    assert "(e.key==='p'||e.key==='P')" in js
    assert "e.shiftKey" in js
    # Bare '?' opens the shortcuts modal.
    assert "openShortcutsHelp()" in js
    assert "e.key==='?'" in js
    # The pre-existing Ctrl/Cmd+K "new chat" binding must be untouched --
    # regression guard against reintroducing the shortcut collision the plan
    # doc explicitly resolved by choosing Shift+P instead of plain K.
    assert "await newSession();await renderSessionList();closeMobileSidebar();$('msg').focus();" in js


def test_escape_closes_palette_and_shortcuts_help():
    js = read("static/boot.js")
    assert "isCommandPaletteOpen" in js
    assert "closeCommandPalette();return;" in js
    assert "isShortcutsHelpOpen" in js
    assert "closeShortcutsHelp();return;" in js


def test_css_wiring_present():
    css = read("static/style.css")
    assert ".cmdk-overlay{" in css
    assert ".cmdk-modal{" in css
    assert ".cmdk-input{" in css
    assert ".shortcuts-help-modal{" in css
    # List rows reuse the existing composer-autocomplete item classes rather
    # than redefining their own -- spot check the reused class names appear
    # (they're defined once, above the cmdk block, and referenced by the JS
    # renderer via className='cmd-item').
    assert ".cmd-item{" in css


def test_i18n_keys_present_in_all_15_locales():
    src = read("static/i18n.js")
    required_keys = [
        "command_palette", "command_palette_placeholder", "command_palette_no_results",
        "command_palette_section_navigate", "command_palette_section_commands",
        "command_palette_section_actions", "command_palette_hint",
        "keyboard_shortcuts", "keyboard_shortcuts_close",
        "shortcuts_group_general", "shortcuts_group_sessions", "shortcuts_group_composer",
        "shortcut_open_palette", "shortcut_open_shortcuts", "shortcut_new_chat",
        "shortcut_toggle_sidebar", "shortcut_focus_composer", "shortcut_open_settings",
        "shortcut_navigate_sessions", "shortcut_send", "shortcut_send_newline",
    ]
    locale_keys = re.findall(r"^  (?:'([a-zA-Z-]+)'|([a-zA-Z-]+)): \{$", src, re.MULTILINE)
    locales = [a or b for a, b in locale_keys]
    assert locales == [
        "en", "it", "ja", "ru", "es", "de", "zh", "zh-Hant", "pt", "ko",
        "fr", "cs", "tr", "pl", "vi",
    ], locales

    starts = [m.start() for m in re.finditer(r"^  (?:'[a-zA-Z-]+'|[a-zA-Z-]+): \{$", src, re.MULTILINE)]
    starts.append(len(src))
    for i, locale in enumerate(locales):
        block = src[starts[i]:starts[i + 1]]
        for key in required_keys:
            count = len(re.findall(rf"^    {re.escape(key)}: ", block, re.MULTILINE))
            assert count == 1, f"{locale} locale: expected exactly one '{key}', found {count}"
