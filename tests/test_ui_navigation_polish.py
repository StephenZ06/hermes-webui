"""Regression coverage for the shared UI-polish behaviours.

These checks deliberately target the single shared implementations so every
panel inherits the behaviour without per-page listeners or polling loops.
"""
from pathlib import Path


ROOT = Path(__file__).parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_direct_sidebar_navigation_setting_has_a_single_persisted_owner():
    config = _read("api/config.py")
    html = _read("static/index.html")
    panels = _read("static/panels.js")
    boot = _read("static/boot.js")

    assert '"sidebar_direct_navigation": False' in config
    assert '"sidebar_direct_navigation"' in config
    assert 'id="settingsSidebarDirectNavigation"' in html
    assert "settingsSidebarDirectNavigation" in panels
    assert "_configureSidebarEdgeReveal" in boot
    assert "requestAnimationFrame" in boot


def test_themed_tooltips_never_restore_native_browser_titles():
    micro = _read("static/micro.js")
    assert "data-mi-title" in micro
    assert "function unpark(el)" in micro
    unpark = micro.split("function unpark(el)", 1)[1].split("function showTip", 1)[0]
    assert "setAttribute('title'" not in unpark
    assert "MutationObserver" in micro


def test_folder_plus_icons_use_the_shared_crisp_variant():
    icons = _read("static/vendor/mx-icons/work-hub-icons.js")
    style = _read("static/style.css")
    notebook = _read("static/notebook/index.js")
    assert "work-hub-icon--plus" in icons
    assert "vector-effect=\"non-scaling-stroke\"" in icons
    assert ".work-hub-project-create .work-hub-icon--plus" in style
    assert "name === 'plus'" in notebook


def test_close_buttons_share_the_quarter_turn_motion_hook():
    micro = _read("static/micro.js")
    style = _read("static/style.css")
    assert "button-close-turn" in micro
    assert ".button-close-turn:hover" in style


def test_deleted_session_recovery_is_shared_by_single_and_batch_delete():
    sessions = _read("static/sessions.js")
    assert "async function _loadReplacementSessionAfterDelete" in sessions
    assert sessions.count("_loadReplacementSessionAfterDelete()") >= 2
    helper = sessions.split("async function _loadReplacementSessionAfterDelete", 1)[1].split("async function deleteSession", 1)[0]
    assert "error.status===404" in helper
