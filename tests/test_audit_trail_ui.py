"""Audit Trail UI (Priority 3) wiring guards.

Structural checks pinning the frontend wiring together -- the aggregation
logic itself is covered by tests/test_audit_trail_api.py. See
docs/HERMES_STUDIO_PARITY_PLAN.md, "Priority 3 -- Audit Trail UI".
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
PANELS_JS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
I18N_JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")


def test_nav_tabs_present_in_rail_and_mobile_sidebar():
    rail_section, sidebar_section = INDEX_HTML.split('<aside class="sidebar">', 1)
    assert 'data-panel="audit"' in rail_section
    assert 'data-panel="audit"' in sidebar_section
    assert "switchPanel('audit'" in INDEX_HTML
    assert 'data-i18n-title="tab_audit"' in INDEX_HTML


def test_panel_container_present_with_expected_children():
    idx = INDEX_HTML.index('id="panelAudit"')
    end = INDEX_HTML.index('id="panelSettings"', idx)
    block = INDEX_HTML[idx:end]
    assert 'id="auditRefreshBtn"' in block
    assert 'id="auditSessionFilter"' in block
    assert 'id="auditList"' in block
    assert 'onclick="loadAuditTrail()"' in block


def test_panel_registered_in_switch_dispatch():
    assert "audit: 'tab_audit'" in PANELS_JS
    assert "'audit'" in PANELS_JS[PANELS_JS.index("const MAIN_VIEW_PANELS"):PANELS_JS.index("\n", PANELS_JS.index("const MAIN_VIEW_PANELS"))]
    assert "if (nextPanel === 'audit') await loadAuditTrail();" in PANELS_JS


def test_load_function_calls_the_right_endpoint():
    assert "async function loadAuditTrail()" in PANELS_JS
    idx = PANELS_JS.index("async function loadAuditTrail()")
    end = PANELS_JS.index("\nfunction ", idx)
    body = PANELS_JS[idx:end]
    assert "'/api/audit'" in body
    assert "session_id=" in body
    assert "limit=" in body


def test_session_filter_scoped_request_omits_limit_and_skips_option_resync():
    """Single-session requests must not also pass ?limit= (the endpoint's
    session_id branch ignores it anyway), and must not resync the filter's
    own option list from a single-session response (which would drop every
    other session's option)."""
    idx = PANELS_JS.index("async function loadAuditTrail()")
    end = PANELS_JS.index("\nfunction ", idx)
    body = PANELS_JS[idx:end]
    assert "if (!sessionId) _auditSyncSessionFilterOptions(entries);" in body


def test_status_badge_classes_present_for_every_status():
    for status in ("running", "completed", "interrupted"):
        assert f"audit_status_{status}" in PANELS_JS
        assert f".audit-entry-status-{status}" in STYLE_CSS


def test_entry_row_escapes_untrusted_fields():
    idx = PANELS_JS.index("function _auditEntryRow(entry)")
    end = PANELS_JS.index("\nfunction ", idx)
    body = PANELS_JS[idx:end]
    for field in ("entry.session_id", "entry.content_preview", "entry.status"):
        assert f"esc({field})" in body, f"{field} must be escaped before rendering"


def test_css_uses_theme_tokens_not_hardcoded_colors():
    assert ".audit-entry" in STYLE_CSS
    idx = STYLE_CSS.index("/* Activity panel (audit trail)")
    block = STYLE_CSS[idx: idx + 1800]
    assert "var(--success)" in block
    assert "var(--warning)" in block
    assert "var(--accent)" in block
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block)


def test_i18n_keys_present_in_all_15_locales():
    required_keys = [
        "tab_audit", "audit_all_sessions", "audit_empty", "audit_no_content",
        "audit_status_running", "audit_status_completed", "audit_status_interrupted",
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


def test_no_slash_command_added():
    """Deliberate scope decision (see the parity plan): this is a browse/
    inspect surface, not something scripted through chat -- unlike Personas/
    Skills, which have create/apply actions worth a slash command."""
    assert "cmdAudit" not in (ROOT / "static" / "commands.js").read_text(encoding="utf-8")
