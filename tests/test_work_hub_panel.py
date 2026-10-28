"""Static contracts for the native Work Hub screen."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_work_hub_uses_native_panel_and_curated_mx_icons():
    page = read("static/index.html")
    script = read("static/work-hub.js")

    assert 'id="panelNotes"' in page
    assert "Work Hub" in page
    assert "static/work-hub.js" in page
    assert "mx-icons" in script
    assert "react" not in script.lower()


def test_work_hub_control_icons_have_distinct_svg_paths():
    icon_script = ROOT / "static/vendor/mx-icons/work-hub-icons.js"
    result = subprocess.run(
        [
            "node", "-e",
            "global.window = {}; require(process.argv[1]); const names = ['plus', 'sparkles', 'save', 'loader', 'settings']; const icons = names.map(name => window.WorkHubIcons(name)); if (new Set(icons).size !== names.length) process.exit(1);",
            str(icon_script),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_work_hub_has_a_non_fallback_checkmark_icon():
    icon_script = ROOT / "static/vendor/mx-icons/work-hub-icons.js"
    result = subprocess.run(
        [
            "node", "-e",
            "global.window = {}; require(process.argv[1]); if (window.WorkHubIcons('check') === window.WorkHubIcons('work')) process.exit(1);",
            str(icon_script),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_work_hub_owns_the_main_notes_surface_not_the_sidebar_panel():
    page = read("static/index.html")
    main_notes = page.split('<div id="mainNotes"', 1)[1].split('</div>', 1)[0]
    sidebar_notes = page.split('<div class="panel-view" id="panelNotes">', 1)[1].split('<!-- Profiles panel -->', 1)[0]

    assert 'id="workHub"' in main_notes
    assert 'stickyBoardFrame' not in main_notes
    assert 'id="workHub"' not in sidebar_notes


def test_work_hub_scope_navigation_lives_in_the_notes_sidebar_only():
    page = read("static/index.html")
    script = read("static/work-hub.js")
    sidebar_notes = page.split('<div class="panel-view" id="panelNotes">', 1)[1].split('<!-- Profiles panel -->', 1)[0]

    assert 'id="workHubSidebar"' in sidebar_notes
    assert 'renderWorkHubNavigation' in script
    assert '<aside class="work-hub-nav">' not in script
    assert 'grid-template-columns:' in read("static/style.css") and 'var(--wh-inspector-width)' in read("static/style.css")


def test_work_hub_board_uses_the_notes_surface_without_an_outer_card():
    css = read("static/style.css")
    root_rule = css.split("#workHub {", 1)[1].split("}", 1)[0]
    outer_rule = css.split(".work-hub {", 1)[1].split("}", 1)[0]

    assert "padding: 0" in root_rule
    assert " border: " not in outer_rule
    assert "border-radius" not in outer_rule


def test_work_hub_uses_hermes_theme_tokens_not_blue_fallback_palette():
    css = read("static/style.css")
    work_hub_css = css.split('/* ── Work Hub', 1)[1].split('/* ── Touch responsiveness', 1)[0]

    for token in ("var(--bg)", "var(--surface)", "var(--text)", "var(--muted)", "var(--border)"):
        assert token in work_hub_css
    for fallback in ("--bg-primary", "--text-primary", "--text-secondary", "#0d1424", "#edf3ff"):
        assert fallback not in work_hub_css


def test_work_hub_has_reduced_motion_and_narrow_drawer_rules():
    css = read("static/style.css")

    assert ".work-hub" in css
    assert "prefers-reduced-motion" in css
    assert "@media" in css


def test_work_hub_script_parses_in_supported_node_runtime():
    result = subprocess.run(
        ["node", "--check", str(ROOT / "static/work-hub.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_work_hub_post_bodies_use_the_shared_json_api_contract():
    script = read("static/work-hub.js")

    assert "body: JSON.stringify({ item:" in script
    assert "body: JSON.stringify({ item_id:" in script


def test_work_hub_exposes_current_chat_link_action():
    script = read("static/work-hub.js")

    assert "Link current chat" in script
    assert "linked_session_ids" in script


def test_all_work_scope_does_not_exclude_project_items_or_clear_missing_agent():
    script = read("static/work-hub.js")

    assert "store.activeScope === 'all' ? true" in script
    assert "Unavailable: ${esc(item.agent_profile)}" in script


def test_work_hub_refresh_does_not_overwrite_a_newer_local_revision():
    script = read("static/work-hub.js")

    assert "if ((data.revision || 0) < store.revision) return;" in script


def test_work_hub_search_replaces_results_and_rebinds_item_actions():
    script = read("static/work-hub.js")

    assert "canvas.innerHTML = '';" in script
    assert "renderCanvas(scopedItems()); bind();" in script


def test_new_item_opens_right_inspector_with_editable_title():
    script = read("static/work-hub.js")
    css = read("static/style.css")

    assert 'id="workHubTitle"' in script
    assert "title: titleValue()" in script

    inspector_rule = css.split(".work-hub-inspector {", 1)[1].split("}", 1)[0]
    assert "grid-column: 2" in inspector_rule
    assert "grid-row: 1" in inspector_rule


def test_work_hub_updates_revision_after_delete():
    script = read("static/work-hub.js")

    delete_body = script.split("async function deleteItem", 1)[1].split("async function createItem", 1)[0]
    assert "const result = await request('/api/work_hub/items/delete'" in delete_body
    assert "store.revision = result.revision" in delete_body


def test_narrow_work_hub_uses_css_inspector_width():
    script = read("static/work-hub.js")

    assert "window.matchMedia('(max-width: 620px)').matches" in script


def test_goal_planner_saves_items_without_launching_a_workflow():
    script = read("static/work-hub.js")

    assert 'id="goalPlannerSave"' in script
    assert '"/api/work_hub/workflows/start"' not in script
    assert "item_ids: createdItems.map(item => item.id)" not in script


def test_work_hub_controls_use_skin_safe_accent_contrast_and_no_accent_resizer_bar():
    css = read("static/style.css")

    assert "--accent-contrast:var(--bg)" in css
    assert ".work-hub:hover .work-hub-resizer, .work-hub-resizer:hover { opacity: 1; background: transparent; }" in css


def test_work_hub_has_icon_only_create_and_per_board_filters():
    script = read("static/work-hub.js")
    css = read("static/style.css")
    assert 'id="workHubCreate" aria-label="New item"' in script
    assert "work-hub-board-filter" in script
    assert "boardFilters" in script
    assert "priority" in script
    assert "work-hub-column-filter" in css
    assert css.count("background: var(--accent); color: var(--accent-contrast);") >= 3


def test_workspace_work_hub_mirror_replaces_legacy_notes_board_preview():
    page = read("static/index.html")
    workspace = read("static/workspace.js")
    work_hub = read("static/work-hub.js")

    assert 'id="workspaceWorkHubList"' in page
    assert 'id="workspaceNotesBoardsList"' not in page
    assert "renderWorkspaceWorkHub" in workspace
    assert "window.renderWorkspaceWorkHub" in work_hub
    assert "window.openWorkHubItem" in work_hub


def test_workspace_work_hub_mirror_uses_the_active_chat_project_boards_and_expands_tasks():
    work_hub = read("static/work-hub.js")

    assert "const boards = (data.boards || []).filter(board => board.project_id === projectId);" in work_hub
    assert "const boardIds = new Set(boards.map(board => board.id));" in work_hub
    assert "boardIds.has(item.board_id)" in work_hub
    assert "workspaceExpandedBoards" in work_hub
    assert "workspace-work-hub-tasks" in work_hub
    assert "workspace-work-hub-board-open" in work_hub


def test_workspace_work_hub_mirror_is_board_first_and_scope_aware():
    work_hub = read("static/work-hub.js")
    css = read("static/style.css")

    assert "workspaceExpandedBoards" in work_hub
    assert "workspace-work-hub-board" in work_hub
    assert "workspace-work-hub-board-toggle" in work_hub
    assert "No active tasks." in work_hub
    assert "openWorkHubItem(null, projectId, board.id)" in work_hub
    assert "project?.name || 'Project work'" in work_hub
    assert ".workspace-work-hub-board" in css
    assert ".workspace-work-hub-task" in css


def test_workspace_work_hub_board_open_replaces_stale_project_scope():
    script = read("static/work-hub.js")
    instrumented = script.replace(
        "\n})();\n\n/* Goal Planner dialog UI. */",
        "\nwindow.__workHubStore = store; window.__openWorkHubItem = openWorkHubItem;\n})();\n\n/* Goal Planner dialog UI. */",
        1,
    )
    runner = """
const source = %s;
global.localStorage = {getItem(){ return null; }, setItem(){}};
global.window = {addEventListener(){}, matchMedia(){ return {matches:false}; }};
global.document = {getElementById(){ return null; }, addEventListener(){}, querySelectorAll(){ return []; }};
global.api = async () => ({});
(async () => {
  eval(source);
  window.__workHubStore.activeFolderId = 'project-a';
  await window.__openWorkHubItem(null, 'project-b', 'board-b');
  if (window.__workHubStore.activeFolderId !== 'project-b' || window.__workHubStore.activeBoardId !== 'board-b') process.exit(1);
})().catch(error => { console.error(error.stack); process.exit(1); });
""" % repr(instrumented)
    result = subprocess.run(["node", "-e", runner], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_work_hub_mutations_notify_the_open_workspace_panel_mirror():
    """Board-level mutations must refresh the already mounted chat-side mirror."""
    script = read("static/work-hub.js")

    for start, end in (
        ("async function createWorkHubProject", "function showWorkHubBoardProjectPicker"),
        ("async function createWorkHubBoard", "async function renameWorkHubBoard"),
        ("async function renameWorkHubBoard", "async function deleteWorkHubBoard"),
        ("async function deleteWorkHubBoard", "function renderCanvas"),
        ("async function changeWorkflow", "function initResizer"),
    ):
        mutation = script.split(start, 1)[1].split(end, 1)[0]
        assert "notifyWorkHubChanged()" in mutation

    instrumented = script.replace(
        "\n})();\n\n/* Goal Planner dialog UI. */",
        "\nwindow.__notifyWorkHubChanged = notifyWorkHubChanged;\n})();\n\n/* Goal Planner dialog UI. */",
        1,
    )
    runner = """
const source = %s;
const events = [];
global.localStorage = {getItem(){ return null; }, setItem(){}};
global.CustomEvent = function(type){ this.type = type; };
global.window = {addEventListener(){}, matchMedia(){ return {matches:false}; }};
global.document = {
  getElementById(){ return null; }, addEventListener(){}, querySelectorAll(){ return []; },
  dispatchEvent(event){ events.push(event.type); },
};
global.api = async () => ({});
eval(source);
window.__notifyWorkHubChanged();
if (events.join(',') !== 'work-hub-changed') process.exit(1);
""" % repr(instrumented)
    result = subprocess.run(["node", "-e", runner], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def test_composer_does_not_offer_workspace_panel_toggle():
    page = read("static/index.html")

    assert 'id="btnWorkspacePanelToggle"' not in page


def test_work_hub_does_not_render_floating_workspace_panel_arrow():
    page = read("static/index.html")
    css = read("static/style.css")

    assert 'id="btnWorkspacePanelEdgeToggle"' in page
    assert 'main.main.showing-notes ~ #btnWorkspacePanelEdgeToggle{display:none!important;}' in css


def test_work_hub_closes_an_open_workspace_panel_on_entry():
    panels = read("static/panels.js")
    assert "if (nextPanel === 'notes' && typeof closeWorkspacePanel === 'function') closeWorkspacePanel();" in panels


def test_work_hub_project_tiles_use_chat_project_metadata_and_boards():
    script = read("static/work-hub.js")

    assert "store.projects = data.projects || []" in script
    assert "store.projects.forEach(project =>" in script
    assert "board.project_id === project.project_id" in script
    assert "work-hub-project-tile" in script
    assert "item.status !== 'cancelled'" in script
    assert "project.name || 'Untitled project'" in script
    assert "project.color || 'var(--accent)'" in script


def test_work_hub_project_tiles_have_a_narrow_skin_safe_layout():
    css = read("static/style.css")

    assert ".work-hub-project-tile" in css
    assert "var(--accent-bg)" in css
    assert "@media (max-width: 620px)" in css


def test_work_hub_workspace_folders_reuse_chat_hierarchy_for_nested_boards():
    script = read("static/work-hub.js")
    css = read("static/style.css")

    assert "project-folder-list work-hub-projects" in script
    assert "project-chip project-folder-row work-hub-project-tile" in script
    assert "project-folder-sessions work-hub-project-boards" in script
    assert "project-folder-sessions-inner work-hub-project-boards-inner" in script
    project_row_rule = css.split(".work-hub-project-tile{", 1)[1].split("}", 1)[0]
    assert "grid-template-columns:16px 8px minmax(0,1fr) auto" in project_row_rule


def test_workspace_graph_is_a_files_adjacent_tab_with_safe_empty_and_error_states():
    page = read("static/index.html")
    workspace = read("static/workspace.js")

    tabs = page.split('class="workspace-panel-tabs"', 1)[1].split('</div>', 1)[0]
    assert tabs.index('id="workspaceFilesTab"') < tabs.index('id="workspaceGraphTab"') < tabs.index('id="workspaceArtifactsTab"')
    assert 'id="workspaceGraphPane"' in page
    assert "id: 'graph'" in workspace
    assert "No graph is available for this workspace yet." in workspace
    assert "Unable to load this workspace graph." in workspace


def test_chat_project_refresh_notifies_work_hub_to_reload_shared_projects():
    sessions = read("static/sessions.js")

    assert "project-sessions-changed" in sessions


def test_work_hub_uses_nested_boards_and_a_real_filter_icon():
    script = read("static/work-hub.js")
    icons = read("static/vendor/mx-icons/work-hub-icons.js")

    assert "boardFilters" in script
    assert "work-hub-board-row" in script
    assert "work-hub-project-boards" in script
    assert "createWorkHubBoard" in script
    assert "deleteWorkHubBoard" in script
    assert "renameWorkHubBoard" in script
    assert "data-rename-board" in script
    assert "showWorkHubBoardProjectPicker" in script
    assert "project-picker-item" in script
    assert "icon('pencil')" in script
    assert "icon('filter')" in script


def test_work_hub_board_rename_uses_themed_mx_icon_control():
    script = read("static/work-hub.js")
    css = read("static/style.css")
    icons = read("static/vendor/mx-icons/work-hub-icons.js")

    assert 'class="work-hub-board-rename"' in script
    assert '>Rename<' not in script
    assert "pencil:" in icons
    assert ".work-hub-board-rename" in css
    assert "filter:" in icons


def test_work_hub_board_project_picker_uses_chat_style_rows_not_native_buttons():
    script = read("static/work-hub.js")
    css = read("static/style.css")

    assert "const item = document.createElement('div'); item.className = 'project-picker-item';" in script
    assert "const item = document.createElement('button'); item.type = 'button'; item.className = 'project-picker-item';" not in script
    assert "width:6px;height:6px;border-radius:50%;background:" in script
    assert ";flex-shrink:0;" in script
    assert ".project-picker-item{font-weight:600;" in css
    assert ".project-folder-list .project-chip .color-dot{margin-right:4px;}" in css
    assert ".work-hub-project-color{width:8px;height:8px;border-radius:50%;margin-right:4px;}" in css


def test_work_hub_board_selection_keeps_its_folder_scope_and_folder_toggle_is_accessible():
    script = read("static/work-hub.js")

    assert "b.setAttribute('aria-expanded', String(expanded))" in script
    assert "data-folder-id=\"${esc(project.project_id)}\"" in script
    assert "store.activeFolderId = button.dataset.folderId" in script
    assert "child.inert" not in script
    assert "boardsList.classList.toggle('expanded', expanded)" in script
    assert "boardsList.inert = !expanded" in script


def test_work_hub_collapsed_board_lists_have_no_intrinsic_row_height():
    css = read("static/style.css")

    chat_workspace_css = css.split("/* Projects folder list", 1)[1]
    boards_rule = chat_workspace_css.split(".project-folder-sessions{", 1)[1].split("}", 1)[0]
    inner_rule = chat_workspace_css.split(".project-folder-sessions-inner{", 1)[1].split("}", 1)[0]
    assert "grid-template-rows:0fr" in boards_rule
    assert "overflow:hidden" in inner_rule
    assert "min-height:0" in inner_rule


def test_graph_tab_is_icon_only_and_hides_files_surface():
    page = read("static/index.html")
    workspace = read("static/workspace.js")

    assert 'id="workspaceGraphTab"' in page and "Graph View</button>" not in page
    assert "previewArea.hidden = nextId !== 'files'" in workspace
    assert "emptyState.hidden = nextId !== 'files'" in workspace
    assert "fileTree.hidden = nextId !== 'files'" in workspace
    assert "breadcrumb.hidden = nextId !== 'files'" in workspace


def test_graph_tab_has_the_same_exclusive_pane_css_contract_as_other_tabs():
    css = read("static/style.css")

    assert '.rightpanel[data-active-tab="graph"] .breadcrumb-bar,.rightpanel[data-active-tab="graph"] .file-tree,.rightpanel[data-active-tab="graph"] #wsEmptyState,.rightpanel[data-active-tab="graph"] .workspace-artifacts{display:none!important;}' in css
    assert '.rightpanel:not([data-active-tab="graph"]) .workspace-graph-pane{display:none!important;}' in css
    assert '.rightpanel:has(#workspaceGraphTab.active) .preview-area.visible{display:flex!important;}' in css


def test_graph_tab_reuses_the_proven_html_preview_frame_without_file_chrome():
    css = read("static/style.css")
    workspace = read("static/workspace.js")

    assert "function _openWorkspaceGraphPreview()" in workspace
    assert "showPreview('html')" in workspace
    assert "$('previewHtmlIframe')" in workspace
    assert "_graphPreviewUrl(project.graph, tokens)" in workspace
    assert '.rightpanel[data-active-tab="graph"] .preview-area.visible{display:flex!important;}' in css


def test_graph_view_passes_theme_before_load_and_has_a_compact_loading_state():
    """Graph View must avoid a default-theme flash and never stretch its retry button."""
    css = read("static/style.css")
    workspace = read("static/workspace.js")

    assert "hermes_graph_theme" in workspace
    assert "workspace-graph-loading" in workspace
    assert "workspace-graph-loading-pending" in workspace
    assert "event.data.type !== 'hermes-graph-ready'" in workspace
    assert "iframe.src = 'about:blank';" not in workspace.split("function _openWorkspaceGraphPreview()", 1)[1].split("function _renderWorkspaceGraphPane()", 1)[0]
    assert ".workspace-graph-empty .sm-btn{flex:none;width:auto;min-height:30px;" in css
    assert "@media(prefers-reduced-motion:reduce){.workspace-graph-loading" in css
    assert ".preview-area.workspace-graph-loading-pending #previewHtmlIframe{opacity:0;}" in css


def test_graph_view_refreshes_after_workspace_mutations_and_navigation():
    """A changed workspace must not leave an already open graph frozen."""
    css = read("static/style.css")
    workspace = read("static/workspace.js")

    assert "function _scheduleWorkspaceGraphRefresh()" in workspace
    assert "_scheduleWorkspaceGraphRefresh();" in workspace
    assert "_workspaceGraphMapPromise = null" in workspace
    assert '.rightpanel[data-active-tab="graph"] .preview-path{display:none!important;}' in css


def test_workspace_graph_empty_state_does_not_share_height_with_the_file_preview():
    css = read("static/style.css")
    workspace = read("static/workspace.js")

    assert '.rightpanel[data-active-tab="graph"] .preview-area.visible{display:flex!important;}' in css
    assert "if(preview) preview.hidden = true;" in workspace


def test_workspace_live_refresh_does_not_repeat_the_optional_git_badge_probe():
    workspace = read("static/workspace.js")

    assert "preservePreview:true,refreshGit:false" in workspace
    assert "opts.refreshGit!==false" in workspace


def test_files_use_an_exclusive_preview_state_instead_of_a_tree_preview_split():
    workspace = read("static/workspace.js")
    css = read("static/style.css")

    assert "function setWorkspaceFilePreviewState(active)" in workspace
    assert "setWorkspaceFilePreviewState(true);" in workspace
    assert "setWorkspaceFilePreviewState(false);" in workspace
    assert "panel.dataset.filePreview" in workspace
    assert '.rightpanel[data-file-preview="true"] .file-tree{display:none!important;}' in css


def test_non_graph_workspace_tabs_hide_stale_file_preview():
    css = read("static/style.css")

    for tab in ("artifacts", "todos", "office", "plane", "preview"):
        assert f'.rightpanel[data-active-tab="{tab}"] .preview-area{{display:none!important;}}' in css


def test_graph_parent_sends_hermes_theme_tokens_after_iframe_load():
    workspace = read("static/workspace.js")

    assert "function _sendWorkspaceGraphTheme" in workspace
    assert "hermes-graph-theme" in workspace
    assert "getComputedStyle(document.documentElement)" in workspace
