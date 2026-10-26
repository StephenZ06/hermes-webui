"""Regression coverage for the cross-panel spacing and fluid-layout pass."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
PANELS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
WORK_HUB = (ROOT / "static" / "work-hub.js").read_text(encoding="utf-8")
OFFICE = (ROOT / "static" / "office" / "index.js").read_text(encoding="utf-8")
SESSIONS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")


def test_navigation_dividers_use_the_shared_vertical_rhythm():
    assert 'class="office-panel-divider"' not in HTML
    assert "divider.className = 'profile-concept-divider'" in PANELS
    assert ".office-panel-divider{height:1px;margin:14px 8px;" in CSS
    # The filter box sits evenly between the WORKSPACES and CONVERSATIONS
    # dividers (12px above and below).
    assert "#panelChat{--chat-sidebar-divider-space:8px;--chat-sidebar-section-heading-space:14px;" in CSS


def test_spaces_sidebar_omits_nonessential_intro_and_validation_copy():
    assert 'class="panel-head-sub" data-i18n="workspace_desc"' not in HTML
    assert "hint.textContent=t('workspace_paths_validated_hint');" not in PANELS


def test_profile_concept_card_uses_one_divider_and_equal_responsive_gutters():
    help_body = PANELS[PANELS.index("function _renderProfileConceptHelp("):]
    assert '<div class="main-view-content profile-concept-content">' in help_body
    assert '<div class="detail-card profile-concept-card">' in help_body
    assert 'style="border-top:1px solid var(--border);padding-top:8px;margin-top:4px"' not in help_body
    assert ".profile-concept-content{max-width:none;margin-inline:-8px;}" in CSS
    assert ".profile-concept-card{margin-bottom:0;}" in CSS
    assert "@media(max-width:700px){\n  .main-view-header{padding:8px 16px;}\n  .main-view-body{padding:16px;}\n  .profile-concept-content{margin-inline:0;}\n}" in CSS


def test_chat_workspaces_heading_matches_the_office_divider_pattern():
    assert "const sessionSearchWrap=$('sessionSearch')?.closest('.session-search');" in SESSIONS
    assert "workspacesSection.appendChild(sessionSearchWrap);" in SESSIONS
    assert ".chat-sidebar-section--workspaces{padding:0;border-top:0;}" in CSS
    assert ".chat-sidebar-section--workspaces .chat-sidebar-section-heading,.chat-sidebar-section--conversations .chat-sidebar-section-heading{margin:15px 4px 13px;" in CSS
    assert ".chat-sidebar-section--workspaces .chat-sidebar-section-heading::before,.chat-sidebar-section--workspaces .chat-sidebar-section-heading::after{content:\"\";height:1px;flex:1;background:var(--border);}" in CSS
    assert ".chat-sidebar-section--workspaces .sidebar-search{padding:0 4px 10px;}" in CSS


def test_chat_conversations_heading_uses_the_same_centered_divider_pattern():
    assert ".chat-sidebar-section--conversations{margin:0 0 3px;padding:0;border-top:0;}" in CSS
    assert ".chat-sidebar-section--conversations .chat-sidebar-section-heading{margin:3px 4px 0;gap:10px;padding:0;}" in CSS
    assert ".chat-sidebar-section--conversations .chat-sidebar-section-heading::before,.chat-sidebar-section--conversations .chat-sidebar-section-heading::after{content:\"\";height:1px;flex:1;background:var(--border);}" in CSS
    assert ".chat-sidebar-section--conversations .chat-sidebar-section-heading svg{display:none;}" in CSS
    assert ".chat-sidebar-section--workspaces .project-folder-list{padding:6px 4px 8px;}" in CSS
    assert ".chat-sidebar-section--conversations + .session-date-header{padding-top:0;}" in CSS


def test_knowledge_rows_and_work_hub_folders_use_the_panel_width():
    # width:auto, not 100%: with the 4px side margins a 100% row overflowed the
    # list on the right; auto keeps both insets equal to the search box.
    assert ".knowledge-item{width:auto;margin-inline:4px;min-width:0;overflow:hidden;" in CSS
    assert ".knowledge-item .skill-name{min-width:0;flex:1;flex-shrink:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}" in CSS
    assert "#workHubProjects.work-hub-projects{padding:0 0 10px;}" in CSS


def test_insights_and_logs_use_fluid_gutters_and_a_narrow_layout():
    assert "#insightsContent{padding:clamp(16px,2.5vw,32px);}" in CSS
    assert ".logs-main-body{padding:clamp(16px,2.5vw,32px);}" in CSS
    assert "@media (max-width:640px){#insightsContent,.logs-main-body{padding:14px;}" in CSS


def test_task_status_is_viewport_bounded_but_not_artificially_height_capped():
    assert ".office-tasks-body{display:grid;grid-template-rows:minmax(0,1fr);" in CSS
    assert "max-height:calc(100vh - 100px);" in CSS


def test_office_and_work_hub_use_the_shared_section_heading_pattern():
    assert 'office-tools-title' not in HTML  # Dashboard/Integrations sit directly under the head
    assert 'class="office-sidebar-section-title office-history-title"' in HTML
    assert ".office-page-nav{padding:0 8px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));" in CSS
    assert "officeIcon('workspace-heading')" not in OFFICE
    assert "officeIcon('setting3-linear')" not in OFFICE
    assert "officeIcon('history2-bold')" not in OFFICE
    assert '<div class="work-hub-nav-label work-hub-projects-heading"><span>WORKSPACES</span></div><div id="workHubProjects"' in WORK_HUB
    # The row holds + at rest and Done while deleting projects.
    assert '<div class="work-hub-project-create-row">${store.deleteMode' in WORK_HUB
    assert 'class="work-hub-project-create" id="workHubProjectCreate"' in WORK_HUB
    assert 'style="flex:1;min-height:0;overflow:auto;"' not in WORK_HUB
    assert "${icon('dashboard')}<span>WORKSPACES</span>" not in WORK_HUB
    assert 'class="work-hub-scope-divider"' not in WORK_HUB
    # Tighter above the WORKSPACES divider than below it.
    assert ".work-hub-projects-heading{position:relative;display:flex;align-items:center;gap:10px;margin:6px 0 14px;" in CSS
    assert ".work-hub-projects-heading::before,.work-hub-projects-heading::after{content:\"\";height:1px;flex:1;background:var(--border);}" in CSS
    assert ".work-hub-projects-heading::before{margin-left:0;}.work-hub-projects-heading::after{margin-right:0;}" in CSS
    assert ".work-hub-project-create-row{position:relative;display:flex;justify-content:center;padding:0 0 8px;}" in CSS


def test_work_hub_project_menu_has_three_centered_actions():
    # New board, New project, and Delete (which enters the wiggling
    # delete mode; boards are deleted from that mode too, not a menu entry).
    assert "New board</button><button type=\"button\" data-create-project>New project</button><button type=\"button\" class=\"is-danger\" data-delete-project>Delete</button>" in WORK_HUB
    assert "data-delete-board>Delete board</button>" not in WORK_HUB
    assert ".work-hub-create-menu{position:absolute;left:0;right:0;top:calc(100% + 6px);" in CSS
    assert ".work-hub-create-menu button{text-align:center;" in CSS


def test_work_hub_project_tiles_show_board_counts_and_include_main_boards_in_delete_picker():
    assert "const count = boards.length;" in WORK_HUB
    assert 'aria-label="${count} boards"' in WORK_HUB
    assert "board.default ? '' : `<button type=\"button\" class=\"work-hub-board-delete\"" not in WORK_HUB
    assert "class=\"work-hub-board-delete\" data-delete-board=" in WORK_HUB


def test_office_section_titles_use_icon_free_dividers_with_double_spacing():
    assert ".office-sidebar-section-title{margin:20px 8px;" in CSS
    assert ".office-project-folders-title{margin:14px 0;" in CSS
    assert ".office-project-folders{flex:0 0 auto;padding:0 8px;" in CSS
    assert ".office-sidebar-list{flex:1;min-height:0;overflow-y:auto;padding:0 8px;" in CSS
    assert ".office-history-title{margin:9px 8px 4px;}" in CSS
    project_folder_body = OFFICE[OFFICE.index("function renderProjectFolders("):]
    assert "workspace-heading" not in project_folder_body


def test_office_section_titles_center_labels_inside_their_dividers():
    assert ".office-sidebar-section-title,.office-project-folders-title{display:flex;align-items:center;gap:10px;" in CSS
    assert ".office-sidebar-section-title>span,.office-project-folders-title>span{flex:0 0 auto;text-align:center;}" in CSS
