"""Regression coverage for the Chat sidebar's usage card hierarchy."""
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
HTML = (REPO / "static/index.html").read_text(encoding="utf-8")
UI = (REPO / "static/ui.js").read_text(encoding="utf-8")
SESSIONS = (REPO / "static/sessions.js").read_text(encoding="utf-8")
CSS = (REPO / "static/style.css").read_text(encoding="utf-8")


def test_usage_card_exposes_both_codex_rate_limit_windows():
    assert 'id="chatUsageWidgetWindowToggle"' in HTML
    assert 'data-usage-window="session"' in HTML
    assert 'data-usage-window="weekly"' in HTML
    assert 'data-usage-window="monthly"' not in HTML
    assert 'id="chatUsageWidgetPlan"' in HTML
    assert 'id="chatUsageWidgetLabelStage"' in HTML
    assert "function selectAccountUsageWindow(windowKey)" in UI
    assert "_accountUsageWindowKey" in UI
    assert "let _accountUsageWindow='session';" in UI


def test_usage_card_places_window_switcher_above_plan_and_remaining_quota():
    assert HTML.index('id="chatUsageWidgetWindowToggle"') < HTML.index('id="chatUsageWidgetBattery"')
    assert HTML.index('id="chatUsageWidgetPlan"') < HTML.index('id="chatUsageWidgetPercent"')
    assert 'class="chat-usage-widget-reset"><span id="chatUsageWidgetReset"></span>' in HTML
    assert ".chat-usage-widget-title-row .chat-usage-widget-window-toggle" in CSS


def test_usage_card_uses_an_animated_ten_cell_battery_meter_for_remaining_quota():
    assert 'class="chat-usage-widget-battery" id="chatUsageWidgetBattery"' in HTML
    assert HTML.count('class="chat-usage-widget-battery-cell"') == 10
    assert "function _renderAccountUsageBattery(remainingPercent)" in UI
    assert "_renderAccountUsageBattery(remaining);" in UI
    assert "cell.classList.toggle('is-filled',index<filledCells);" in UI
    assert ".chat-usage-widget-battery{display:grid;grid-template-columns:repeat(10,1fr);" in CSS
    assert ".chat-usage-widget-battery-cell{min-width:0;height:7px;" in CSS
    assert "transition:background-color .3s ease,border-color .3s ease,opacity .3s ease,transform .3s ease;" in CSS


def test_sidebar_has_explicit_workspace_and_conversation_sections():
    assert "chat-sidebar-section--workspaces" in SESSIONS
    assert "chat-sidebar-section--conversations" in SESSIONS
    assert "WORKSPACES" in SESSIONS
    assert "CONVERSATIONS" in SESSIONS
    assert ".chat-sidebar-section-heading" in CSS
    assert ".chat-usage-widget-window-toggle" in CSS
    assert ".chat-sidebar-section--workspaces .project-folder-list" in CSS
    # Spacing tokens are scoped to the chat panel and consumed by the search row.
    tokens = re.search(r"#panelChat\{([^}]*)\}", CSS)
    assert tokens and re.search(r"--chat-sidebar-divider-space:\d+px;", tokens.group(1))
    assert "#panelChat .sidebar-search{padding-bottom:var(--chat-sidebar-divider-space);}" in CSS
    # Sections are separated by their headings: a label centred between hairlines.
    for section in ("workspaces", "conversations"):
        rule = f".chat-sidebar-section--{section} .chat-sidebar-section-heading::before"
        assert rule in CSS, rule
    assert '.chat-sidebar-section-heading::after{content:"";height:1px;flex:1;background:var(--border);}' in CSS


def test_usage_window_switch_uses_shared_type_and_motion_tokens():
    assert "--chat-sidebar-card-type-size:11px;" in CSS
    assert ".chat-usage-widget-window-content.is-incoming" in CSS
    assert "chatUsageWindowTextEnter" in CSS
    assert "is-incoming" in UI
    assert ".chat-sidebar-section--conversations{margin:0 0 2px;" in CSS
    assert ".chat-usage-widget-label-stage{position:relative;display:inline-flex;align-items:center;" in CSS
    assert "text-transform:uppercase" in CSS
    assert ".chat-usage-widget-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:10px;" in CSS
    assert "const isNeuralwatt=String(data&&data.provider||'').toLowerCase()==='neuralwatt';" in UI
    assert "toggle.hidden=isNeuralwatt||selectable.length<2;" in UI
    assert "toggle.dataset.activeWindow=_accountUsageWindow;" in UI
    assert "label.textContent=isNeuralwatt?'MONTHLY USAGE'" in UI
    assert "provider==='neuralwatt'?'NeuralWatt Basic'" in UI
    assert ".chat-usage-widget-reset{display:block;width:100%;margin-top:3px" in CSS
    assert "text-align:right" in CSS
    assert "font-size:10px" in CSS
    assert "text-transform:lowercase" in CSS


def test_neuralwatt_usage_toggle_honors_the_hidden_attribute():
    """The stylesheet must not override JS hiding the Codex-only toggle."""
    assert ".chat-usage-widget-window-toggle[hidden]{display:none!important;}" in CSS


def test_neuralwatt_rate_limited_response_keeps_the_monthly_card_visible():
    assert "data&&data.rate_limited" in UI
    assert "t('provider_quota_unavailable')" in UI
    assert "MONTHLY USAGE" in UI


def test_usage_widget_fades_on_provider_change():
    assert "let _lastAccountUsageProvider;" in UI
    assert "function _fadeAccountUsageWidget(callback)" in UI
    assert "_fadeAccountUsageWidget(()=>_renderAccountUsageImpl(data))" in UI
    assert "const providerChanged=_lastAccountUsageProvider!==undefined && provider!==_lastAccountUsageProvider;" in UI
    assert ".chat-usage-widget.is-fading{opacity:0;}" in CSS
    assert ".chat-usage-widget.is-fading" in CSS
    assert "transition:opacity .18s ease" in CSS


def test_usage_window_switch_keeps_an_outgoing_content_layer_until_it_finishes():
    assert 'id="chatUsageWidgetWindowStage"' in HTML
    assert 'id="chatUsageWidgetWindowContent"' in HTML
    assert "outgoing=content.cloneNode(true);" in UI
    assert "outgoing.querySelectorAll('[id]').forEach(el=>el.removeAttribute('id'));" in UI
    assert "outgoing.remove();" in UI
    assert "stage.querySelectorAll('.is-outgoing').forEach(el=>el.remove());" in UI
    assert ".chat-usage-widget-window-content.is-outgoing" in CSS
    assert "chatUsageWindowTextExit" in CSS
    assert "outgoingLabel=label.cloneNode(true);" in UI
    assert "if(outgoingLabel) outgoingLabel.remove();" in UI


def test_usage_window_switch_has_one_sliding_active_indicator():
    assert "toggle.dataset.activeWindow=_accountUsageWindow;" in UI
    assert ".chat-usage-widget-window-toggle::before" in CSS
    assert ".chat-usage-widget-window-toggle[data-active-window=\"weekly\"]::before" in CSS
    assert "transition:transform .32s cubic-bezier(.2,.8,.2,1)" in CSS


def test_codex_usage_window_toggle_uses_the_compact_control_size():
    assert "width:54px" in CSS
    assert "min-height:18px" in CSS
    assert "font-size:10px" in CSS
    assert "transform:translateX(54px)" in CSS


def test_usage_window_motion_is_not_silently_skipped_for_the_explicit_control():
    assert "if(_accountUsageData&&stage&&content){" in UI
    assert "const reduceMotion=!!" not in UI
    assert "chat-usage-widget-window-content.is-incoming,.chat-usage-widget-window-content.is-outgoing{animation:none;}" not in CSS
    assert ".chat-usage-widget-window-content.is-incoming .chat-usage-widget-percent" in CSS
    assert ".chat-usage-widget-window-content.is-outgoing .chat-usage-widget-percent" in CSS
    assert ".chat-usage-widget-label-text.is-incoming" in CSS
    assert ".chat-usage-widget-label-text.is-outgoing" in CSS
    assert ".chat-usage-widget-window-content.is-outgoing .chat-usage-widget-battery" in CSS
    assert "animation:chatUsageWindowTextEnter .24s ease-out .12s both" in CSS
    assert "animation:chatUsageWindowTextExit .16s ease-in both" in CSS
    assert "function _renderAccountUsageBattery(remainingPercent)" in UI
    assert "battery.dataset.level=remaining<=5?'danger':(remaining<=20?'warn':'normal');" in UI
    assert "transition-delay:calc(var(--usage-battery-index)*35ms);" in CSS
