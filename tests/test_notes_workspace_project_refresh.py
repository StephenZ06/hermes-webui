"""Regression coverage for Notes and workspace project-context transitions."""
from __future__ import annotations

import pathlib


REPO = pathlib.Path(__file__).parent.parent
NOTES_JS = (REPO / "static" / "notes.js").read_text(encoding="utf-8")
CSS = (REPO / "static" / "style.css").read_text(encoding="utf-8")
SESSIONS_JS = (REPO / "static" / "sessions.js").read_text(encoding="utf-8")
WORKSPACE_JS = (REPO / "static" / "workspace.js").read_text(encoding="utf-8")


def _function_block(source: str, marker: str, next_marker: str) -> str:
    start = source.index(marker)
    end = source.index(next_marker, start)
    return source[start:end]


def test_saved_note_refreshes_workspace_views_without_reselecting_the_iframe_board():
    """A debounce save must never rebuild the active iframe while it is being typed in."""
    listener = _function_block(
        NOTES_JS,
        "// Keep the workspace preview in sync when the sticky-board iframe saves changes.",
        "\n});",
    )

    assert "loadNotesPanel()" not in listener
    assert "_renderWorkspaceNotesPane()" in listener


def test_saved_note_updates_the_workspace_preview_from_its_confirmed_snapshot():
    """The parent must not wait for a second GET before showing a saved edit."""
    listener = _function_block(
        NOTES_JS,
        "// Keep the workspace preview in sync when the sticky-board iframe saves changes.",
        "\n});",
    )
    iframe = (REPO / "static" / "vendor" / "sticky-board" / "index.html").read_text(encoding="utf-8")

    assert "const savedBoard = _notesBoards.find" in listener
    assert "savedBoard.columns = e.data.columns" in listener
    assert "var columnsSnapshot" in iframe
    assert "columns: columnsSnapshot" in iframe
    assert "if (!response.ok)" in iframe


def test_notes_refresh_discards_older_overlapping_board_responses():
    """A delayed earlier save may not restore an older board snapshot."""
    helper = _function_block(
        NOTES_JS,
        "async function _refreshNotesPanelData()",
        "\nasync function loadNotesPanel",
    )

    assert "const refreshGeneration = ++_notesDataRefreshGeneration" in helper
    assert "if (refreshGeneration !== _notesDataRefreshGeneration) return false;" in helper


def test_workspace_notes_preview_renders_only_the_board_selected_in_its_context():
    """The selector is separate from the preview; boards must never be combined."""
    helper = _function_block(
        NOTES_JS,
        "function _renderWorkspaceNotesPreview",
        "\nfunction _renderWorkspaceNotesPane",
    )

    assert "const board = _workspaceNotesSelectedBoard(projectId);" in helper
    assert "for (const board of boards)" not in helper
    assert "Select a board above to view its notes." in helper


def test_workspace_board_selection_is_scoped_to_project_or_all_boards_context():
    helpers = _function_block(
        NOTES_JS,
        "function _workspaceNotesScopeKey",
        "\nfunction _renderWorkspaceNotesContext",
    )

    assert "_workspaceNotesSelectedBoards" in helpers
    assert "return projectId || '__all__';" in helpers
    assert "function _selectWorkspaceNotesBoard" in helpers


def test_workspace_refresh_after_chat_navigation_keeps_tree_loading_separate_from_notes():
    """A slow workspace/git refresh cannot delay the project-scoped Notes request."""
    helper = _function_block(
        SESSIONS_JS,
        "function _deferWorkspaceRefreshForSession",
        "\nfunction _resolveSessionModelForDisplaySoon",
    )

    assert "loadDir('.', opts)" in helper
    assert "refreshWorkspaceNotesPane" not in helper


def test_workspace_notes_never_labels_general_boards_as_unlinked():
    assert "Unlinked boards" not in NOTES_JS


def test_workspace_notes_refresh_fetches_current_boards_before_rendering_context():
    """Opening the docked Notes tab must not rely on data cached by the full Notes page."""
    helper = _function_block(
        NOTES_JS,
        "async function refreshWorkspaceNotesPane",
        "\nfunction _buildStickyBoardRow",
    )

    assert "await _refreshNotesPanelData()" in helper
    assert "_renderWorkspaceNotesPane(_workspaceNotesProjectId())" in helper


def test_workspace_notes_refresh_is_bound_to_the_selected_session_context():
    """A late Project X request may never repaint Project Y's Notes pane."""
    helper = _function_block(
        NOTES_JS,
        "async function refreshWorkspaceNotesPane",
        "\nfunction _buildStickyBoardRow",
    )

    assert "const sessionId = options.sessionId" in helper
    assert helper.count("_isWorkspaceNotesSessionCurrent(sessionId)") >= 2
    assert "_renderWorkspaceNotesPane(_workspaceNotesProjectId())" in helper


def test_workspace_notes_uses_the_chat_project_assignment_not_an_inherited_workspace():
    """A general chat may reuse a project path but must still show all boards."""
    helper = _function_block(
        NOTES_JS,
        "function _workspaceNotesProjectId()",
        "\nfunction _workspaceFilteredBoards",
    )

    assert "return session.project_id || null;" in helper
    assert "matchingProjects" not in helper


def test_general_chat_workspace_notes_shows_only_unlinked_boards():
    helper = _function_block(
        NOTES_JS,
        "function _workspaceFilteredBoards",
        "\nfunction _renderWorkspaceNotesContext",
    )

    assert "return _notesBoards.filter(b => !b.project_id);" in helper


def test_workspace_notes_only_uses_an_expandable_row_when_subtasks_exist():
    helper = _function_block(
        NOTES_JS,
        "function _renderWorkspaceNotesPreview",
        "\nfunction _renderWorkspaceNotesPane",
    )

    assert "for (const subTask of note.subItems || [])" in helper
    assert "document.createElement(subtasks.childElementCount ? 'details' : 'div')" in helper
    assert "document.createElement('summary')" in helper
    assert "workspace-notes-note-summary" in helper


def test_workspace_note_expander_precedes_its_title():
    assert ".workspace-notes-note-summary::before" in CSS
    at = CSS.index(".workspace-notes-note-summary::before")
    rule = CSS[at:CSS.index("\n", at)]
    assert "margin-right:6px" in rule
    assert "position:relative;top:-1px" in rule
    assert ".workspace-notes-note-summary::after" not in CSS


def test_workspace_note_summary_is_the_full_row_click_target():
    at = CSS.index(".workspace-notes-note-summary{")
    rule = CSS[at:CSS.index("\n", at)]
    assert "width:100%" in rule
    assert "box-sizing:border-box" in rule
    assert "padding:6px 8px" in rule


def test_long_workspace_note_subitems_wrap_without_being_clipped():
    at = CSS.index(".workspace-notes-subtask{")
    rule = CSS[at:CSS.index("}", at)]
    assert "white-space:pre-wrap" in rule
    assert "overflow-wrap:anywhere" in rule


def test_sticky_board_note_text_controls_are_multiline_and_auto_grow():
    """Pasted notes must show their complete text instead of an input's one-line viewport."""
    iframe = (REPO / "static" / "vendor" / "sticky-board" / "index.html").read_text(encoding="utf-8")

    assert "function autoGrowTextarea(textarea)" in iframe
    assert "var input = el('textarea', {" in iframe
    assert "var titleInput = el('textarea', {" in iframe
    assert "autoGrowTextarea(input);" in iframe
    assert "autoGrowTextarea(titleInput);" in iframe
    assert ".note-title{\n" in iframe
    assert "white-space:pre-wrap;overflow-wrap:anywhere;" in iframe


def test_sticky_board_multiline_controls_keep_existing_enter_shortcuts():
    iframe = (REPO / "static" / "vendor" / "sticky-board" / "index.html").read_text(encoding="utf-8")
    keydown = iframe[iframe.index("document.addEventListener('keydown'"):iframe.index("// ── Drag & Drop")]

    assert keydown.count("if (e.key === 'Enter' && !e.shiftKey)") == 2


def test_workspace_notes_reads_the_app_session_not_a_window_property():
    """`S` is a global lexical const, so it is not exposed as `window.S`."""
    session_helpers = _function_block(
        NOTES_JS,
        "function _workspaceNotesProjectId()",
        "\nfunction _workspaceFilteredBoards",
    )

    assert "window.S && S.session" not in NOTES_JS
    assert "const session = _workspaceNotesSession();" in session_helpers
    assert "typeof S !== 'undefined'" in NOTES_JS


def test_session_selection_repaints_notes_before_transcript_loading_finishes():
    """Changing projects clears the prior board immediately, not after message I/O."""
    body = _function_block(
        SESSIONS_JS,
        "async function loadSession(",
        "\nfunction _isMessagingSession",
    )

    assign_idx = body.index("S.session=data.session;")
    render_idx = body.index("renderWorkspaceNotesPaneForSession(", assign_idx)
    refresh_idx = body.index("refreshWorkspaceNotesPane({", assign_idx)
    messages_idx = body.index("await _ensureMessagesLoaded(", assign_idx)

    assert assign_idx < render_idx < refresh_idx < messages_idx
    assert "sessionId: sid" in body[render_idx:messages_idx]
    assert "projectId:" not in body[render_idx:messages_idx]


def test_workspace_notes_tab_and_session_navigation_both_fetch_fresh_data():
    mount = _function_block(
        WORKSPACE_JS,
        "registerChatPane({\n  id: 'plane'",
        "\n// ── Live preview pane",
    )
    load_session = _function_block(
        SESSIONS_JS,
        "async function loadSession(",
        "\nfunction _isMessagingSession",
    )

    # The Plane tab is now the Work Hub view: mounting it re-renders through
    # the Work Hub renderer, which fetches its own data rather than painting a
    # cached list.
    assert "renderWorkspaceWorkHub()" in mount
    work_hub_js = (REPO / "static" / "work-hub.js").read_text(encoding="utf-8")
    renderer = work_hub_js[work_hub_js.index("async function renderWorkspaceWorkHub()"):]
    renderer = renderer[: renderer.index("\n  async function ", 1)]
    assert "await request('/api/work_hub/bootstrap')" in renderer
    # Session navigation still refreshes the notes pane for that session.
    assert "refreshWorkspaceNotesPane({" in load_session
    assert "sessionId: sid" in load_session
    assert "projectId:" not in load_session
