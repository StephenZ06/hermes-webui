"""Office Dashboard and Integrations navigation contract."""
import pathlib


REPO = pathlib.Path(__file__).parent.parent
INDEX = (REPO / "static" / "index.html").read_text(encoding="utf-8")
OFFICE = (REPO / "static" / "office" / "index.js").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
ICONS = (REPO / "static" / "vendor" / "mx-icons" / "work-hub-icons.js").read_text(encoding="utf-8")
RFC = (REPO / "docs" / "rfcs" / "office-visualization.md").read_text(encoding="utf-8")


def test_office_sidebar_replaces_the_explainer_with_native_page_navigation():
    office_at = INDEX.index('id="panelOffice"')
    office = INDEX[office_at:INDEX.index('<!-- Workspaces panel -->', office_at)]
    assert 'id="officePageNav"' in office
    assert 'data-office-subview="dashboard"' in office
    assert 'data-office-subview="integrations"' in office
    assert 'Chats that delegated to subagents' not in office
    assert '<div class="sidebar-divider" aria-hidden="true"></div>' not in office
    # Page-nav entries carry image tool marks (nav icon marks redesign).
    assert "['dashboard', '/static/office-dashboard-tool.png', 'Dashboard', 'Office overview']" in OFFICE
    assert "['integrations', '/static/office-integrations-tool.png', 'Integrations', 'Connected accounts']" in OFFICE
    assert (REPO / "static" / "office-dashboard-tool.png").is_file()
    assert (REPO / "static" / "office-integrations-tool.png").is_file()
    assert "dashboard:" in ICONS


def test_office_subviews_have_native_shells_and_return_to_floor_navigation():
    assert "function setOfficeSubview(name)" in OFFICE
    assert "function renderOfficeSubview(container)" in OFFICE
    assert "office-${_officeSubview}" in OFFICE
    assert "_officeSubview === 'dashboard'" in OFFICE
    assert "officeSetSubview('floor')" in OFFICE
    assert "arrow-left" in OFFICE
    assert 'aria-label="Return to the Office floor"' in OFFICE
    assert '<span>Office floor</span>' not in OFFICE


def test_office_resets_to_projects_floor_when_leaving_or_selecting_a_chat():
    assert "function resetOfficeToDefault({ render = false } = {})" in OFFICE
    assert "_officeSubview = 'floor';" in OFFICE
    assert "_outlet = 'projects';" in OFFICE
    assert "_viewMode = 'live';" in OFFICE
    assert "_historyAdapter = null;" in OFFICE
    assert "function unmount()" in OFFICE
    assert "_preserveOfficeNavigationOnUnmount = true;" in OFFICE
    assert "resetOfficeToDefault();" in OFFICE
    show_history = OFFICE[OFFICE.index("function showHistory(parentSessionId)"):OFFICE.index("/** Leave the frozen view")]
    return_live = OFFICE[OFFICE.index("function returnToLive()"):OFFICE.index("/**\n * A one-line summary")]
    assert "resetOfficeToDefault({ render: true });" in show_history
    assert "resetOfficeToDefault({ render: true });" in return_live


def test_office_page_navigation_has_equal_insets_and_theme_safe_narrow_layout():
    assert ".office-page-nav{padding:0 8px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;}" in CSS
    assert ".office-page-nav-btn{display:flex;align-items:center;gap:7px;width:100%;min-height:52px;" in CSS
    assert ".office-page-nav-copy" in CSS
    assert ".office-subview{flex:1;min-height:0;width:100%;overflow:auto;padding:clamp(14px,2vw,28px);" in CSS
    assert ".office-subview-head{width:100%;" in CSS
    assert "max-width:1120px" not in CSS[CSS.index(".office-subview{"):CSS.index(".office-session-row{")]
    assert "@media (max-width:1000px)" in CSS
    assert "@media (max-width:640px){.office-subview{padding:14px;}" in CSS


def test_office_navigation_icons_use_the_sidebar_muted_gray_treatment():
    assert ".office-page-nav-icon" in CSS
    icon_rule = CSS[CSS.index(".office-page-nav-icon{"):CSS.index(".office-page-nav-btn .work-hub-icon{")]
    assert "color:var(--muted);" in icon_rule


def test_office_navigation_cards_use_solid_surfaces_without_glow_or_gradients():
    cards = CSS[CSS.index(".office-page-nav-btn{"):CSS.index(".office-subview{")]
    assert "background:var(--surface-subtle);" in cards
    assert "linear-gradient" not in cards
    assert "box-shadow" not in cards


def test_dashboard_derives_outlet_scoped_cards_from_existing_office_state():
    assert "function officeDashboardModel(state, outlet)" in OFFICE
    assert "const selectedView = mode === 'business'" in OFFICE
    assert "const visibleIds = new Set" in OFFICE
    assert "const scopedWorkers = workers.filter" in OFFICE
    assert "function renderOfficeDashboard(state, opts)" in OFFICE
    assert "office-dashboard-snapshot" in OFFICE
    assert "office-dashboard-distribution" in OFFICE
    assert "office-dashboard-attention" in OFFICE


def test_dashboard_includes_profile_scoped_history_and_office_roster_baselines():
    assert "function dashboardHistoryWorkers(mode)" in OFFICE
    assert "const historicalWorkers = dashboardHistoryWorkers(mode);" in OFFICE
    assert "const baselineAgents = mode === 'business' ? 21 : 4;" in OFFICE
    assert "agents: Math.max(baselineAgents, liveScopedWorkers.length)" in OFFICE
    assert "_historyParents" in OFFICE


def test_dashboard_top_metrics_use_live_workers_not_historical_history():
    assert "const liveScopedWorkers = scopedWorkers.filter(worker => !worker.historical);" in OFFICE
    assert "const liveCounts = taskStatusCounts(liveScopedWorkers);" in OFFICE
    assert "agents: Math.max(baselineAgents, liveScopedWorkers.length)" in OFFICE
    assert "active: liveCounts.running" in OFFICE


def test_dashboard_metrics_navigate_or_focus_their_related_live_sections():
    assert "function dashboardMetricAction(action, model)" in OFFICE
    assert "switchPanel('tasks')" in OFFICE
    assert "openCronDetail" in OFFICE
    assert "scrollDashboardPanelIntoView" in OFFICE
    assert "office-dashboard-panel-focus" in OFFICE
    assert "data-dashboard-metric-action" in OFFICE


def test_dashboard_rows_route_live_attention_and_completed_work_to_its_context():
    assert "function openDashboardWorker" in OFFICE
    assert "worker.historical" in OFFICE
    assert "showHistory(worker.dashboardParentId)" in OFFICE
    assert "data-dashboard-worker-id" in OFFICE
    assert "data-attention-focus" in OFFICE
    assert "office-dashboard-transitioning" in OFFICE
    assert "event.stopPropagation()" in OFFICE


def test_dashboard_attention_cards_offer_existing_approval_and_clarify_responses():
    assert "function dashboardAttentionItems(model)" in OFFICE
    assert "office-dashboard-attention-action" in OFFICE
    assert "data-attention-choice" in OFFICE
    assert "data-attention-input" in OFFICE
    assert "function respondDashboardAttention" in OFFICE
    assert "/api/approval/respond" in OFFICE
    assert "/api/clarify/respond" in OFFICE


def test_integration_cards_have_equal_setup_and_future_configuration_controls():
    assert "office-integration-actions" in OFFICE
    assert "office-integration-settings" in OFFICE
    assert "Configure Gmail integration" in OFFICE
    assert "Choose marketing platform" in OFFICE
    assert "Choose operations provider" in OFFICE
    assert "Choose document provider" in OFFICE
    assert "office-integration-capabilities" not in OFFICE
    assert ".office-integration-card.is-gmail" not in CSS


def test_dashboard_metric_cards_rely_on_equal_padding_not_extra_bottom_height():
    metric_rule = CSS[CSS.index(".office-dashboard-metric{"):CSS.index(".office-dashboard-metric span,")]
    assert "padding:15px;" in metric_rule
    assert "min-height" not in metric_rule


def test_dashboard_reflows_metrics_before_sidebar_constrained_desktop_widths():
    assert "@media (max-width:1400px){.office-dashboard-snapshot{grid-template-columns:repeat(2,minmax(0,1fr));}" in CSS


def test_office_rfc_records_dashboard_and_gmail_connection_boundaries():
    assert "Office Dashboard and Integrations" in RFC
    assert "Gmail" in RFC
    assert "OAuth" in RFC
    assert "does not connect an account automatically" in RFC


def test_dashboard_poll_leaves_unchanged_markup_alone():
    # The reconcile poll re-rendered every few seconds and replayed the
    # empty-state fade, which read as the lower cards flickering.
    body = OFFICE[OFFICE.index("function renderOfficeDashboard(state, opts)"):]
    body = body[:body.index("\nfunction ")]
    assert "if (host._officeDashHtml === html) return;" in body
    assert body.index("if (host._officeDashHtml === html) return;") < body.index("host.innerHTML = html;")
    assert ".office-dashboard-refreshed .office-dash-empty" in CSS


def test_dashboard_lists_chain_the_wheel_to_the_page():
    last = CSS.rindex(".office-dashboard-panel-body{overscroll-behavior:")
    assert CSS[last:].startswith(".office-dashboard-panel-body{overscroll-behavior:auto;}")


def test_every_dashboard_empty_state_icon_has_a_ring():
    rule = CSS[CSS.rindex(".office-dash-empty-icon.is-neutral{"):]
    rule = rule[:rule.index("}")]
    assert "border:1px solid" in rule


def test_floor_detail_empty_state_uses_the_framed_panel_empty():
    panel = OFFICE[OFFICE.index("function dashboardDistributionPanel(model)"):OFFICE.index("function bindDashboardDistribution")]
    assert "dashEmpty('check', 'green', 'Nothing completed yet'" in panel
    assert '<div class="office-dashboard-empty">No completed tasks' not in panel


def test_subviews_enter_with_a_staggered_motion_that_releases_its_fill():
    subview = OFFICE[OFFICE.index("function renderOfficeSubview(container)"):OFFICE.index("function setOfficeSubview(name)")]
    assert "subviewEl.classList.add('is-entering')" in subview
    assert "subviewEl.classList.remove('is-entering')" in subview
    assert "@keyframes office-subview-in" in CSS
    assert "@media (prefers-reduced-motion:reduce){.office-subview.is-entering *{animation:none!important;}}" in CSS


def test_panel_icons_match_their_title_block_and_integration_health_has_a_tile():
    assert ".office-dashboard-panel-head .office-dash-icon,.office-dashboard-integration .office-dash-icon{align-self:stretch;width:auto;height:auto;aspect-ratio:1;" in CSS
    assert '<span class="office-dash-icon is-purple">${officeIcon(\'settings\', \'Integrations\')}</span>' in OFFICE
    assert ".office-integration-card h2{text-transform:uppercase;" in CSS


def test_work_distribution_swap_rebuilds_only_its_own_card():
    # Opening a floor re-rendered the whole dashboard, so every other panel
    # replayed its entry fade (a flicker). The swap replaces that card alone.
    bind = OFFICE[OFFICE.index("function bindDashboardDistribution(host, state)"):]
    bind = bind[:bind.index("\nfunction ")]
    assert "renderOfficeDashboard(state, { swap: 'distribution' })" in bind
    assert "_officeDashHtml = undefined" not in bind
    body = OFFICE[OFFICE.index("function renderOfficeDashboard(state, opts)"):]
    body = body[:body.index("\nfunction ")]
    swap = body[body.index("if (oldCard) {"):body.index("const refreshed")]
    assert "oldCard.replaceWith(card)" in swap
    assert "host.innerHTML" not in swap
    assert "host._officeDashHtml = html;" in swap
